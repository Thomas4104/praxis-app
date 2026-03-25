"""Integration Tests fuer Multi-Tenancy Isolation.

Stellt sicher, dass Organisationen vollstaendig voneinander isoliert sind:
- Patienten, Termine, Rechnungen gehoeren einer Organisation
- Suche und API-Endpoints filtern korrekt nach organization_id
"""
import pytest
from datetime import datetime, date, timedelta
from models import db, Patient, Employee, Appointment, Invoice, Location
from tests.conftest import login, logout


@pytest.fixture
def org_a_data(db, org, admin_user):
    """Testdaten fuer Organisation A (Test-Praxis)."""
    # Standort
    location = Location(organization_id=org.id, name='Standort A', is_active=True)
    db.session.add(location)
    db.session.flush()

    # Mitarbeiter
    employee = Employee(
        organization_id=org.id,
        user_id=admin_user.id,
        employee_number='E001',
        default_location_id=location.id,
        is_active=True,
    )
    db.session.add(employee)
    db.session.flush()

    # Patient
    patient = Patient(
        organization_id=org.id,
        first_name='Anna',
        last_name='Mueller',
        patient_number='P00001',
        date_of_birth=date(1985, 3, 15),
        is_active=True,
    )
    db.session.add(patient)
    db.session.flush()

    # Termin
    start = datetime.now() + timedelta(days=1)
    appointment = Appointment(
        patient_id=patient.id,
        employee_id=employee.id,
        location_id=location.id,
        start_time=start,
        end_time=start + timedelta(minutes=30),
        duration_minutes=30,
        status='scheduled',
    )
    db.session.add(appointment)
    db.session.flush()

    # Rechnung
    invoice = Invoice(
        organization_id=org.id,
        patient_id=patient.id,
        invoice_number='R-2026-001',
        amount_total=150.00,
        amount_open=150.00,
        status='sent',
        due_date=date.today() + timedelta(days=30),
    )
    db.session.add(invoice)
    db.session.commit()

    return {
        'location': location,
        'employee': employee,
        'patient': patient,
        'appointment': appointment,
        'invoice': invoice,
    }


@pytest.fixture
def org_b_data(db, other_org, other_org_user):
    """Testdaten fuer Organisation B (Andere-Praxis)."""
    location = Location(organization_id=other_org.id, name='Standort B', is_active=True)
    db.session.add(location)
    db.session.flush()

    employee = Employee(
        organization_id=other_org.id,
        user_id=other_org_user.id,
        employee_number='E100',
        default_location_id=location.id,
        is_active=True,
    )
    db.session.add(employee)
    db.session.flush()

    patient = Patient(
        organization_id=other_org.id,
        first_name='Bruno',
        last_name='Schmidt',
        patient_number='P00001',
        date_of_birth=date(1990, 7, 20),
        is_active=True,
    )
    db.session.add(patient)
    db.session.flush()

    start = datetime.now() + timedelta(days=2)
    appointment = Appointment(
        patient_id=patient.id,
        employee_id=employee.id,
        location_id=location.id,
        start_time=start,
        end_time=start + timedelta(minutes=30),
        duration_minutes=30,
        status='scheduled',
    )
    db.session.add(appointment)
    db.session.flush()

    invoice = Invoice(
        organization_id=other_org.id,
        patient_id=patient.id,
        invoice_number='R-2026-100',
        amount_total=200.00,
        amount_open=200.00,
        status='sent',
        due_date=date.today() + timedelta(days=30),
    )
    db.session.add(invoice)
    db.session.commit()

    return {
        'location': location,
        'employee': employee,
        'patient': patient,
        'appointment': appointment,
        'invoice': invoice,
    }


class TestPatientIsolation:
    """User in Org A kann KEINE Patienten von Org B sehen."""

    def test_patient_list_shows_only_own_org(self, client, admin_user, org_a_data, org_b_data):
        """Patientenliste zeigt nur Patienten der eigenen Organisation."""
        login(client, 'admin_test', 'SecurePass123!')
        response = client.get('/patients/')
        html = response.data.decode()
        assert 'Anna' in html or 'Mueller' in html
        assert 'Bruno' not in html
        assert 'Schmidt' not in html

    def test_patient_detail_blocked_for_other_org(self, client, admin_user, org_a_data, org_b_data):
        """Zugriff auf Patient aus anderer Organisation wird blockiert (403)."""
        login(client, 'admin_test', 'SecurePass123!')
        other_patient_id = org_b_data['patient'].id
        response = client.get(f'/patients/{other_patient_id}')
        assert response.status_code in (403, 404)

    def test_patient_edit_blocked_for_other_org(self, client, admin_user, org_a_data, org_b_data):
        """Bearbeitung eines Patienten aus anderer Organisation wird blockiert."""
        login(client, 'admin_test', 'SecurePass123!')
        other_patient_id = org_b_data['patient'].id
        response = client.get(f'/patients/{other_patient_id}/edit')
        assert response.status_code in (403, 404)


class TestAppointmentIsolation:
    """User in Org A kann KEINE Termine von Org B sehen."""

    def test_calendar_api_shows_only_own_org(self, client, admin_user, org_a_data, org_b_data):
        """Kalender-API gibt nur Termine der eigenen Organisation zurueck."""
        login(client, 'admin_test', 'SecurePass123!')
        today = date.today().isoformat()
        future = (date.today() + timedelta(days=7)).isoformat()
        response = client.get(f'/calendar/api/appointments?start={today}&end={future}')
        assert response.status_code == 200
        data = response.get_json()
        if data:
            # Alle zurueckgegebenen Termine muessen zur eigenen Org gehoeren
            own_patient_id = org_a_data['patient'].id
            other_patient_id = org_b_data['patient'].id
            for appt in data:
                assert appt.get('patient_id') != other_patient_id


class TestInvoiceIsolation:
    """User in Org A kann KEINE Rechnungen von Org B sehen."""

    def test_billing_list_shows_only_own_org(self, client, admin_user, org_a_data, org_b_data):
        """Rechnungsliste zeigt nur Rechnungen der eigenen Organisation."""
        login(client, 'admin_test', 'SecurePass123!')
        response = client.get('/billing/')
        html = response.data.decode()
        assert 'R-2026-001' in html
        assert 'R-2026-100' not in html

    def test_invoice_detail_blocked_for_other_org(self, client, admin_user, org_a_data, org_b_data):
        """Zugriff auf Rechnung aus anderer Organisation wird blockiert."""
        login(client, 'admin_test', 'SecurePass123!')
        other_invoice_id = org_b_data['invoice'].id
        response = client.get(f'/billing/{other_invoice_id}')
        assert response.status_code in (403, 404)


class TestSearchIsolation:
    """Suche gibt nur Ergebnisse der eigenen Organisation zurueck."""

    def test_patient_api_search_only_own_org(self, client, admin_user, org_a_data, org_b_data):
        """Patienten-Suche (API) gibt nur eigene Patienten zurueck."""
        login(client, 'admin_test', 'SecurePass123!')
        response = client.get('/patients/api/search?q=Mueller')
        data = response.get_json()
        assert any('Mueller' in p.get('text', '') for p in data)

        response = client.get('/patients/api/search?q=Schmidt')
        data = response.get_json()
        assert len(data) == 0

    def test_patient_search_min_length(self, client, admin_user, org_a_data):
        """Suche mit weniger als 2 Zeichen gibt leere Liste zurueck."""
        login(client, 'admin_test', 'SecurePass123!')
        response = client.get('/patients/api/search?q=A')
        data = response.get_json()
        assert data == []


class TestAPIEndpointIsolation:
    """API-Endpoints filtern korrekt nach Organization."""

    def test_cross_org_appointment_move_blocked(self, client, admin_user, org_a_data, org_b_data):
        """Termin einer fremden Organisation kann nicht verschoben werden."""
        login(client, 'admin_test', 'SecurePass123!')
        other_appt_id = org_b_data['appointment'].id
        new_start = (datetime.now() + timedelta(days=3)).isoformat()
        response = client.put(
            f'/calendar/api/appointments/{other_appt_id}/move',
            json={'new_start_time': new_start},
            content_type='application/json',
        )
        assert response.status_code in (403, 404)

    def test_cross_org_patient_toggle_blocked(self, client, admin_user, org_a_data, org_b_data):
        """Patient einer fremden Organisation kann nicht deaktiviert werden."""
        login(client, 'admin_test', 'SecurePass123!')
        other_patient_id = org_b_data['patient'].id
        response = client.post(f'/patients/{other_patient_id}/toggle')
        assert response.status_code in (403, 404)
