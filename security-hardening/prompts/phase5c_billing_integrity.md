Du bist ein Financial Systems Security Experte. Dein Auftrag: Abrechnungs-Integritaet in /Users/thomasbalke/praxis-app sicherstellen.

WICHTIG: Lies IMMER zuerst die betroffenen Dateien KOMPLETT.

## Aufgabe 1: Rechnungs-Immutabilitaet
Datei: /Users/thomasbalke/praxis-app/blueprints/billing/routes.py

Finde die Route zum Bearbeiten/Hinzufuegen von Rechnungspositionen. Fuege eine Pruefung hinzu die verhindert, dass versendete Rechnungen geaendert werden:

```python
# Vor JEDER Mutation einer Rechnung:
IMMUTABLE_STATUSES = {'sent', 'paid', 'overdue', 'cancelled'}

if invoice.status in IMMUTABLE_STATUSES:
    flash('Versendete Rechnungen koennen nicht mehr geaendert werden. '
          'Erstellen Sie stattdessen eine Korrekturrechnung.', 'error')
    return redirect(url_for('billing.detail', id=invoice.id))
```

Wende diese Pruefung an auf:
- Positionen hinzufuegen
- Positionen aendern
- Positionen loeschen
- Rechnungsdaten aendern

## Aufgabe 2: Zahlungs-Validierung
Datei: /Users/thomasbalke/praxis-app/services/billing_service.py

Finde die record_payment() Funktion und fuege Validierung hinzu:

```python
def record_payment(invoice_id, amount, payment_date=None, method='bank_transfer', reference=''):
    invoice = Invoice.query.get(invoice_id)
    if not invoice:
        raise ValueError('Rechnung nicht gefunden')

    # Validierung: Nur versendete/ueberfaellige Rechnungen
    if invoice.status not in ('sent', 'overdue', 'partially_paid'):
        raise ValueError(f'Zahlung nicht moeglich bei Status: {invoice.status}')

    # Validierung: Betrag muss positiv sein
    if amount <= 0:
        raise ValueError('Zahlungsbetrag muss groesser als 0 sein')

    # Validierung: Keine Ueberzahlung (mit Toleranz fuer Rundung)
    max_payment = invoice.amount_open + 0.05  # 5 Rappen Toleranz
    if amount > max_payment:
        raise ValueError(
            f'Zahlungsbetrag ({amount:.2f}) uebersteigt den offenen Betrag ({invoice.amount_open:.2f})'
        )

    # Zahlungsdatum darf nicht in der Zukunft liegen
    from datetime import date
    if payment_date and payment_date > date.today():
        raise ValueError('Zahlungsdatum darf nicht in der Zukunft liegen')

    # ... Rest der bestehenden Logik ...
```

## Aufgabe 3: Float durch Decimal ersetzen
Datei: /Users/thomasbalke/praxis-app/models.py

Finde das Invoice Model und aendere die Geldbetrags-Felder:
```python
from decimal import Decimal
# oder besser: SQLAlchemy Numeric Type

# Aendere in Invoice:
amount_total = db.Column(db.Numeric(10, 2), default=0)  # statt Float
amount_paid = db.Column(db.Numeric(10, 2), default=0)
amount_open = db.Column(db.Numeric(10, 2), default=0)

# Aendere in InvoiceItem:
quantity = db.Column(db.Numeric(10, 2), default=1)
tax_points = db.Column(db.Numeric(10, 2), default=0)
tp_value = db.Column(db.Numeric(10, 4), default=0)
amount = db.Column(db.Numeric(10, 2), default=0)
vat_rate = db.Column(db.Numeric(5, 2), default=0)
vat_amount = db.Column(db.Numeric(10, 2), default=0)

# Aendere in Payment:
amount = db.Column(db.Numeric(10, 2), nullable=False)
```

ACHTUNG: Suche ALLE Float-Felder die Geldbetraege darstellen und stelle sie um.
Pruefe auch: DunningRecord (fees), EmployeeSalary, Payslip, Expense, etc.

## Aufgabe 4: Rechnungsnummer Race-Condition fixen
Datei: /Users/thomasbalke/praxis-app/services/billing_service.py

Finde die Funktion die Rechnungsnummern generiert und fuege eine DB-Lock hinzu:

```python
from sqlalchemy import func

def generate_invoice_number(org_id):
    """Thread-sichere Rechnungsnummer-Generierung."""
    # Lock auf die Setting-Zeile setzen
    setting = SystemSetting.query.filter_by(
        organization_id=org_id,
        key='billing_next_invoice_number'
    ).with_for_update().first()  # SELECT ... FOR UPDATE

    if not setting:
        setting = SystemSetting(
            organization_id=org_id,
            key='billing_next_invoice_number',
            value='1'
        )
        db.session.add(setting)

    next_nr = int(setting.value)
    setting.value = str(next_nr + 1)
    # KEIN commit hier - wird mit der Rechnung zusammen committed

    year = datetime.utcnow().year
    return f'RE-{year}-{next_nr:05d}'
```

## Aufgabe 5: Audit-Logging fuer alle Billing-Operationen
Stelle sicher (nach Phase 5a), dass JEDE Billing-Operation geloggt wird:

```python
from services.audit_service import log_action

# Bei Rechnungserstellung:
log_action('create', 'invoice', invoice.id, changes={
    'invoice_number': {'new': invoice.invoice_number},
    'amount_total': {'new': str(invoice.amount_total)},
    'patient_id': {'new': invoice.patient_id},
})

# Bei Zahlungserfassung:
log_action('create', 'payment', payment.id, changes={
    'invoice_id': {'new': invoice.id},
    'amount': {'new': str(amount)},
    'method': {'new': method},
})

# Bei Mahnung:
log_action('create', 'dunning', invoice.id, changes={
    'dunning_level': {'new': next_level},
    'fee': {'new': str(fee)},
})
```

## Reihenfolge:
1. Lies billing/routes.py, billing_service.py, models.py (Invoice, InvoiceItem, Payment) KOMPLETT
2. Implementiere Immutabilitaet
3. Implementiere Zahlungs-Validierung
4. Stelle Float auf Numeric um
5. Fixe Race-Condition
6. Fuege Audit-Logging hinzu
7. Syntax-Checks fuer ALLE geaenderten Dateien
