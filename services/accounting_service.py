"""Service-Modul fuer die Finanzbuchhaltung"""
from datetime import datetime, date
from models import (db, Account, JournalEntry, JournalEntryLine, CreditorInvoice,
                    FixedAsset, CostCenter, PeriodLock, Invoice, Payment)


def get_next_entry_number(org_id):
    """Generiert die naechste Belegnummer"""
    year = date.today().year
    last = JournalEntry.query.filter_by(organization_id=org_id) \
        .filter(JournalEntry.entry_number.like(f'BU-{year}-%')) \
        .order_by(JournalEntry.id.desc()).first()
    if last and last.entry_number:
        try:
            num = int(last.entry_number.split('-')[-1]) + 1
        except (ValueError, IndexError):
            num = 1
    else:
        num = 1
    return f'BU-{year}-{num:04d}'


def is_period_locked(org_id, check_date):
    """Prueft ob eine Periode gesperrt ist"""
    # Jahressperre
    year_lock = PeriodLock.query.filter_by(
        organization_id=org_id, year=check_date.year, month=0
    ).first()
    if year_lock and year_lock.locked_at:
        return True
    # Monatssperre
    month_lock = PeriodLock.query.filter_by(
        organization_id=org_id, year=check_date.year, month=check_date.month
    ).first()
    if month_lock and month_lock.locked_at:
        return True
    return False


def get_account_balance(account_id, up_to_date=None):
    """Berechnet den Saldo eines Kontos"""
    account = Account.query.get(account_id)
    if not account:
        return 0.0

    query = JournalEntryLine.query.join(JournalEntry).filter(
        JournalEntryLine.account_id == account_id
    )
    if up_to_date:
        query = query.filter(JournalEntry.date <= up_to_date)

    lines = query.all()
    total_debit = sum(l.debit or 0 for l in lines)
    total_credit = sum(l.credit or 0 for l in lines)

    # Aktiven und Aufwand: Soll-Saldo (Debit - Credit)
    # Passiven, Eigenkapital, Ertrag: Haben-Saldo (Credit - Debit)
    if account.account_type in ('asset', 'expense'):
        return round(total_debit - total_credit, 2)
    else:
        return round(total_credit - total_debit, 2)


def create_journal_entry(org_id, entry_date, description, lines_data, source='manual',
                         source_id=None, reference=None, created_by_id=None):
    """Erstellt eine Buchung mit Validierung (Soll == Haben)

    lines_data: Liste von Dicts mit keys:
        account_id, debit, credit, vat_code, vat_amount, cost_center_id, description
    """
    if is_period_locked(org_id, entry_date):
        return None, 'Periode ist gesperrt. Keine Buchungen moeglich.'

    # Soll == Haben pruefen
    total_debit = sum(l.get('debit', 0) or 0 for l in lines_data)
    total_credit = sum(l.get('credit', 0) or 0 for l in lines_data)
    if round(total_debit, 2) != round(total_credit, 2):
        return None, f'Soll ({total_debit:.2f}) und Haben ({total_credit:.2f}) stimmen nicht ueberein.'

    entry = JournalEntry(
        organization_id=org_id,
        entry_number=reference or get_next_entry_number(org_id),
        date=entry_date,
        description=description,
        source=source,
        source_id=source_id,
        reference=reference,
        created_by_id=created_by_id
    )
    db.session.add(entry)
    db.session.flush()

    for ld in lines_data:
        line = JournalEntryLine(
            entry_id=entry.id,
            account_id=ld['account_id'],
            debit=ld.get('debit', 0) or 0,
            credit=ld.get('credit', 0) or 0,
            vat_code=ld.get('vat_code'),
            vat_amount=ld.get('vat_amount', 0) or 0,
            cost_center_id=ld.get('cost_center_id'),
            description=ld.get('description', '')
        )
        db.session.add(line)

    db.session.commit()
    return entry, None


def storno_entry(entry_id, created_by_id=None):
    """Erstellt eine Stornobuchung (Gegenbuchung)"""
    original = JournalEntry.query.get(entry_id)
    if not original:
        return None, 'Buchung nicht gefunden.'
    if original.is_storno:
        return None, 'Eine Stornobuchung kann nicht erneut storniert werden.'

    org_id = original.organization_id
    if is_period_locked(org_id, original.date):
        return None, 'Periode ist gesperrt.'

    storno = JournalEntry(
        organization_id=org_id,
        entry_number=get_next_entry_number(org_id),
        date=date.today(),
        description=f'STORNO: {original.description}',
        source='storno',
        source_id=original.id,
        is_storno=True,
        storno_of_id=original.id,
        created_by_id=created_by_id
    )
    db.session.add(storno)
    db.session.flush()

    # Gegenbuchung: Soll und Haben vertauschen
    for line in original.lines:
        storno_line = JournalEntryLine(
            entry_id=storno.id,
            account_id=line.account_id,
            debit=line.credit,
            credit=line.debit,
            vat_code=line.vat_code,
            vat_amount=-(line.vat_amount or 0),
            cost_center_id=line.cost_center_id,
            description=f'Storno: {line.description or ""}'
        )
        db.session.add(storno_line)

    db.session.commit()
    return storno, None


def book_invoice(invoice, org_id):
    """Bucht eine Rechnung automatisch: Debitoren an Ertrag"""
    # Debitorenkonto bestimmen (1100=Patienten, 1101=Versicherungen)
    if invoice.billing_model == 'tiers_payant':
        debitor_number = '1101'
    else:
        debitor_number = '1100'

    debitor_account = Account.query.filter_by(
        organization_id=org_id, account_number=debitor_number
    ).first()

    # Ertragskonto bestimmen
    ertrag_map = {'KVG': '3000', 'UVG': '3010', 'IVG': '3010', 'MVG': '3010'}
    ertrag_number = ertrag_map.get(invoice.billing_type, '3020')
    ertrag_account = Account.query.filter_by(
        organization_id=org_id, account_number=ertrag_number
    ).first()

    if not debitor_account or not ertrag_account:
        return None, 'Konten nicht gefunden.'

    lines = [
        {'account_id': debitor_account.id, 'debit': invoice.amount_total, 'credit': 0,
         'description': f'Rechnung {invoice.invoice_number}'},
        {'account_id': ertrag_account.id, 'debit': 0, 'credit': invoice.amount_total,
         'description': f'Rechnung {invoice.invoice_number}'}
    ]

    return create_journal_entry(
        org_id, invoice.created_at.date() if invoice.created_at else date.today(),
        f'Rechnung {invoice.invoice_number} - {invoice.patient.last_name if invoice.patient else ""}',
        lines, source='invoice', source_id=invoice.id
    )


def book_payment(payment, org_id, bank_account_number='1020'):
    """Bucht eine Zahlung automatisch: Bank an Debitoren"""
    invoice = Invoice.query.get(payment.invoice_id)
    if not invoice:
        return None, 'Rechnung nicht gefunden.'

    bank_account = Account.query.filter_by(
        organization_id=org_id, account_number=bank_account_number
    ).first()
    debitor_number = '1101' if invoice.billing_model == 'tiers_payant' else '1100'
    debitor_account = Account.query.filter_by(
        organization_id=org_id, account_number=debitor_number
    ).first()

    if not bank_account or not debitor_account:
        return None, 'Konten nicht gefunden.'

    lines = [
        {'account_id': bank_account.id, 'debit': payment.amount, 'credit': 0,
         'description': f'Zahlung Rechnung {invoice.invoice_number}'},
        {'account_id': debitor_account.id, 'debit': 0, 'credit': payment.amount,
         'description': f'Zahlung Rechnung {invoice.invoice_number}'}
    ]

    return create_journal_entry(
        org_id, payment.payment_date or date.today(),
        f'Zahlung {invoice.invoice_number}',
        lines, source='payment', source_id=payment.id
    )


def book_dunning_fee(dunning_record, org_id):
    """Bucht Mahngebuehr: Debitoren an uebriger Ertrag"""
    if not dunning_record.dunning_fee or dunning_record.dunning_fee <= 0:
        return None, 'Keine Mahngebuehr.'

    debitor_account = Account.query.filter_by(
        organization_id=org_id, account_number='1100'
    ).first()
    ertrag_account = Account.query.filter_by(
        organization_id=org_id, account_number='6700'
    ).first()

    if not debitor_account or not ertrag_account:
        return None, 'Konten nicht gefunden.'

    lines = [
        {'account_id': debitor_account.id, 'debit': dunning_record.dunning_fee, 'credit': 0,
         'description': f'Mahngebuehr Stufe {dunning_record.dunning_level}'},
        {'account_id': ertrag_account.id, 'debit': 0, 'credit': dunning_record.dunning_fee,
         'description': f'Mahngebuehr Stufe {dunning_record.dunning_level}'}
    ]

    return create_journal_entry(
        org_id, dunning_record.dunning_date or date.today(),
        f'Mahngebuehr Stufe {dunning_record.dunning_level}',
        lines, source='dunning', source_id=dunning_record.id
    )


def run_depreciation(org_id, depreciation_date=None, created_by_id=None):
    """Fuehrt Abschreibungslauf fuer alle aktiven Anlagen durch"""
    if depreciation_date is None:
        depreciation_date = date.today()

    assets = FixedAsset.query.filter_by(organization_id=org_id, is_active=True).all()
    entries = []

    for asset in assets:
        if not asset.account_id or not asset.depreciation_account_id:
            continue
        if asset.current_book_value <= 0:
            continue

        if not asset.useful_life_years or asset.useful_life_years <= 0:
            continue

        if asset.depreciation_method == 'linear':
            annual = asset.acquisition_value / asset.useful_life_years
        else:  # degressiv (doppelte lineare Rate)
            rate = 2.0 / asset.useful_life_years
            annual = asset.current_book_value * rate

        monthly = round(annual / 12, 2)
        if monthly <= 0:
            continue
        if monthly > asset.current_book_value:
            monthly = asset.current_book_value

        lines = [
            {'account_id': asset.depreciation_account_id, 'debit': monthly, 'credit': 0,
             'description': f'Abschreibung {asset.name}'},
            {'account_id': asset.account_id, 'debit': 0, 'credit': monthly,
             'description': f'Abschreibung {asset.name}'}
        ]

        entry, error = create_journal_entry(
            org_id, depreciation_date,
            f'Abschreibung {asset.name} ({asset.depreciation_method})',
            lines, source='depreciation', source_id=asset.id,
            created_by_id=created_by_id
        )
        if entry:
            asset.current_book_value = round(asset.current_book_value - monthly, 2)
            db.session.commit()
            entries.append(entry)

    return entries


def generate_balance_sheet(org_id, stichtag=None):
    """Generiert Bilanz zum Stichtag"""
    if stichtag is None:
        stichtag = date.today()

    accounts = Account.query.filter_by(organization_id=org_id, is_active=True).all()

    aktiven = []
    passiven = []
    total_aktiven = 0
    total_passiven = 0

    for acc in accounts:
        if acc.account_type not in ('asset', 'liability', 'equity'):
            continue
        balance = get_account_balance(acc.id, stichtag)
        if balance == 0:
            continue

        entry = {'number': acc.account_number, 'name': acc.name, 'balance': balance}

        if acc.account_type == 'asset':
            aktiven.append(entry)
            total_aktiven += balance
        else:
            passiven.append(entry)
            total_passiven += balance

    return {
        'stichtag': stichtag.isoformat(),
        'aktiven': sorted(aktiven, key=lambda x: x['number']),
        'passiven': sorted(passiven, key=lambda x: x['number']),
        'total_aktiven': round(total_aktiven, 2),
        'total_passiven': round(total_passiven, 2),
        'differenz': round(total_aktiven - total_passiven, 2)
    }


def generate_income_statement(org_id, von_datum=None, bis_datum=None):
    """Generiert Erfolgsrechnung fuer Zeitraum"""
    if bis_datum is None:
        bis_datum = date.today()
    if von_datum is None:
        von_datum = date(bis_datum.year, 1, 1)

    accounts = Account.query.filter_by(organization_id=org_id, is_active=True).all()

    ertraege = []
    aufwaende = []
    total_ertrag = 0
    total_aufwand = 0

    for acc in accounts:
        if acc.account_type not in ('income', 'expense'):
            continue

        # Nur Buchungen im Zeitraum berechnen
        lines = JournalEntryLine.query.join(JournalEntry).filter(
            JournalEntryLine.account_id == acc.id,
            JournalEntry.date >= von_datum,
            JournalEntry.date <= bis_datum
        ).all()

        total_debit = sum(l.debit or 0 for l in lines)
        total_credit = sum(l.credit or 0 for l in lines)

        if acc.account_type == 'income':
            balance = total_credit - total_debit
        else:
            balance = total_debit - total_credit

        if balance == 0:
            continue

        entry = {'number': acc.account_number, 'name': acc.name, 'balance': round(balance, 2)}

        if acc.account_type == 'income':
            ertraege.append(entry)
            total_ertrag += balance
        else:
            aufwaende.append(entry)
            total_aufwand += balance

    return {
        'von': von_datum.isoformat(),
        'bis': bis_datum.isoformat(),
        'ertraege': sorted(ertraege, key=lambda x: x['number']),
        'aufwaende': sorted(aufwaende, key=lambda x: x['number']),
        'total_ertrag': round(total_ertrag, 2),
        'total_aufwand': round(total_aufwand, 2),
        'gewinn_verlust': round(total_ertrag - total_aufwand, 2)
    }


def generate_vat_report(org_id, von_datum, bis_datum):
    """Generiert MwSt-Abrechnung fuer Zeitraum"""
    lines = JournalEntryLine.query.join(JournalEntry).filter(
        JournalEntry.organization_id == org_id,
        JournalEntry.date >= von_datum,
        JournalEntry.date <= bis_datum,
        JournalEntryLine.vat_code.isnot(None),
        JournalEntryLine.vat_code != ''
    ).all()

    umsatzsteuer = {}
    vorsteuer = 0

    for line in lines:
        vat_code = line.vat_code
        vat_amount = abs(line.vat_amount or 0)

        if vat_code == 'vorsteuer':
            vorsteuer += vat_amount
        elif vat_code in ('8.1', '3.8', '2.6'):
            umsatzsteuer.setdefault(vat_code, 0)
            umsatzsteuer[vat_code] += vat_amount

    total_umsatzsteuer = sum(umsatzsteuer.values())

    return {
        'von': von_datum.isoformat(),
        'bis': bis_datum.isoformat(),
        'umsatzsteuer': {k: round(v, 2) for k, v in umsatzsteuer.items()},
        'total_umsatzsteuer': round(total_umsatzsteuer, 2),
        'vorsteuer': round(vorsteuer, 2),
        'mwst_schuld': round(total_umsatzsteuer - vorsteuer, 2)
    }


def get_open_debtors(org_id):
    """Offene Debitoren mit Ageing"""
    today = date.today()
    invoices = Invoice.query.filter(
        Invoice.organization_id == org_id,
        Invoice.status.in_(['sent', 'overdue', 'partially_paid']),
        Invoice.amount_open > 0
    ).all()

    result = {'0_30': [], '31_60': [], '61_90': [], 'ueber_90': [],
              'total_0_30': 0, 'total_31_60': 0, 'total_61_90': 0, 'total_ueber_90': 0, 'total': 0}

    for inv in invoices:
        days = (today - (inv.due_date or inv.created_at.date())).days if inv.due_date else 0
        entry = {
            'rechnung_id': inv.id,
            'nummer': inv.invoice_number,
            'patient': f'{inv.patient.first_name} {inv.patient.last_name}' if inv.patient else '-',
            'betrag': inv.amount_open,
            'faellig_seit_tagen': max(0, days)
        }

        if days <= 30:
            result['0_30'].append(entry)
            result['total_0_30'] += inv.amount_open
        elif days <= 60:
            result['31_60'].append(entry)
            result['total_31_60'] += inv.amount_open
        elif days <= 90:
            result['61_90'].append(entry)
            result['total_61_90'] += inv.amount_open
        else:
            result['ueber_90'].append(entry)
            result['total_ueber_90'] += inv.amount_open

        result['total'] += inv.amount_open

    for k in ['total_0_30', 'total_31_60', 'total_61_90', 'total_ueber_90', 'total']:
        result[k] = round(result[k], 2)

    return result


def get_open_creditors(org_id):
    """Offene Kreditoren"""
    creditors = CreditorInvoice.query.filter(
        CreditorInvoice.organization_id == org_id,
        CreditorInvoice.status.in_(['open', 'approved'])
    ).order_by(CreditorInvoice.due_date).all()

    return [{
        'id': c.id,
        'lieferant': c.creditor_name or (c.contact.display_name if c.contact else '-'),
        'nummer': c.invoice_number,
        'betrag': c.amount,
        'faellig': c.due_date.isoformat() if c.due_date else '-',
        'status': c.status
    } for c in creditors]


def get_liquidity(org_id):
    """Aktuelle Liquiditaet (Summe Bankkonten + Kasse)"""
    liquid_accounts = Account.query.filter(
        Account.organization_id == org_id,
        Account.account_number.in_(['1000', '1020', '1021']),
        Account.is_active == True
    ).all()

    total = 0
    details = []
    for acc in liquid_accounts:
        balance = get_account_balance(acc.id)
        details.append({'konto': acc.account_number, 'name': acc.name, 'saldo': balance})
        total += balance

    return {'total': round(total, 2), 'konten': details}
