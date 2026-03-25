"""Tests fuer Audit-Logging Compliance (DSG/DSGVO)."""
import pytest
from datetime import date
from tests.conftest import login


class TestAuditLogging:
    """Audit-Logging muss alle sicherheitsrelevanten Aktionen erfassen."""

    def test_login_creates_audit_log(self, client, admin_user, db):
        """Erfolgreicher Login muss geloggt werden."""
        from models import AuditLog
        login(client, 'admin_test', 'SecurePass123!')
        with client.application.app_context():
            logs = AuditLog.query.filter_by(action='login').all()
            assert len(logs) > 0, 'Login wurde nicht im Audit-Log erfasst'

    def test_failed_login_creates_audit_log(self, client, admin_user, db):
        """Fehlgeschlagener Login muss geloggt werden."""
        from models import AuditLog
        login(client, 'admin_test', 'falsches_passwort')
        with client.application.app_context():
            logs = AuditLog.query.filter_by(action='login_failed').all()
            assert len(logs) > 0, 'Fehlgeschlagener Login wurde nicht geloggt'

    def test_patient_access_logged(self, client, admin_user, db, org):
        """Patientenzugriff muss geloggt werden."""
        from models import Patient, AuditLog

        patient = Patient(
            organization_id=org.id,
            first_name='Test',
            last_name='AuditPatient',
            date_of_birth=date(1990, 1, 1),
        )
        db.session.add(patient)
        db.session.commit()
        patient_id = patient.id

        login(client, 'admin_test', 'SecurePass123!')
        client.get(f'/patients/{patient_id}')

        with client.application.app_context():
            logs = AuditLog.query.filter_by(
                entity_type='patient',
                entity_id=patient_id,
            ).all()
            assert len(logs) > 0, 'Patientenzugriff wurde nicht geloggt'

    def test_audit_log_contains_user_and_ip(self, client, admin_user, db):
        """Audit-Logs muessen User-ID und IP enthalten."""
        from models import AuditLog
        login(client, 'admin_test', 'SecurePass123!')
        with client.application.app_context():
            log = AuditLog.query.filter_by(action='login').first()
            if log:
                assert log.user_id is not None, 'User-ID fehlt im Audit-Log'
                assert log.ip_address is not None, 'IP-Adresse fehlt im Audit-Log'

    def test_audit_log_contains_role(self, client, admin_user, db):
        """Audit-Logs muessen die Benutzerrolle enthalten."""
        from models import AuditLog
        login(client, 'admin_test', 'SecurePass123!')
        with client.application.app_context():
            log = AuditLog.query.filter_by(action='login').first()
            if log:
                assert log.user_role is not None, 'Benutzerrolle fehlt im Audit-Log'

    def test_audit_log_has_integrity_hash(self, client, admin_user, db):
        """Audit-Logs muessen einen Integritaets-Hash haben."""
        from models import AuditLog
        login(client, 'admin_test', 'SecurePass123!')
        with client.application.app_context():
            log = AuditLog.query.filter_by(action='login').first()
            if log:
                assert log.integrity_hash is not None, 'Integritaets-Hash fehlt'
                assert len(log.integrity_hash) == 64, 'Hash muss SHA-256 sein (64 Zeichen)'


class TestSensitiveDataRedaction:
    """Sensible Felder muessen in Audit-Logs maskiert werden."""

    def test_ahv_number_redacted(self):
        """AHV-Nummern werden in Aenderungs-Logs maskiert."""
        from services.audit_service import _sanitize_changes
        changes = {
            'ahv_number': {'old': '756.1234.5678.90', 'new': '756.9876.5432.10'},
            'first_name': {'old': 'Alt', 'new': 'Neu'},
        }
        sanitized = _sanitize_changes(changes)
        assert sanitized['ahv_number']['old'] == '[REDACTED]'
        assert sanitized['ahv_number']['new'] == '[CHANGED]'
        # Nicht-sensitive Felder bleiben unveraendert
        assert sanitized['first_name']['old'] == 'Alt'
        assert sanitized['first_name']['new'] == 'Neu'

    def test_insurance_number_redacted(self):
        """Versicherungsnummern werden maskiert."""
        from services.audit_service import _sanitize_changes
        changes = {
            'insurance_number': {'old': 'INS-123', 'new': 'INS-456'},
        }
        sanitized = _sanitize_changes(changes)
        assert sanitized['insurance_number']['old'] == '[REDACTED]'

    def test_iban_redacted(self):
        """IBAN-Nummern werden maskiert."""
        from services.audit_service import _sanitize_changes
        changes = {
            'iban': {'old': 'CH93 0076 2011 6238 5295 7', 'new': 'CH12 3456 7890'},
        }
        sanitized = _sanitize_changes(changes)
        assert sanitized['iban']['old'] == '[REDACTED]'

    def test_password_hash_redacted(self):
        """Passwort-Hashes werden maskiert."""
        from services.audit_service import _sanitize_changes
        changes = {
            'password_hash': {'old': 'pbkdf2:sha256:...old', 'new': 'pbkdf2:sha256:...new'},
        }
        sanitized = _sanitize_changes(changes)
        assert sanitized['password_hash']['old'] == '[REDACTED]'

    def test_totp_secret_redacted(self):
        """TOTP-Secrets werden maskiert."""
        from services.audit_service import _sanitize_changes
        changes = {
            'totp_secret': {'old': None, 'new': 'JBSWY3DPEHPK3PXP'},
        }
        sanitized = _sanitize_changes(changes)
        assert sanitized['totp_secret']['new'] == '[CHANGED]'

    def test_non_sensitive_fields_unchanged(self):
        """Nicht-sensible Felder bleiben unveraendert."""
        from services.audit_service import _sanitize_changes
        changes = {
            'first_name': {'old': 'Hans', 'new': 'Peter'},
            'city': {'old': 'Zürich', 'new': 'Bern'},
            'phone': {'old': '+41 44 123', 'new': '+41 31 456'},
        }
        sanitized = _sanitize_changes(changes)
        assert sanitized['first_name']['old'] == 'Hans'
        assert sanitized['city']['new'] == 'Bern'
        assert sanitized['phone']['old'] == '+41 44 123'


class TestAuditServiceFunctions:
    """Tests fuer Audit-Service Hilfsfunktionen."""

    def test_compute_hmac_deterministic(self):
        """HMAC-Berechnung ist deterministisch."""
        from services.audit_service import _compute_hmac
        hash1 = _compute_hmac('test-data')
        hash2 = _compute_hmac('test-data')
        assert hash1 == hash2

    def test_compute_hmac_different_data(self):
        """Verschiedene Daten erzeugen verschiedene HMACs."""
        from services.audit_service import _compute_hmac
        hash1 = _compute_hmac('daten-a')
        hash2 = _compute_hmac('daten-b')
        assert hash1 != hash2

    def test_log_action_with_changes(self, app, db, org, admin_user):
        """log_action mit Aenderungen speichert sanitisierte Changes."""
        import json
        from flask_login import login_user
        from models import AuditLog
        from services.audit_service import log_action

        with app.test_request_context():
            login_user(admin_user)
            log_action(
                'update', 'patient', 1,
                changes={
                    'first_name': {'old': 'Alt', 'new': 'Neu'},
                    'ahv_number': {'old': '756.0000', 'new': '756.1111'},
                }
            )
            db.session.commit()

            log = AuditLog.query.filter_by(action='update', entity_type='patient').first()
            assert log is not None
            changes = json.loads(log.changes_json)
            assert changes['first_name']['old'] == 'Alt'
            assert changes['ahv_number']['old'] == '[REDACTED]'
