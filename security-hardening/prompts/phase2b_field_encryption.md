Du bist ein Datenbank-Sicherheitsexperte. Dein Auftrag: Sensible Felder in /Users/thomasbalke/praxis-app/models.py mit Verschluesselung schuetzen.

VORAUSSETZUNG: /Users/thomasbalke/praxis-app/utils/encryption.py existiert bereits mit EncryptedString TypeDecorator.

WICHTIG: Lies IMMER zuerst models.py KOMPLETT, bevor du Aenderungen machst.

## Aufgabe 1: Import hinzufuegen
Datei: /Users/thomasbalke/praxis-app/models.py

Fuege am Anfang der Datei hinzu:
```python
from utils.encryption import EncryptedString
```

## Aufgabe 2: Sensible Felder auf EncryptedString umstellen
Aendere folgende Felder von `db.Column(db.String(...))` zu `db.Column(EncryptedString())`:

### Patient Model:
- `ahv_number` - AHV-Nummer (Sozialversicherung)
- `insurance_number` - Versicherungsnummer
- `notes` - Klinische Notizen (nur wenn es ein kurzes Textfeld ist, nicht wenn es db.Text ist und sehr lang sein kann)

### BankAccount Model:
- `iban` - IBAN
- `qr_iban` - QR-IBAN

### Appointment Model (SOAP-Noten):
- `soap_subjective` - Subjektive Beschwerden
- `soap_objective` - Objektiver Befund
- `soap_assessment` - Beurteilung
- `soap_plan` - Behandlungsplan

### TreatmentSeries Model:
- `diagnosis_text` - Diagnosetext
- `diagnosis_code` - Diagnosecode

ACHTUNG bei der Umstellung:
- EncryptedString() verwendet intern db.Text, daher String-Laengen-Constraints entfernen
- Wenn ein Feld als `db.Column(db.String(50))` definiert ist, wird es zu `db.Column(EncryptedString())`
- Wenn ein Feld bereits `db.Column(db.Text)` ist, wird es zu `db.Column(EncryptedString())`
- KEINE Felder umstellen die in Queries mit filter/filter_by verwendet werden (z.B. ahv_number wird nur angezeigt, nicht gesucht - OK)

## Aufgabe 3: Migration erstellen
Erstelle eine Alembic-Migration-Datei:
```bash
cd /Users/thomasbalke/praxis-app && python -c "
# Generiere Migrations-Hinweis
print('HINWEIS: Nach dem Aendern der Spaltentypen muss eine Migration erstellt werden:')
print('flask db migrate -m \"encrypt sensitive fields\"')
print('flask db upgrade')
print('')
print('ACHTUNG: Bestehende Daten muessen separat verschluesselt werden!')
print('Dafuer ein Migrations-Script erstellen das alle bestehenden Werte liest und verschluesselt zurueckschreibt.')
"
```

## Aufgabe 4: Daten-Migrations-Script erstellen
Erstelle: /Users/thomasbalke/praxis-app/scripts/encrypt_existing_data.py

```python
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
```

## Reihenfolge:
1. Lies models.py KOMPLETT (alle relevanten Models finden)
2. Fuege Import hinzu
3. Aendere die Felder einzeln und sorgfaeltig
4. Erstelle das Migrations-Script
5. Syntax-Check: python3 -c "import ast; ast.parse(open('/Users/thomasbalke/praxis-app/models.py').read())"
