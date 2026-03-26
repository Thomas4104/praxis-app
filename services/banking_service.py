"""
CAMT-Banking-Import und VESR-Parser nach Cenplex-Vorbild.
Unterstuetzt CAMT.054 (Notification) XML-Dateien und VESR-Textdateien.
"""
import xml.etree.ElementTree as ET
from datetime import datetime, date
from decimal import Decimal
from models import db, Invoice, Payment


def parse_camt054(file_content):
    """
    Parst eine CAMT.054 XML-Datei (Bank-to-Customer Debit/Credit Notification).
    Unterstuetzt CAMT02-CAMT08 Namespaces.

    Returns: Liste von Payment-Dictionaries
    """
    # Verschiedene CAMT-Namespaces (Cenplex: Cam02-Cam08)
    namespaces = [
        'urn:iso:std:iso:20022:tech:xsd:camt.054.001.02',
        'urn:iso:std:iso:20022:tech:xsd:camt.054.001.04',
        'urn:iso:std:iso:20022:tech:xsd:camt.054.001.08',
    ]

    payments = []

    if isinstance(file_content, bytes):
        try:
            file_content = file_content.decode('utf-8')
        except UnicodeDecodeError:
            file_content = file_content.decode('latin-1')

    try:
        root = ET.fromstring(file_content)
    except ET.ParseError:
        return {'error': 'Ungueltige XML-Datei', 'payments': []}

    # Namespace erkennen
    ns = ''
    for namespace in namespaces:
        if namespace in root.tag or root.find(f'.//{{{namespace}}}Ntfctn') is not None:
            ns = f'{{{namespace}}}'
            break

    # Notifications durchgehen
    for ntfctn in root.iter(f'{ns}Ntfctn') if ns else root.iter('Ntfctn'):
        for entry in ntfctn.iter(f'{ns}Ntry') if ns else ntfctn.iter('Ntry'):
            payment = _parse_camt_entry(entry, ns)
            if payment:
                payments.append(payment)

    return {'error': None, 'payments': payments}


def _parse_camt_entry(entry, ns):
    """Parst einen einzelnen CAMT-Eintrag"""
    try:
        # Betrag
        amt_elem = entry.find(f'{ns}Amt') if ns else entry.find('Amt')
        amount = Decimal(amt_elem.text) if amt_elem is not None and amt_elem.text else Decimal('0')
        currency = amt_elem.get('Ccy', 'CHF') if amt_elem is not None else 'CHF'

        # Credit/Debit
        cdt_dbt = entry.find(f'{ns}CdtDbtInd') if ns else entry.find('CdtDbtInd')
        is_credit = cdt_dbt is not None and cdt_dbt.text == 'CRDT'

        if not is_credit:
            return None  # Nur Gutschriften (Zahlungseingaenge) beruecksichtigen

        # Buchungsdatum
        booking_date = None
        book_dt = entry.find(f'{ns}BookgDt/{ns}Dt') if ns else entry.find('.//BookgDt/Dt')
        if book_dt is not None and book_dt.text:
            try:
                booking_date = datetime.strptime(book_dt.text, '%Y-%m-%d').date()
            except ValueError:
                booking_date = date.today()

        # Valuta-Datum
        valuta_date = None
        val_dt = entry.find(f'{ns}ValDt/{ns}Dt') if ns else entry.find('.//ValDt/Dt')
        if val_dt is not None and val_dt.text:
            try:
                valuta_date = datetime.strptime(val_dt.text, '%Y-%m-%d').date()
            except ValueError:
                pass

        # Referenznummer (verschiedene Stellen moeglich)
        reference = ''
        # Strukturierte Referenz (QR-Referenz oder SCOR)
        for ref_path in [
            f'{ns}NtryDtls/{ns}TxDtls/{ns}RmtInf/{ns}Strd/{ns}CdtrRefInf/{ns}Ref',
            './/TxDtls//Strd//Ref',
            f'{ns}NtryDtls/{ns}TxDtls/{ns}Refs/{ns}EndToEndId',
            './/TxDtls//EndToEndId'
        ]:
            ref_elem = entry.find(ref_path) if ns and '{' in ref_path else entry.find(ref_path)
            if ref_elem is not None and ref_elem.text and ref_elem.text != 'NOTPROVIDED':
                reference = ref_elem.text.strip()
                break

        # Unstrukturierte Referenz als Fallback
        if not reference:
            ustrd = entry.find(f'{ns}NtryDtls/{ns}TxDtls/{ns}RmtInf/{ns}Ustrd') if ns else entry.find('.//Ustrd')
            if ustrd is not None and ustrd.text:
                reference = ustrd.text.strip()[:50]

        # Gegenseite (Name des Zahlers)
        debtor_name = ''
        dbtr = entry.find(f'{ns}NtryDtls/{ns}TxDtls/{ns}RltdPties/{ns}Dbtr/{ns}Nm') if ns else entry.find('.//Dbtr/Nm')
        if dbtr is not None and dbtr.text:
            debtor_name = dbtr.text.strip()

        return {
            'amount': float(amount),
            'currency': currency,
            'booking_date': booking_date or date.today(),
            'valuta_date': valuta_date,
            'reference': reference,
            'debtor_name': debtor_name,
            'is_from_file': True,
            'raw_reference': reference
        }
    except Exception:
        return None


def parse_vesr(file_content):
    """
    Parst eine VESR-Datei (Verguetungen mit Einzahlungsschein mit Referenznummer).
    Cenplex: VesrLine

    Format: Feste Zeichenpositionen pro Zeile
    """
    payments = []

    if isinstance(file_content, bytes):
        file_content = file_content.decode('latin-1')

    for line in file_content.strip().split('\n'):
        line = line.strip()
        if len(line) < 87:
            continue

        # Transaktionsart (Pos 0-2)
        transaction_type = line[0:3]

        # Kontrollsaetze ueberspringen
        if transaction_type in ('999', '995'):
            continue

        try:
            # Konto-Nummer (Pos 3-11)
            account_nr = line[3:12].strip()

            # Referenznummer (Pos 12-37, 26 Zeichen) - Cenplex VESR-Format
            reference = line[12:38].strip()

            # Betrag (Pos 39-48, 10 Zeichen, letzte 2 = Rappen)
            amount_raw = line[39:49].strip()
            amount = Decimal(amount_raw) / 100

            # Buchungsdatum (Pos 65-70, yyMMdd)
            booking_date_str = line[65:71]
            try:
                booking_date = datetime.strptime(booking_date_str, '%y%m%d').date()
            except ValueError:
                booking_date = date.today()

            # Valuta-Datum (Pos 87-92, yyMMdd)
            valuta_date = None
            if len(line) >= 93:
                try:
                    valuta_date = datetime.strptime(line[87:93], '%y%m%d').date()
                except ValueError:
                    pass

            payments.append({
                'amount': float(amount),
                'booking_date': booking_date,
                'valuta_date': valuta_date,
                'reference': reference,
                'account_nr': account_nr,
                'is_from_file': True,
                'raw_reference': reference
            })
        except (ValueError, IndexError):
            continue

    return {'error': None, 'payments': payments}


def match_payment_to_invoice(payment_data, organization_id):
    """
    Versucht eine Zahlung automatisch einer Rechnung zuzuordnen.
    Nutzt Referenznummer (VESR) oder Betrag-Matching.

    Cenplex: LoadPaymentInfos / InvoiceSelection
    """
    reference = payment_data.get('reference', '')
    amount = Decimal(str(payment_data.get('amount', 0)))

    # 1. Versuch: Referenznummer matchen
    if reference and len(reference) >= 20:
        # VESR-Format: Pos 17-25 = Invoice-ID (9 Zeichen)
        try:
            invoice_id_str = reference[17:26].lstrip('0')
            if invoice_id_str:
                invoice_id = int(invoice_id_str)
                invoice = Invoice.query.filter_by(
                    id=invoice_id,
                    organization_id=organization_id
                ).first()
                if invoice:
                    return {
                        'invoice': invoice,
                        'is_fully_payed': float(amount) >= float(invoice.amount_open or 0),
                        'payed_too_much': float(amount) > float(invoice.amount_total or 0),
                        'match_type': 'reference'
                    }
        except (ValueError, IndexError):
            pass

    # 2. Versuch: Referenznummer in invoice.reference_number suchen
    if reference:
        invoice = Invoice.query.filter_by(
            organization_id=organization_id,
            reference_number=reference
        ).first()
        if invoice:
            return {
                'invoice': invoice,
                'is_fully_payed': float(amount) >= float(invoice.amount_open or 0),
                'payed_too_much': float(amount) > float(invoice.amount_total or 0),
                'match_type': 'reference_number'
            }

    # 3. Versuch: Exakten Betrag matchen (offene Rechnungen)
    open_invoices = Invoice.query.filter(
        Invoice.organization_id == organization_id,
        Invoice.status.in_(['sent', 'reminded']),
        Invoice.amount_open > 0
    ).all()

    exact_matches = [inv for inv in open_invoices if abs(float(inv.amount_open or 0) - float(amount)) < 0.01]

    if len(exact_matches) == 1:
        return {
            'invoice': exact_matches[0],
            'is_fully_payed': True,
            'payed_too_much': False,
            'match_type': 'amount_exact'
        }

    # Kein eindeutiger Match
    return {
        'invoice': None,
        'possible_invoices': exact_matches[:5] if exact_matches else [],
        'match_type': 'none'
    }


def import_payments(file_content, file_type, organization_id):
    """
    Importiert Zahlungen aus einer Datei und ordnet sie Rechnungen zu.

    file_type: 'camt054' oder 'vesr'
    Returns: Zusammenfassung des Imports

    Hinweis: Nur zugeordnete Zahlungen werden in der DB gespeichert,
    da Payment.invoice_id NOT NULL ist. Nicht zugeordnete Zahlungen
    werden im Ergebnis als 'unmatched' zurueckgegeben.
    """
    # Datei parsen
    if file_type == 'camt054':
        result = parse_camt054(file_content)
    elif file_type == 'vesr':
        result = parse_vesr(file_content)
    else:
        return {'error': 'Unbekannter Dateityp', 'imported': 0, 'matched': 0, 'unmatched': 0}

    if result.get('error'):
        return {'error': result['error'], 'imported': 0, 'matched': 0, 'unmatched': 0}

    imported = 0
    matched = 0
    unmatched = 0
    details = []

    for payment_data in result['payments']:
        match = match_payment_to_invoice(payment_data, organization_id)

        invoice = match.get('invoice')

        if invoice:
            payment = Payment(
                invoice_id=invoice.id,
                amount=payment_data['amount'],
                payment_date=payment_data['booking_date'],
                payment_method='bank',
                payment_type=0,  # Bank
                reference=payment_data.get('reference', ''),
                source='import',
                is_from_file=True,
                is_fully_payed=match.get('is_fully_payed', False),
                payed_too_much=match.get('payed_too_much', False),
                notes=f"Import: {payment_data.get('debtor_name', '')}"
            )
            db.session.add(payment)
            # Rechnungsbetrag aktualisieren
            invoice.amount_paid = round(float(invoice.amount_paid or 0) + payment_data['amount'], 2)
            invoice.amount_open = round(float(invoice.amount_total or 0) - float(invoice.amount_paid or 0), 2)
            if invoice.amount_open <= 0:
                invoice.status = 'paid'
                invoice.paid_at = datetime.utcnow()
            matched += 1
            imported += 1
        else:
            # Nicht zugeordnete Zahlung kann nicht gespeichert werden (invoice_id NOT NULL)
            unmatched += 1

        details.append({
            'amount': payment_data['amount'],
            'reference': payment_data.get('reference', ''),
            'debtor': payment_data.get('debtor_name', ''),
            'booking_date': payment_data['booking_date'].strftime('%d.%m.%Y') if payment_data.get('booking_date') else '',
            'matched': invoice is not None,
            'invoice_number': invoice.invoice_number if invoice else None,
            'invoice_id': invoice.id if invoice else None,
            'match_type': match.get('match_type', 'none')
        })

    if matched > 0:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            return {'error': 'Datenbankfehler beim Speichern', 'imported': 0, 'matched': 0, 'unmatched': 0}

    return {
        'error': None,
        'imported': imported,
        'matched': matched,
        'unmatched': unmatched,
        'total_parsed': len(result['payments']),
        'details': details
    }
