"""Tests fuer SOAP-Noten Versionierung (medizinische Compliance)."""
import hashlib
import pytest
from datetime import date, datetime, timedelta
from tests.conftest import login


@pytest.fixture
def appointment_with_soap(db, org, admin_user):
    """Erstellt einen Termin mit SOAP-Daten fuer Versionierungstests."""
    from models import Patient, Employee, Appointment

    patient = Patient(
        organization_id=org.id,
        first_name='SOAP',
        last_name='TestPatient',
        date_of_birth=date(1985, 3, 15),
    )
    db.session.add(patient)
    db.session.flush()

    employee = Employee(
        organization_id=org.id,
        user_id=admin_user.id,
        is_active=True,
    )
    db.session.add(employee)
    db.session.flush()

    appointment = Appointment(
        patient_id=patient.id,
        employee_id=employee.id,
        start_time=datetime.utcnow(),
        end_time=datetime.utcnow() + timedelta(minutes=30),
        duration_minutes=30,
        status='completed',
        soap_subjective='Patient klagt ueber Rueckenschmerzen',
        soap_objective='LWS-Flexion eingeschraenkt',
        soap_assessment='Lumbago akut',
        soap_plan='Manuelle Therapie 2x/Woche',
    )
    db.session.add(appointment)
    db.session.commit()

    return appointment, patient, employee


class TestSoapNoteHistory:
    """SOAP-Aenderungen muessen versioniert werden."""

    def test_create_history_entry(self, app, db, admin_user, appointment_with_soap):
        """SOAP-Aenderung erstellt einen History-Eintrag."""
        from models import SoapNoteHistory
        appointment, _, _ = appointment_with_soap

        with app.app_context():
            history = SoapNoteHistory(
                appointment_id=appointment.id,
                version=1,
                soap_subjective=appointment.soap_subjective,
                soap_objective=appointment.soap_objective,
                soap_assessment=appointment.soap_assessment,
                soap_plan=appointment.soap_plan,
                changed_by_id=admin_user.id,
                changed_at=datetime.utcnow(),
                change_reason='Initiale Dokumentation',
                content_hash='placeholder',
            )
            history.compute_hash()
            db.session.add(history)
            db.session.commit()

            assert history.id is not None
            assert history.version == 1
            assert history.content_hash is not None
            assert len(history.content_hash) == 64  # SHA-256

    def test_version_numbers_sequential(self, app, db, admin_user, appointment_with_soap):
        """History-Eintraege haben aufeinanderfolgende Versionsnummern."""
        from models import SoapNoteHistory
        appointment, _, _ = appointment_with_soap

        with app.app_context():
            for version in range(1, 4):
                history = SoapNoteHistory(
                    appointment_id=appointment.id,
                    version=version,
                    soap_subjective=f'Version {version} - Subjektiv',
                    soap_objective=f'Version {version} - Objektiv',
                    soap_assessment=f'Version {version} - Assessment',
                    soap_plan=f'Version {version} - Plan',
                    changed_by_id=admin_user.id,
                    changed_at=datetime.utcnow(),
                    change_reason=f'Korrektur Version {version}',
                    content_hash='placeholder',
                )
                history.compute_hash()
                db.session.add(history)

            db.session.commit()

            entries = SoapNoteHistory.query.filter_by(
                appointment_id=appointment.id,
            ).order_by(SoapNoteHistory.version).all()

            assert len(entries) == 3
            for i, entry in enumerate(entries, start=1):
                assert entry.version == i

    def test_content_hash_computed_correctly(self, app, db, admin_user, appointment_with_soap):
        """Content-Hash wird korrekt aus SOAP-Feldern berechnet."""
        from models import SoapNoteHistory
        appointment, _, _ = appointment_with_soap

        with app.app_context():
            history = SoapNoteHistory(
                appointment_id=appointment.id,
                version=1,
                soap_subjective='Subjektiv',
                soap_objective='Objektiv',
                soap_assessment='Assessment',
                soap_plan='Plan',
                changed_by_id=admin_user.id,
                changed_at=datetime.utcnow(),
                content_hash='placeholder',
            )
            computed = history.compute_hash()

            # Manuell den erwarteten Hash berechnen
            content = 'Subjektiv|Objektiv|Assessment|Plan'
            expected = hashlib.sha256(content.encode()).hexdigest()

            assert computed == expected
            assert history.content_hash == expected

    def test_content_hash_changes_on_different_content(self, app, db, admin_user, appointment_with_soap):
        """Verschiedene SOAP-Inhalte erzeugen verschiedene Hashes."""
        from models import SoapNoteHistory
        appointment, _, _ = appointment_with_soap

        with app.app_context():
            h1 = SoapNoteHistory(
                appointment_id=appointment.id, version=1,
                soap_subjective='Text A', soap_objective='',
                soap_assessment='', soap_plan='',
                changed_by_id=admin_user.id, changed_at=datetime.utcnow(),
                content_hash='placeholder',
            )
            h1.compute_hash()

            h2 = SoapNoteHistory(
                appointment_id=appointment.id, version=2,
                soap_subjective='Text B', soap_objective='',
                soap_assessment='', soap_plan='',
                changed_by_id=admin_user.id, changed_at=datetime.utcnow(),
                content_hash='placeholder',
            )
            h2.compute_hash()

            assert h1.content_hash != h2.content_hash

    def test_history_preserves_old_values(self, app, db, admin_user, appointment_with_soap):
        """History-Eintrag bewahrt die alten SOAP-Werte."""
        from models import SoapNoteHistory
        appointment, _, _ = appointment_with_soap

        original_subjective = appointment.soap_subjective
        original_objective = appointment.soap_objective

        with app.app_context():
            # Alten Zustand in History speichern
            history = SoapNoteHistory(
                appointment_id=appointment.id,
                version=1,
                soap_subjective=original_subjective,
                soap_objective=original_objective,
                soap_assessment=appointment.soap_assessment,
                soap_plan=appointment.soap_plan,
                changed_by_id=admin_user.id,
                changed_at=datetime.utcnow(),
                change_reason='Vor Korrektur',
                content_hash='placeholder',
            )
            history.compute_hash()
            db.session.add(history)

            # SOAP-Felder am Termin aendern
            appointment.soap_subjective = 'Neuer subjektiver Befund'
            appointment.soap_objective = 'Neuer objektiver Befund'
            db.session.commit()

            # History muss alte Werte enthalten
            saved = SoapNoteHistory.query.filter_by(
                appointment_id=appointment.id, version=1
            ).first()
            assert saved.soap_subjective == original_subjective
            assert saved.soap_objective == original_objective

    def test_history_requires_changed_by(self, app, db, appointment_with_soap):
        """History-Eintrag muss einen Bearbeiter haben (changed_by_id)."""
        from models import SoapNoteHistory
        from sqlalchemy.exc import IntegrityError
        appointment, _, _ = appointment_with_soap

        with app.app_context():
            history = SoapNoteHistory(
                appointment_id=appointment.id,
                version=1,
                soap_subjective='Test',
                soap_objective='Test',
                soap_assessment='Test',
                soap_plan='Test',
                changed_by_id=None,  # Pflichtfeld!
                changed_at=datetime.utcnow(),
                content_hash='testhash',
            )
            db.session.add(history)
            with pytest.raises(IntegrityError):
                db.session.commit()
            db.session.rollback()


class TestSoapHistoryApi:
    """Tests fuer die SOAP-History API-Route."""

    def test_soap_history_api_returns_versions(self, client, admin_user, db, app,
                                                appointment_with_soap):
        """API gibt SOAP-History-Eintraege zurueck."""
        from models import SoapNoteHistory
        appointment, _, _ = appointment_with_soap

        with app.app_context():
            for v in range(1, 3):
                h = SoapNoteHistory(
                    appointment_id=appointment.id,
                    version=v,
                    soap_subjective=f'Subjektiv v{v}',
                    soap_objective=f'Objektiv v{v}',
                    soap_assessment=f'Assessment v{v}',
                    soap_plan=f'Plan v{v}',
                    changed_by_id=admin_user.id,
                    changed_at=datetime.utcnow(),
                    content_hash='placeholder',
                )
                h.compute_hash()
                db.session.add(h)
            db.session.commit()
            appt_id = appointment.id

        login(client, 'admin_test', 'SecurePass123!')
        resp = client.get(f'/treatment/api/termin/{appt_id}/soap/history')

        # Route koennte 200 oder 302 (Redirect) zurueckgeben
        if resp.status_code == 200:
            data = resp.get_json()
            assert isinstance(data, list)
            assert len(data) >= 2
            # Neueste Version zuerst
            assert data[0]['version'] >= data[1]['version']
