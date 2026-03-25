"""Tests fuer Feld-Level-Verschluesselung."""
import os
import pytest

# Setze gueltigen Fernet-Key fuer Tests
# Muss VOR dem Import der Verschluesselungs-Module gesetzt werden
os.environ['ENCRYPTION_KEY'] = 'dGVzdC1rZXktZm9yLXVuaXQtdGVzdHMtb25seQ=='


class TestEncryptDecrypt:
    """Grundlegende Verschluesselungs-Tests."""

    def test_encrypt_decrypt_roundtrip(self):
        """Verschluesseln und Entschluesseln ergibt den Originalwert."""
        # Fernet-Singleton zuruecksetzen fuer frischen Key
        import utils.encryption as enc
        enc._fernet = None

        from utils.encryption import encrypt_value, decrypt_value
        original = 'Sensible Patientendaten'
        encrypted = encrypt_value(original)
        assert encrypted != original
        assert encrypted is not None
        decrypted = decrypt_value(encrypted)
        assert decrypted == original

    def test_encrypt_none_returns_none(self):
        """None-Werte werden nicht verschluesselt."""
        from utils.encryption import encrypt_value
        assert encrypt_value(None) is None

    def test_encrypt_empty_returns_empty(self):
        """Leere Strings werden nicht verschluesselt."""
        from utils.encryption import encrypt_value
        assert encrypt_value('') == ''

    def test_decrypt_none_returns_none(self):
        """Entschluesselung von None gibt None zurueck."""
        from utils.encryption import decrypt_value
        assert decrypt_value(None) is None

    def test_decrypt_empty_returns_empty(self):
        """Entschluesselung eines leeren Strings gibt leeren String zurueck."""
        from utils.encryption import decrypt_value
        assert decrypt_value('') == ''

    def test_different_plaintexts_different_ciphertexts(self):
        """Verschiedene Klartexte erzeugen verschiedene Ciphertexte."""
        from utils.encryption import encrypt_value
        enc1 = encrypt_value('Wert A')
        enc2 = encrypt_value('Wert B')
        assert enc1 != enc2

    def test_same_plaintext_different_ciphertexts(self):
        """Gleicher Klartext erzeugt verschiedene Ciphertexte (Fernet-IV)."""
        from utils.encryption import encrypt_value
        enc1 = encrypt_value('Gleicher Wert')
        enc2 = encrypt_value('Gleicher Wert')
        # Fernet nutzt zufaellige IVs, daher unterschiedliche Ciphertexte
        assert enc1 != enc2

    def test_unicode_roundtrip(self):
        """Unicode-Zeichen (Umlaute, Sonderzeichen) werden korrekt behandelt."""
        from utils.encryption import encrypt_value, decrypt_value
        original = 'Müller-Schönegg Straße 42, Zürich'
        encrypted = encrypt_value(original)
        decrypted = decrypt_value(encrypted)
        assert decrypted == original


class TestEncryptedStringType:
    """Tests fuer den EncryptedString SQLAlchemy TypeDecorator."""

    def test_encrypted_string_type_exists(self):
        """EncryptedString TypeDecorator ist verfuegbar."""
        from utils.encryption import EncryptedString
        es = EncryptedString()
        assert es is not None

    def test_process_bind_param_encrypts(self):
        """process_bind_param verschluesselt den Wert."""
        from utils.encryption import EncryptedString, decrypt_value
        es = EncryptedString()
        encrypted = es.process_bind_param('Testwert', dialect=None)
        assert encrypted != 'Testwert'
        # Entschluesselung muss funktionieren
        assert decrypt_value(encrypted) == 'Testwert'

    def test_process_bind_param_none(self):
        """process_bind_param gibt None fuer None zurueck."""
        from utils.encryption import EncryptedString
        es = EncryptedString()
        assert es.process_bind_param(None, dialect=None) is None

    def test_process_result_value_decrypts(self):
        """process_result_value entschluesselt den Wert."""
        from utils.encryption import EncryptedString, encrypt_value
        es = EncryptedString()
        encrypted = encrypt_value('Testwert')
        decrypted = es.process_result_value(encrypted, dialect=None)
        assert decrypted == 'Testwert'


class TestPatientDataEncryption:
    """Tests fuer verschluesselte Patientenfelder in der Datenbank."""

    def test_ahv_number_encrypted_in_db(self, app, db, org):
        """AHV-Nummern werden verschluesselt in der DB gespeichert."""
        # Fuer diesen Test brauchen wir einen gueltigen Encryption-Key
        import utils.encryption as enc
        old_fernet = enc._fernet
        try:
            # Key setzen und Singleton zuruecksetzen
            os.environ['ENCRYPTION_KEY'] = 'dGVzdC1rZXktZm9yLXVuaXQtdGVzdHMtb25seQ=='
            enc._fernet = None

            from models import Patient
            with app.app_context():
                patient = Patient(
                    organization_id=org.id,
                    first_name='Test',
                    last_name='Verschluesselt',
                    date_of_birth=date(1990, 1, 1),
                    ahv_number='756.1234.5678.90',
                )
                db.session.add(patient)
                db.session.commit()

                # Ueber ORM lesen - soll entschluesselt sein
                p = db.session.get(Patient, patient.id)
                assert p.ahv_number == '756.1234.5678.90'

                # Direkt per SQL pruefen ob verschluesselt
                from sqlalchemy import text
                result = db.session.execute(
                    text('SELECT ahv_number FROM patients WHERE id = :id'),
                    {'id': patient.id}
                ).fetchone()

                raw_value = result[0]
                if raw_value:
                    # Falls EncryptedString aktiv ist, muss der Rohwert
                    # verschieden vom Klartext sein
                    assert raw_value != '756.1234.5678.90', \
                        'AHV-Nummer darf nicht im Klartext in der DB stehen'
        finally:
            enc._fernet = old_fernet

    def test_insurance_number_encrypted_in_db(self, app, db, org):
        """Versicherungsnummern werden verschluesselt in der DB gespeichert."""
        import utils.encryption as enc
        old_fernet = enc._fernet
        try:
            os.environ['ENCRYPTION_KEY'] = 'dGVzdC1rZXktZm9yLXVuaXQtdGVzdHMtb25seQ=='
            enc._fernet = None

            from models import Patient
            with app.app_context():
                patient = Patient(
                    organization_id=org.id,
                    first_name='Test',
                    last_name='Insurance',
                    date_of_birth=date(1990, 1, 1),
                    insurance_number='INS-12345-67890',
                )
                db.session.add(patient)
                db.session.commit()

                # ORM liest entschluesselt
                p = db.session.get(Patient, patient.id)
                assert p.insurance_number == 'INS-12345-67890'

                # Raw-SQL zeigt verschluesselten Wert
                from sqlalchemy import text
                result = db.session.execute(
                    text('SELECT insurance_number FROM patients WHERE id = :id'),
                    {'id': patient.id}
                ).fetchone()

                raw_value = result[0]
                if raw_value:
                    assert raw_value != 'INS-12345-67890', \
                        'Versicherungsnummer darf nicht im Klartext in der DB stehen'
        finally:
            enc._fernet = old_fernet


# Import fuer Datum in der Klasse
from datetime import date
