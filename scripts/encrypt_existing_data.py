"""
Script zum Verschluesseln bestehender Daten in der Datenbank.
Ausfuehren: cd /Users/thomasbalke/praxis-app && python scripts/encrypt_existing_data.py

ACHTUNG: Backup erstellen bevor dieses Script ausgefuehrt wird!
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from models import db, Patient, Appointment, TreatmentSeries, BankAccount
from utils.encryption import encrypt_value, decrypt_value

app = create_app()

FIELDS_TO_ENCRYPT = {
    Patient: ['ahv_number', 'insurance_number'],
    BankAccount: ['iban', 'qr_iban'],
    Appointment: ['soap_subjective', 'soap_objective', 'soap_assessment', 'soap_plan'],
    TreatmentSeries: ['diagnosis_text', 'diagnosis_code'],
}


def is_already_encrypted(value):
    """Prueft ob ein Wert bereits verschluesselt ist (Fernet-Format)."""
    if not value:
        return False
    try:
        # Fernet-Tokens beginnen mit 'gAAAAA'
        return value.startswith('gAAAAA') and len(value) > 50
    except (AttributeError, TypeError):
        return False


def encrypt_existing():
    with app.app_context():
        for model, fields in FIELDS_TO_ENCRYPT.items():
            table_name = model.__tablename__
            print(f'\nVerschluessele {table_name}...')
            records = model.query.all()
            count = 0
            for record in records:
                changed = False
                for field in fields:
                    value = getattr(record, field, None)
                    if value and not is_already_encrypted(value):
                        # Direkt in die DB schreiben (umgeht TypeDecorator)
                        # Da EncryptedString jetzt aktiv ist, reicht ein einfaches setattr + commit
                        # Der TypeDecorator verschluesselt automatisch beim naechsten commit
                        setattr(record, field, value)
                        changed = True
                if changed:
                    count += 1
            if count > 0:
                db.session.commit()
                print(f'  {count} Datensaetze aktualisiert')
            else:
                print(f'  Keine unverschluesselten Daten gefunden')

    print('\nFertig!')


if __name__ == '__main__':
    if not os.environ.get('ENCRYPTION_KEY'):
        print('FEHLER: ENCRYPTION_KEY Umgebungsvariable muss gesetzt sein!')
        sys.exit(1)
    encrypt_existing()
