Du bist ein Data Security Test Engineer. Dein Auftrag: Tests fuer Datensicherheit und Compliance in /Users/thomasbalke/praxis-app schreiben.

WICHTIG: Lies zuerst models.py, billing_service.py, und audit_service.py um die tatsaechliche Implementierung zu verstehen.

Voraussetzung: /Users/thomasbalke/praxis-app/tests/conftest.py existiert bereits.

## Aufgabe 1: Billing-Integritaets-Tests
Erstelle: /Users/thomasbalke/praxis-app/tests/test_billing_integrity.py

Teste:
1. Versendete Rechnungen koennen nicht geaendert werden (Immutabilitaet)
2. Zahlungen koennen den offenen Betrag nicht uebersteigen
3. Zahlungsbetraege muessen positiv sein
4. Rechnungsnummern sind eindeutig pro Organisation
5. Stornierte Rechnungen koennen nicht reaktiviert werden

Passe die Tests an die tatsaechlichen Models und Routes an.

## Aufgabe 2: Verschluesselungs-Tests
Erstelle: /Users/thomasbalke/praxis-app/tests/test_encryption.py

```python
"""Tests fuer Feld-Level-Verschluesselung."""
import os
import pytest

# Setze Test-Encryption-Key
os.environ['ENCRYPTION_KEY'] = 'dGVzdC1rZXktZm9yLXVuaXQtdGVzdHMtb25seQ=='


class TestEncryption:
    def test_encrypt_decrypt_roundtrip(self):
        from utils.encryption import encrypt_value, decrypt_value
        original = 'Sensible Patientendaten'
        encrypted = encrypt_value(original)
        assert encrypted != original
        decrypted = decrypt_value(encrypted)
        assert decrypted == original

    def test_encrypt_none_returns_none(self):
        from utils.encryption import encrypt_value
        assert encrypt_value(None) is None

    def test_encrypt_empty_returns_empty(self):
        from utils.encryption import encrypt_value
        assert encrypt_value('') == ''

    def test_encrypted_string_type_decorator(self, app, db):
        """EncryptedString TypeDecorator verschluesselt in der DB."""
        # Diesen Test nur ausfuehren wenn EncryptedString vorhanden ist
        try:
            from utils.encryption import EncryptedString
        except ImportError:
            pytest.skip('EncryptedString nicht verfuegbar')

    def test_ahv_number_not_plaintext_in_db(self, app, db, org):
        """AHV-Nummern duerfen nicht im Klartext in der DB stehen."""
        from models import Patient
        from datetime import date
        with app.app_context():
            patient = Patient(
                organization_id=org.id,
                first_name='Test',
                last_name='Patient',
                date_of_birth=date(1990, 1, 1),
                ahv_number='756.1234.5678.90',
            )
            db.session.add(patient)
            db.session.commit()
            # Direkte DB-Abfrage sollte verschluesselten Wert zeigen
            # (abhaengig von EncryptedString Implementation)
```

## Aufgabe 3: Audit-Logging-Tests
Erstelle: /Users/thomasbalke/praxis-app/tests/test_audit.py

```python
"""Tests fuer Audit-Logging Compliance."""
import pytest
from tests.conftest import login


class TestAuditLogging:
    def test_login_creates_audit_log(self, client, admin_user, db):
        """Erfolgreicher Login muss geloggt werden."""
        from models import AuditLog
        login(client, 'admin_test', 'SecurePass123!')
        with client.application.app_context():
            logs = AuditLog.query.filter_by(action='login').all()
            assert len(logs) > 0

    def test_failed_login_creates_audit_log(self, client, admin_user, db):
        """Fehlgeschlagener Login muss geloggt werden."""
        from models import AuditLog
        login(client, 'admin_test', 'wrong')
        with client.application.app_context():
            logs = AuditLog.query.filter_by(action='login_failed').all()
            assert len(logs) > 0

    def test_patient_access_logged(self, client, admin_user, db, org):
        """Patientenzugriff muss geloggt werden."""
        from models import Patient, AuditLog
        from datetime import date
        patient = Patient(
            organization_id=org.id,
            first_name='Test',
            last_name='Patient',
            date_of_birth=date(1990, 1, 1),
        )
        db.session.add(patient)
        db.session.commit()

        login(client, 'admin_test', 'SecurePass123!')
        client.get(f'/patients/{patient.id}')

        with client.application.app_context():
            logs = AuditLog.query.filter_by(
                entity_type='patient',
                entity_id=patient.id,
            ).all()
            assert len(logs) > 0

    def test_audit_log_contains_user_and_ip(self, client, admin_user, db):
        """Audit-Logs muessen User-ID und IP enthalten."""
        from models import AuditLog
        login(client, 'admin_test', 'SecurePass123!')
        with client.application.app_context():
            log = AuditLog.query.filter_by(action='login').first()
            if log:
                assert log.user_id is not None
                assert log.ip_address is not None

    def test_sensitive_changes_redacted_in_audit(self, db, app):
        """Sensible Felder muessen in Audit-Logs maskiert sein."""
        from services.audit_service import _sanitize_changes
        changes = {
            'ahv_number': {'old': '756.1234.5678.90', 'new': '756.9876.5432.10'},
            'first_name': {'old': 'Alt', 'new': 'Neu'},
        }
        sanitized = _sanitize_changes(changes)
        assert sanitized['ahv_number']['old'] == '[REDACTED]'
        assert sanitized['first_name']['old'] == 'Alt'  # Nicht-sensitiv bleibt
```

## Aufgabe 4: SOAP-Versionierungs-Tests
Erstelle: /Users/thomasbalke/praxis-app/tests/test_soap_versioning.py

Teste:
1. SOAP-Aenderung erstellt History-Eintrag
2. History-Eintraege haben korrekte Versionsnummern
3. Content-Hash wird berechnet
4. Alte Versionen sind abrufbar

Passe an die tatsaechliche Implementierung an.

## Reihenfolge:
1. Lies models.py, billing_service.py, audit_service.py
2. Passe Tests an tatsaechliche Feld-Namen und Routen an
3. Erstelle Test-Dateien
4. Syntax-Checks
