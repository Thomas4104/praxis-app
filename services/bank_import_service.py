"""Service fuer CAMT (ISO 20022) und VESR Bank-Import
Basierend auf Cenplex Utilities.Banking Logik:
- CAMT camt.054.001.02 bis .08 (XML)
- VESR/ESR .v11 Format (Legacy)
- Automatisches Payment-Matching via 27-Zeichen Referenznummer
"""
import re
import xml.etree.ElementTree as ET
from datetime import datetime, date
from decimal import Decimal
from models import (db, BankImport, BankImportLine, Invoice, Payment,
                    Account, BankAccount)
from services.accounting_service import create_journal_entry


# ============================================================
# CAMT XML Parser (ISO 20022 camt.054.001.02 - .08)
# ============================================================

# Namespace-Mapping fuer alle unterstuetzten Versionen
CAMT_NAMESPACES = {
    '02': 'urn:iso:std:iso:20022:tech:xsd:camt.054.001.02',
    '03': 'urn:iso:std:iso:20022:tech:xsd:camt.054.001.03',
    '04': 'urn:iso:std:iso:20022:tech:xsd:camt.054.001.04',
    '05': 'urn:iso:std:iso:20022:tech:xsd:camt.054.001.05',
    '06': 'urn:iso:std:iso:20022:tech:xsd:camt.054.001.06',
    '07': 'urn:iso:std:iso:20022:tech:xsd:camt.054.001.07',
    '08': 'urn:iso:std:iso:20022:tech:xsd:camt.054.001.08',
}

# camt.053 (Kontoauszug) Namespaces
CAMT053_NAMESPACES = {
    '02': 'urn:iso:std:iso:20022:tech:xsd:camt.053.001.02',
    '04': 'urn:iso:std:iso:20022:tech:xsd:camt.053.001.04',
    '08': 'urn:iso:std:iso:20022:tech:xsd:camt.053.001.08',
}


def detect_camt_version(xml_content):
    """Erkennt die CAMT-Version aus dem XML-Namespace"""
    # Alle bekannten Namespaces pruefen
    for version, ns in CAMT_NAMESPACES.items():
        if ns in xml_content:
            return f'camt.054.001.{version}', ns, '054'

    for version, ns in CAMT053_NAMESPACES.items():
        if ns in xml_content:
            return f'camt.053.001.{version}', ns, '053'

    return None, None, None


def parse_camt_xml(xml_content):
    """Parst eine CAMT XML-Datei und extrahiert Transaktionen

    Unterstuetzt camt.054.001.02-.08 und camt.053.001.02-.08
    Gibt Liste von Dicts zurueck mit: amount, date, valuta_date, reference,
    remittance_info, credit_debit, debtor_name, creditor_name, etc.
    """
    version, namespace, msg_type = detect_camt_version(xml_content)
    if not namespace:
        return [], None, 'Unbekanntes CAMT-Format. Unterstuetzt: camt.054.001.02-.08, camt.053.001.02-.08'

    ns = {'ns': namespace}
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as e:
        return [], None, f'XML-Parsing-Fehler: {str(e)}'

    transactions = []

    # camt.054: BkToCstmrDbtCdtNtfctn, camt.053: BkToCstmrStmt
    if msg_type == '054':
        main_tag = f'{{{namespace}}}BkToCstmrDbtCdtNtfctn'
        ntfctn_tag = 'Ntfctn'
    else:
        main_tag = f'{{{namespace}}}BkToCstmrStmt'
        ntfctn_tag = 'Stmt'

    main_elem = root.find(f'ns:{main_tag.split("}")[-1]}', ns)
    if main_elem is None:
        # Fallback: direkt unter Document suchen
        for child in root:
            tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
            if 'BkToCstmr' in tag:
                main_elem = child
                break

    if main_elem is None:
        return [], version, 'CAMT-Hauptelement nicht gefunden.'

    # Notifications/Statements durchlaufen
    for ntfctn in main_elem.findall(f'ns:{ntfctn_tag}', ns):
        # Konto-Informationen
        acct_elem = ntfctn.find('ns:Acct/ns:Id/ns:IBAN', ns)
        account_iban = acct_elem.text if acct_elem is not None else ''

        # Entries durchlaufen
        for entry in ntfctn.findall('ns:Ntry', ns):
            # Basis-Daten aus Entry
            entry_amt_elem = entry.find('ns:Amt', ns)
            entry_amount = Decimal(entry_amt_elem.text) if entry_amt_elem is not None else Decimal('0')

            cdt_dbt_elem = entry.find('ns:CdtDbtInd', ns)
            credit_debit = cdt_dbt_elem.text if cdt_dbt_elem is not None else 'CRDT'

            # Buchungsdatum
            bookg_dt = entry.find('ns:BookgDt/ns:Dt', ns)
            booking_date = _parse_date(bookg_dt.text) if bookg_dt is not None else None

            # Valuta-Datum
            val_dt = entry.find('ns:ValDt/ns:Dt', ns)
            valuta_date = _parse_date(val_dt.text) if val_dt is not None else booking_date

            # Entry-Referenz
            entry_ref_elem = entry.find('ns:NtryRef', ns)
            entry_ref = entry_ref_elem.text if entry_ref_elem is not None else ''

            # EntryDetails -> TxDtls durchlaufen
            has_tx_details = False
            for ntry_dtls in entry.findall('ns:NtryDtls', ns):
                for tx_dtls in ntry_dtls.findall('ns:TxDtls', ns):
                    has_tx_details = True
                    tx = _extract_transaction_details(tx_dtls, ns, booking_date, valuta_date,
                                                      credit_debit, entry_ref, account_iban)
                    transactions.append(tx)

            # Wenn keine TxDtls vorhanden, Entry selbst als Transaktion
            if not has_tx_details:
                # Remittance Info direkt am Entry
                rmtinf = _extract_remittance_info(entry, ns)
                transactions.append({
                    'amount': float(entry_amount),
                    'date': booking_date,
                    'valuta_date': valuta_date,
                    'credit_debit': credit_debit,
                    'reference': rmtinf.get('reference', ''),
                    'remittance_info': rmtinf.get('unstructured', ''),
                    'debtor_name': '',
                    'debtor_iban': '',
                    'creditor_name': '',
                    'creditor_iban': '',
                    'entry_reference': entry_ref,
                    'account_iban': account_iban,
                })

    return transactions, version, None


def _extract_transaction_details(tx_dtls, ns, booking_date, valuta_date,
                                  credit_debit, entry_ref, account_iban):
    """Extrahiert Details einer einzelnen Transaktion aus TxDtls"""
    # Betrag (aus AmtDtls oder uebergeordnetem Entry)
    amt_elem = tx_dtls.find('ns:AmtDtls/ns:TxAmt/ns:Amt', ns)
    if amt_elem is None:
        amt_elem = tx_dtls.find('ns:Amt', ns)
    amount = Decimal(amt_elem.text) if amt_elem is not None else Decimal('0')

    # Datum (aus RltdDts oder Fallback auf Entry-Datum)
    accpt_dt = tx_dtls.find('ns:RltdDts/ns:AccptncDtTm', ns)
    if accpt_dt is not None:
        tx_date = _parse_datetime(accpt_dt.text)
    else:
        tx_date = booking_date

    # CdtDbtInd auf Transaktionsebene (ueberschreibt Entry)
    tx_cdi = tx_dtls.find('ns:CdtDbtInd', ns)
    if tx_cdi is not None:
        credit_debit = tx_cdi.text

    # Debtor/Creditor
    dbtr_name = tx_dtls.find('ns:RltdPties/ns:Dbtr/ns:Nm', ns)
    dbtr_iban = tx_dtls.find('ns:RltdPties/ns:DbtrAcct/ns:Id/ns:IBAN', ns)
    cdtr_name = tx_dtls.find('ns:RltdPties/ns:Cdtr/ns:Nm', ns)
    cdtr_iban = tx_dtls.find('ns:RltdPties/ns:CdtrAcct/ns:Id/ns:IBAN', ns)

    # Remittance Info (Referenznummer)
    rmtinf = _extract_remittance_info(tx_dtls, ns)

    return {
        'amount': float(amount),
        'date': tx_date or booking_date,
        'valuta_date': valuta_date,
        'credit_debit': credit_debit,
        'reference': rmtinf.get('reference', ''),
        'remittance_info': rmtinf.get('unstructured', ''),
        'debtor_name': dbtr_name.text if dbtr_name is not None else '',
        'debtor_iban': dbtr_iban.text if dbtr_iban is not None else '',
        'creditor_name': cdtr_name.text if cdtr_name is not None else '',
        'creditor_iban': cdtr_iban.text if cdtr_iban is not None else '',
        'entry_reference': entry_ref,
        'account_iban': account_iban,
    }


def _extract_remittance_info(elem, ns):
    """Extrahiert Referenznummer aus RmtInf (strukturiert und unstrukturiert)"""
    result = {'reference': '', 'unstructured': ''}

    rmt_inf = elem.find('ns:RmtInf', ns)
    if rmt_inf is None:
        return result

    # Strukturierte Referenz (QR/ESR)
    strd = rmt_inf.find('ns:Strd/ns:CdtrRefInf/ns:Ref', ns)
    if strd is not None and strd.text:
        result['reference'] = strd.text.strip()
    else:
        # Alternativ: CdtrRefInf direkt unter Strd (aeltere Versionen)
        strd_alt = rmt_inf.find('ns:Strd/ns:CdtrRefInf/ns:CdtrRef', ns)
        if strd_alt is not None and strd_alt.text:
            result['reference'] = strd_alt.text.strip()

    # Unstrukturierte Referenz
    ustrd = rmt_inf.find('ns:Ustrd', ns)
    if ustrd is not None and ustrd.text:
        result['unstructured'] = ustrd.text.strip()
        # Wenn keine strukturierte Referenz, versuche aus Ustrd zu extrahieren
        if not result['reference']:
            ref_match = re.search(r'\b(\d{27})\b', ustrd.text)
            if ref_match:
                result['reference'] = ref_match.group(1)

    return result


# ============================================================
# VESR/ESR Parser (Legacy .v11 Format)
# ============================================================

def parse_vesr_file(content):
    """Parst eine VESR/ESR .v11 Datei (Schweizer Zahlungsformat)

    Format nach Cenplex VesrLine.cs:
    - Pos 0-2: TransactionType (001=Standard, 999/995=Total)
    - Pos 3-11: KontoNr (9 Zeichen)
    - Pos 12-37: Referenznummer (26 Zeichen)
    - Pos 39-48: Betrag (10 Zeichen, 2 Dezimalen)
    - Pos 65-70: Buchungsdatum1 (JJMMTT)
    - Pos 71-76: Buchungsdatum2 (JJMMTT)
    - Pos 87-92: Valuta-Datum (JJMMTT, optional)
    """
    transactions = []
    lines = content.strip().split('\n')

    for line in lines:
        line = line.strip()
        if len(line) < 65:
            continue

        tx_type = line[0:3]

        # Nur Standard-Transaktionen (001), keine Totalzeilen (999/995)
        if tx_type not in ('001', '002', '005', '006', '011'):
            continue

        try:
            konto_nr = line[3:12].strip()
            referenz = line[12:39].strip()
            betrag_str = line[39:49].strip()
            betrag = Decimal(betrag_str) / Decimal('100')  # Letzte 2 Stellen = Rappen

            # Buchungsdatum
            datum_str = line[65:71]
            booking_date = _parse_vesr_date(datum_str)

            # Valuta-Datum (optional, ab Position 87)
            valuta_date = None
            if len(line) >= 93:
                valuta_str = line[87:93].strip()
                if valuta_str and valuta_str != '000000':
                    valuta_date = _parse_vesr_date(valuta_str)

            transactions.append({
                'amount': float(betrag),
                'date': booking_date,
                'valuta_date': valuta_date or booking_date,
                'credit_debit': 'CRDT',  # VESR = Gutschrift-Anzeige
                'reference': referenz,
                'remittance_info': f'VESR Konto {konto_nr}',
                'debtor_name': '',
                'debtor_iban': '',
                'creditor_name': '',
                'creditor_iban': '',
                'entry_reference': konto_nr,
                'account_iban': '',
            })
        except (ValueError, IndexError):
            continue

    return transactions, None


# ============================================================
# Referenznummer-Validierung und Invoice-Matching
# ============================================================

def validate_reference(reference):
    """Validiert und dekodiert eine ESR/QR-Referenznummer (27 Zeichen)

    Cenplex-Format:
    Pos 0-1:   Praefix (2 Zeichen)
    Pos 2-6:   PatientId (5 Zeichen)
    Pos 7-11:  CostUnitId (5 Zeichen)
    Pos 12-16: CustomerId (5 Zeichen)
    Pos 17-25: InvoiceId (9 Zeichen)
    Pos 26:    Pruefziffer
    """
    if not reference:
        return None

    # Nur Ziffern behalten
    ref_clean = re.sub(r'\s+', '', reference)
    if len(ref_clean) < 20:
        return None

    try:
        # InvoiceId aus den letzten 9-10 Zeichen vor Pruefziffer extrahieren
        if len(ref_clean) == 27:
            invoice_id_str = ref_clean[17:26].lstrip('0')
        elif len(ref_clean) == 26:
            invoice_id_str = ref_clean[16:25].lstrip('0')
        else:
            # Versuche die letzten Ziffern als Invoice-ID
            invoice_id_str = ref_clean[-10:-1].lstrip('0')

        if invoice_id_str and invoice_id_str.isdigit():
            return int(invoice_id_str)
    except (ValueError, IndexError):
        pass

    return None


def match_transactions_to_invoices(transactions, org_id):
    """Ordnet Transaktionen automatisch Rechnungen zu

    Matching-Strategie (wie Cenplex VesrImportViewModel):
    1. Strukturierte Referenznummer -> Invoice-ID extrahieren
    2. Betrag + offener Betrag pruefen
    3. Konfidenz berechnen
    """
    results = []

    for tx in transactions:
        match_result = {
            'transaction': tx,
            'invoice': None,
            'match_type': 'none',
            'confidence': 0,
            'is_fully_paid': False,
            'overpayment': 0,
            'possible_invoices': [],
        }

        # 1. Nur Gutschriften (CRDT) als Zahlungen behandeln
        if tx.get('credit_debit') == 'DBIT':
            match_result['match_type'] = 'debit'
            results.append(match_result)
            continue

        amount = Decimal(str(tx['amount']))

        # 2. Referenznummer-Matching
        ref = tx.get('reference', '')
        invoice_id = validate_reference(ref)

        if invoice_id:
            invoice = Invoice.query.filter_by(
                id=invoice_id, organization_id=org_id
            ).first()

            if invoice and invoice.amount_open and invoice.amount_open > 0:
                open_amount = Decimal(str(invoice.amount_open))
                match_result['invoice'] = invoice
                match_result['match_type'] = 'auto'

                if amount >= open_amount:
                    match_result['is_fully_paid'] = True
                    match_result['overpayment'] = float(amount - open_amount)
                    match_result['confidence'] = 100
                else:
                    match_result['confidence'] = 90  # Teilzahlung

                results.append(match_result)
                continue

        # 3. Betrag-Matching als Fallback
        # Suche offene Rechnungen mit passendem Betrag
        possible = Invoice.query.filter(
            Invoice.organization_id == org_id,
            Invoice.status.in_(['sent', 'overdue', 'partially_paid']),
            Invoice.amount_open > 0
        ).all()

        exact_matches = []
        for inv in possible:
            open_amount = Decimal(str(inv.amount_open))
            if amount == open_amount:
                exact_matches.append(inv)
            elif abs(amount - open_amount) <= Decimal('0.05'):
                # Rundungsdifferenz (5 Rappen)
                exact_matches.append(inv)

        if len(exact_matches) == 1:
            match_result['invoice'] = exact_matches[0]
            match_result['match_type'] = 'auto'
            match_result['confidence'] = 70
            match_result['is_fully_paid'] = True
        elif len(exact_matches) > 1:
            match_result['possible_invoices'] = exact_matches
            match_result['match_type'] = 'manual_needed'
            match_result['confidence'] = 50

        # Wenn immer noch kein Match, alle offenen Rechnungen als Vorschlaege
        if not match_result['invoice'] and not match_result['possible_invoices']:
            match_result['possible_invoices'] = possible[:10]  # Max 10 Vorschlaege

        results.append(match_result)

    return results


# ============================================================
# Import-Workflow
# ============================================================

def process_import_file(file_content, file_name, org_id, user_id, bank_account_id=None):
    """Verarbeitet eine Import-Datei (CAMT oder VESR)

    Returns: (BankImport, error_message)
    """
    file_ext = file_name.rsplit('.', 1)[-1].lower() if '.' in file_name else ''

    if file_ext == 'xml':
        transactions, version, error = parse_camt_xml(file_content)
        file_type = 'camt'
    elif file_ext in ('v11', 'esr'):
        transactions, error = parse_vesr_file(file_content)
        version = 'VESR v11'
        file_type = 'vesr'
    else:
        return None, f'Nicht unterstuetztes Dateiformat: .{file_ext}. Erwartet: .xml (CAMT) oder .v11 (VESR)'

    if error:
        return None, error

    if not transactions:
        return None, 'Keine Transaktionen in der Datei gefunden.'

    # BankImport erstellen
    bank_import = BankImport(
        organization_id=org_id,
        file_name=file_name,
        file_type=file_type,
        camt_version=version,
        total_transactions=len(transactions),
        total_amount=sum(Decimal(str(t['amount'])) for t in transactions if t.get('credit_debit') == 'CRDT'),
        bank_account_id=bank_account_id,
        imported_by_id=user_id,
        status='pending'
    )
    db.session.add(bank_import)
    db.session.flush()

    # Matching durchfuehren
    match_results = match_transactions_to_invoices(transactions, org_id)

    matched = 0
    unmatched = 0

    for result in match_results:
        tx = result['transaction']
        line = BankImportLine(
            bank_import_id=bank_import.id,
            transaction_date=tx.get('date'),
            valuta_date=tx.get('valuta_date'),
            amount=Decimal(str(tx['amount'])),
            credit_debit=tx.get('credit_debit', 'CRDT'),
            reference_number=tx.get('reference', ''),
            remittance_info=tx.get('remittance_info', ''),
            debtor_name=tx.get('debtor_name', ''),
            debtor_iban=tx.get('debtor_iban', ''),
            creditor_name=tx.get('creditor_name', ''),
            creditor_iban=tx.get('creditor_iban', ''),
            entry_reference=tx.get('entry_reference', ''),
            match_type=result['match_type'],
            match_confidence=result['confidence'],
            is_fully_paid=result['is_fully_paid'],
            overpayment=Decimal(str(result['overpayment'])),
        )

        if result['invoice']:
            line.invoice_id = result['invoice'].id
            line.status = 'matched'
            matched += 1
        elif result['match_type'] == 'debit':
            line.status = 'skipped'
        else:
            line.status = 'unmatched'
            unmatched += 1

        db.session.add(line)

    bank_import.matched_count = matched
    bank_import.unmatched_count = unmatched
    if unmatched == 0 and matched > 0:
        bank_import.status = 'completed'
    elif matched > 0:
        bank_import.status = 'partially_matched'

    db.session.commit()
    return bank_import, None


def assign_line_to_invoice(line_id, invoice_id, org_id):
    """Manuelle Zuordnung einer Import-Zeile zu einer Rechnung"""
    line = BankImportLine.query.get(line_id)
    if not line:
        return None, 'Import-Zeile nicht gefunden.'

    # Org-Check ueber BankImport
    if line.bank_import.organization_id != org_id:
        return None, 'Keine Berechtigung.'

    invoice = Invoice.query.filter_by(id=invoice_id, organization_id=org_id).first()
    if not invoice:
        return None, 'Rechnung nicht gefunden.'

    amount = Decimal(str(line.amount))
    open_amount = Decimal(str(invoice.amount_open or 0))

    line.invoice_id = invoice.id
    line.match_type = 'manual'
    line.match_confidence = 100
    line.status = 'matched'

    if amount >= open_amount:
        line.is_fully_paid = True
        line.overpayment = amount - open_amount
    else:
        line.is_fully_paid = False

    # Import-Statistik aktualisieren
    bank_import = line.bank_import
    bank_import.matched_count = BankImportLine.query.filter_by(
        bank_import_id=bank_import.id, status='matched'
    ).count()
    bank_import.unmatched_count = BankImportLine.query.filter_by(
        bank_import_id=bank_import.id, status='unmatched'
    ).count()

    if bank_import.unmatched_count == 0:
        bank_import.status = 'completed'
    else:
        bank_import.status = 'partially_matched'

    db.session.commit()
    return line, None


def skip_line(line_id, org_id):
    """Import-Zeile ueberspringen"""
    line = BankImportLine.query.get(line_id)
    if not line or line.bank_import.organization_id != org_id:
        return None, 'Nicht gefunden.'

    line.status = 'skipped'

    # Statistik aktualisieren
    bank_import = line.bank_import
    bank_import.unmatched_count = BankImportLine.query.filter_by(
        bank_import_id=bank_import.id, status='unmatched'
    ).count()
    if bank_import.unmatched_count == 0:
        bank_import.status = 'completed'

    db.session.commit()
    return line, None


def book_import(import_id, org_id, user_id, bank_account_number='1020'):
    """Bucht alle zugeordneten Import-Zeilen

    Erstellt fuer jede gematchte Zeile:
    1. Payment-Eintrag
    2. Buchung: Bank an Debitoren
    3. Aktualisiert Rechnungsstatus
    """
    bank_import = BankImport.query.filter_by(id=import_id, organization_id=org_id).first()
    if not bank_import:
        return 0, 'Import nicht gefunden.'

    matched_lines = BankImportLine.query.filter_by(
        bank_import_id=import_id, status='matched'
    ).all()

    if not matched_lines:
        return 0, 'Keine zugeordneten Transaktionen zum Buchen.'

    bank_account = Account.query.filter_by(
        organization_id=org_id, account_number=bank_account_number
    ).first()

    booked_count = 0

    for line in matched_lines:
        if not line.invoice_id:
            continue

        invoice = Invoice.query.get(line.invoice_id)
        if not invoice:
            continue

        # Payment erstellen
        payment = Payment(
            invoice_id=invoice.id,
            amount=line.amount,
            payment_date=line.transaction_date or date.today(),
            payment_method='bank_transfer',
            reference=line.reference_number or line.entry_reference,
            source='camt_import' if bank_import.file_type == 'camt' else 'vesr_import',
            is_from_file=True,
            is_fully_payed=line.is_fully_paid,
            payed_too_much=line.overpayment > 0 if line.overpayment else False,
        )
        db.session.add(payment)
        db.session.flush()

        line.payment_id = payment.id

        # Rechnungsstatus aktualisieren
        invoice.amount_paid = (invoice.amount_paid or 0) + line.amount
        invoice.amount_open = (invoice.amount_total or 0) - (invoice.amount_paid or 0)
        if invoice.amount_open <= 0:
            invoice.status = 'paid'
            invoice.amount_open = 0
        else:
            invoice.status = 'partially_paid'

        # Buchung: Bank an Debitoren
        if bank_account:
            debitor_number = '1101' if invoice.billing_model == 'tiers_payant' else '1100'
            debitor_account = Account.query.filter_by(
                organization_id=org_id, account_number=debitor_number
            ).first()

            if debitor_account:
                lines_data = [
                    {'account_id': bank_account.id, 'debit': float(line.amount), 'credit': 0,
                     'description': f'CAMT-Import: Zahlung Rechnung {invoice.invoice_number}'},
                    {'account_id': debitor_account.id, 'debit': 0, 'credit': float(line.amount),
                     'description': f'CAMT-Import: Zahlung Rechnung {invoice.invoice_number}'}
                ]

                entry, error = create_journal_entry(
                    org_id,
                    line.transaction_date or date.today(),
                    f'Bank-Import: Zahlung {invoice.invoice_number}',
                    lines_data, source='bank_import', source_id=bank_import.id,
                    created_by_id=user_id
                )
                if entry:
                    line.journal_entry_id = entry.id

        line.status = 'booked'
        booked_count += 1

    bank_import.status = 'completed'
    db.session.commit()

    return booked_count, None


def get_import_history(org_id, limit=20):
    """Gibt die letzten Imports zurueck"""
    return BankImport.query.filter_by(organization_id=org_id) \
        .order_by(BankImport.import_date.desc()).limit(limit).all()


# ============================================================
# Hilfsfunktionen
# ============================================================

def _parse_date(date_str):
    """Parst ein ISO-Datum (YYYY-MM-DD)"""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str[:10], '%Y-%m-%d').date()
    except ValueError:
        return None


def _parse_datetime(dt_str):
    """Parst ein ISO-DateTime (YYYY-MM-DDTHH:MM:SS)"""
    if not dt_str:
        return None
    try:
        return datetime.strptime(dt_str[:10], '%Y-%m-%d').date()
    except ValueError:
        return None


def _parse_vesr_date(date_str):
    """Parst ein VESR-Datum (JJMMTT)"""
    if not date_str or len(date_str) != 6:
        return None
    try:
        year = 2000 + int(date_str[0:2])
        month = int(date_str[2:4])
        day = int(date_str[4:6])
        return date(year, month, day)
    except (ValueError, IndexError):
        return None
