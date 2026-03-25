"""
Feld-Level-Verschluesselung fuer sensible medizinische Daten.
Verwendet Fernet (AES-128-CBC mit HMAC-SHA256) aus der cryptography-Bibliothek.
"""
import os
import base64

import sqlalchemy.types as types
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


def _get_encryption_key():
    """Leitet den Verschluesselungsschluessel aus ENCRYPTION_KEY ab."""
    key = os.environ.get('ENCRYPTION_KEY', '')
    if not key:
        raise RuntimeError(
            'ENCRYPTION_KEY Umgebungsvariable muss gesetzt sein! '
            'Generieren: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
    # Falls der Key bereits ein gueltiger Fernet-Key ist, direkt verwenden
    try:
        Fernet(key.encode() if isinstance(key, str) else key)
        return key.encode() if isinstance(key, str) else key
    except (ValueError, Exception):
        pass
    # Ansonsten: Key ableiten via PBKDF2
    salt = os.environ.get('ENCRYPTION_SALT', 'omnia-praxis-default-salt').encode()
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480000,
    )
    derived = base64.urlsafe_b64encode(kdf.derive(key.encode()))
    return derived


_fernet = None


def _get_fernet():
    """Gibt die Fernet-Instanz zurueck (Singleton)."""
    global _fernet
    if _fernet is None:
        _fernet = Fernet(_get_encryption_key())
    return _fernet


def encrypt_value(plaintext):
    """Verschluesselt einen String. Gibt Base64-codierten Ciphertext zurueck."""
    if plaintext is None or plaintext == '':
        return plaintext
    if isinstance(plaintext, str):
        plaintext = plaintext.encode('utf-8')
    return _get_fernet().encrypt(plaintext).decode('utf-8')


def decrypt_value(ciphertext):
    """Entschluesselt einen Base64-codierten Ciphertext. Gibt String zurueck."""
    if ciphertext is None or ciphertext == '':
        return ciphertext
    try:
        if isinstance(ciphertext, str):
            ciphertext = ciphertext.encode('utf-8')
        return _get_fernet().decrypt(ciphertext).decode('utf-8')
    except InvalidToken:
        # Fallback: Wert ist moeglicherweise noch nicht verschluesselt
        if isinstance(ciphertext, bytes):
            return ciphertext.decode('utf-8', errors='replace')
        return ciphertext


class EncryptedString(types.TypeDecorator):
    """Transparente Verschluesselung fuer SQLAlchemy String-Spalten.

    Verwendung in models.py:
        ahv_number = db.Column(EncryptedString(), nullable=True)
    """
    impl = types.Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        """Wird aufgerufen beim Schreiben in die DB."""
        if value is not None and value != '':
            return encrypt_value(str(value))
        return value

    def process_result_value(self, value, dialect):
        """Wird aufgerufen beim Lesen aus der DB."""
        if value is not None and value != '':
            return decrypt_value(value)
        return value
