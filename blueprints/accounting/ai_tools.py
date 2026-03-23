"""KI-Tools fuer den Finanzbuchhaltungs-Bereich"""
from datetime import datetime, date
from models import (db, Account, JournalEntry, JournalEntryLine, CreditorInvoice,
                    FixedAsset, CostCenter, Invoice)
from services.accounting_service import (
    create_journal_entry, get_account_balance, generate_balance_sheet,
    generate_income_statement, generate_vat_report, get_open_debtors,
    get_open_creditors, get_liquidity
)


ACCOUNTING_TOOLS = [
    {
        'name': 'buchung_erstellen',
        'description': 'Erstellt eine manuelle Buchung in der Finanzbuchhaltung. Soll muss gleich Haben sein.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'datum': {'type': 'string', 'description': 'Buchungsdatum (YYYY-MM-DD)'},
                'text': {'type': 'string', 'description': 'Buchungstext/Beschreibung'},
                'soll_konto': {'type': 'string', 'description': 'Soll-Kontonummer (z.B. 1020)'},
                'haben_konto': {'type': 'string', 'description': 'Haben-Kontonummer (z.B. 6000)'},
                'betrag': {'type': 'number', 'description': 'Buchungsbetrag in CHF'}
            },
            'required': ['datum', 'text', 'soll_konto', 'haben_konto', 'betrag']
        }
    },
    {
        'name': 'kontostand',
        'description': 'Zeigt den aktuellen Saldo eines Kontos an.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'konto_nummer': {'type': 'string', 'description': 'Kontonummer (z.B. 1020)'}
            },
            'required': ['konto_nummer']
        }
    },
    {
        'name': 'kontoauszug',
        'description': 'Zeigt alle Buchungen eines Kontos in einem Zeitraum an.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'konto_nummer': {'type': 'string', 'description': 'Kontonummer'},
                'von_datum': {'type': 'string', 'description': 'Von-Datum (YYYY-MM-DD)'},
                'bis_datum': {'type': 'string', 'description': 'Bis-Datum (YYYY-MM-DD)'}
            },
            'required': ['konto_nummer']
        }
    },
    {
        'name': 'bilanz_erstellen',
        'description': 'Erstellt eine Bilanz zum angegebenen Stichtag (Aktiven und Passiven).',
        'input_schema': {
            'type': 'object',
            'properties': {
                'stichtag': {'type': 'string', 'description': 'Stichtag (YYYY-MM-DD), Standard: heute'}
            },
            'required': []
        }
    },
    {
        'name': 'erfolgsrechnung',
        'description': 'Erstellt eine Erfolgsrechnung (Gewinn- und Verlustrechnung) fuer einen Zeitraum.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'von_datum': {'type': 'string', 'description': 'Von-Datum (YYYY-MM-DD)'},
                'bis_datum': {'type': 'string', 'description': 'Bis-Datum (YYYY-MM-DD)'}
            },
            'required': []
        }
    },
    {
        'name': 'offene_debitoren',
        'description': 'Zeigt alle offenen Debitoren mit Ageing-Report (Altersstruktur).',
        'input_schema': {
            'type': 'object',
            'properties': {},
            'required': []
        }
    },
    {
        'name': 'offene_kreditoren',
        'description': 'Zeigt alle offenen Kreditoren-Rechnungen.',
        'input_schema': {
            'type': 'object',
            'properties': {},
            'required': []
        }
    },
    {
        'name': 'mwst_abrechnung',
        'description': 'Generiert eine MwSt-Abrechnung fuer ein Quartal oder einen Zeitraum.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'quartal': {'type': 'integer', 'description': 'Quartal (1-4)'},
                'jahr': {'type': 'integer', 'description': 'Jahr'},
                'von_datum': {'type': 'string', 'description': 'Alternativ: Von-Datum (YYYY-MM-DD)'},
                'bis_datum': {'type': 'string', 'description': 'Alternativ: Bis-Datum (YYYY-MM-DD)'}
            },
            'required': []
        }
    },
    {
        'name': 'umsatz_monat',
        'description': 'Zeigt den Umsatz eines bestimmten Monats.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'monat': {'type': 'integer', 'description': 'Monat (1-12)'},
                'jahr': {'type': 'integer', 'description': 'Jahr'}
            },
            'required': ['monat', 'jahr']
        }
    },
    {
        'name': 'liquiditaet',
        'description': 'Zeigt die aktuelle Liquiditaet (Summe aller Bankkonten und Kasse).',
        'input_schema': {
            'type': 'object',
            'properties': {},
            'required': []
        }
    }
]


def _get_org_id():
    """Hilfsfunktion: Organisation-ID aus dem ersten Konto ermitteln"""
    from flask_login import current_user
    try:
        return current_user.organization_id
    except Exception:
        acc = Account.query.first()
        return acc.organization_id if acc else 1


def accounting_tool_executor(tool_name, tool_input):
    """Fuehrt KI-Tools fuer die Finanzbuchhaltung aus"""
    org_id = _get_org_id()

    if tool_name == 'buchung_erstellen':
        datum_str = tool_input.get('datum', date.today().isoformat())
        entry_date = datetime.strptime(datum_str, '%Y-%m-%d').date()
        text = tool_input.get('text', '')
        soll_nr = tool_input.get('soll_konto', '')
        haben_nr = tool_input.get('haben_konto', '')
        betrag = float(tool_input.get('betrag', 0))

        soll = Account.query.filter_by(organization_id=org_id, account_number=soll_nr).first()
        haben = Account.query.filter_by(organization_id=org_id, account_number=haben_nr).first()

        if not soll:
            return {'error': f'Soll-Konto {soll_nr} nicht gefunden.'}
        if not haben:
            return {'error': f'Haben-Konto {haben_nr} nicht gefunden.'}
        if betrag <= 0:
            return {'error': 'Betrag muss groesser als 0 sein.'}

        lines = [
            {'account_id': soll.id, 'debit': betrag, 'credit': 0},
            {'account_id': haben.id, 'debit': 0, 'credit': betrag}
        ]

        entry, error = create_journal_entry(org_id, entry_date, text, lines)
        if error:
            return {'error': error}
        return {
            'success': True,
            'buchung_id': entry.id,
            'belegnummer': entry.entry_number,
            'datum': entry.date.isoformat(),
            'beschreibung': entry.description,
            'betrag': betrag,
            'soll_konto': f'{soll.account_number} {soll.name}',
            'haben_konto': f'{haben.account_number} {haben.name}'
        }

    elif tool_name == 'kontostand':
        konto_nr = tool_input.get('konto_nummer', '')
        account = Account.query.filter_by(organization_id=org_id, account_number=konto_nr).first()
        if not account:
            return {'error': f'Konto {konto_nr} nicht gefunden.'}
        balance = get_account_balance(account.id)
        return {
            'konto': f'{account.account_number} {account.name}',
            'typ': account.account_type,
            'saldo': balance,
            'saldo_formatiert': f'CHF {balance:.2f}'
        }

    elif tool_name == 'kontoauszug':
        konto_nr = tool_input.get('konto_nummer', '')
        account = Account.query.filter_by(organization_id=org_id, account_number=konto_nr).first()
        if not account:
            return {'error': f'Konto {konto_nr} nicht gefunden.'}

        von_str = tool_input.get('von_datum', date(date.today().year, 1, 1).isoformat())
        bis_str = tool_input.get('bis_datum', date.today().isoformat())
        von = datetime.strptime(von_str, '%Y-%m-%d').date()
        bis = datetime.strptime(bis_str, '%Y-%m-%d').date()

        lines = JournalEntryLine.query.join(JournalEntry).filter(
            JournalEntryLine.account_id == account.id,
            JournalEntry.date >= von,
            JournalEntry.date <= bis
        ).order_by(JournalEntry.date).all()

        buchungen = []
        for line in lines:
            buchungen.append({
                'datum': line.entry.date.isoformat(),
                'beleg': line.entry.entry_number,
                'text': line.description or line.entry.description,
                'soll': line.debit or 0,
                'haben': line.credit or 0
            })

        return {
            'konto': f'{account.account_number} {account.name}',
            'zeitraum': f'{von_str} bis {bis_str}',
            'anzahl_buchungen': len(buchungen),
            'buchungen': buchungen[:50],
            'saldo': get_account_balance(account.id, bis)
        }

    elif tool_name == 'bilanz_erstellen':
        stichtag_str = tool_input.get('stichtag', date.today().isoformat())
        stichtag = datetime.strptime(stichtag_str, '%Y-%m-%d').date()
        return generate_balance_sheet(org_id, stichtag)

    elif tool_name == 'erfolgsrechnung':
        von_str = tool_input.get('von_datum')
        bis_str = tool_input.get('bis_datum')
        von = datetime.strptime(von_str, '%Y-%m-%d').date() if von_str else None
        bis = datetime.strptime(bis_str, '%Y-%m-%d').date() if bis_str else None
        return generate_income_statement(org_id, von, bis)

    elif tool_name == 'offene_debitoren':
        return get_open_debtors(org_id)

    elif tool_name == 'offene_kreditoren':
        creditors = get_open_creditors(org_id)
        total = sum(c['betrag'] for c in creditors)
        return {'anzahl': len(creditors), 'total': round(total, 2), 'kreditoren': creditors}

    elif tool_name == 'mwst_abrechnung':
        quartal = tool_input.get('quartal')
        jahr = tool_input.get('jahr', date.today().year)

        if tool_input.get('von_datum') and tool_input.get('bis_datum'):
            von = datetime.strptime(tool_input['von_datum'], '%Y-%m-%d').date()
            bis = datetime.strptime(tool_input['bis_datum'], '%Y-%m-%d').date()
        elif quartal:
            q = int(quartal)
            von = date(int(jahr), (q - 1) * 3 + 1, 1)
            if q == 4:
                bis = date(int(jahr), 12, 31)
            else:
                bis = date(int(jahr), q * 3 + 1, 1) - __import__('datetime').timedelta(days=1)
        else:
            von = date(int(jahr), 1, 1)
            bis = date(int(jahr), 12, 31)

        return generate_vat_report(org_id, von, bis)

    elif tool_name == 'umsatz_monat':
        monat = int(tool_input.get('monat', date.today().month))
        jahr = int(tool_input.get('jahr', date.today().year))
        von = date(jahr, monat, 1)
        if monat == 12:
            bis = date(jahr, 12, 31)
        else:
            bis = date(jahr, monat + 1, 1) - __import__('datetime').timedelta(days=1)

        result = generate_income_statement(org_id, von, bis)
        return {
            'monat': f'{monat}/{jahr}',
            'umsatz': result['total_ertrag'],
            'aufwand': result['total_aufwand'],
            'gewinn_verlust': result['gewinn_verlust']
        }

    elif tool_name == 'liquiditaet':
        return get_liquidity(org_id)

    return {'error': f'Unbekanntes Tool: {tool_name}'}
