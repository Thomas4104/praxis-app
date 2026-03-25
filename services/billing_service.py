"""Billing-Service: Taxpunkt-Berechnung, Rechnungserstellung, QR-Rechnung"""
import io
import os
from datetime import date, datetime, timedelta
from models import (db, Invoice, InvoiceItem, Payment, TaxPointValue, BankAccount,
                    TreatmentSeries, TreatmentSeriesTemplate, Appointment,
                    Patient, InsuranceProvider, Organization, DunningRecord, SystemSetting)
from services.settings_service import get_setting


def get_tax_point_value(org_id, tariff_type, ref_date=None, canton=None, insurer_id=None):
    """Findet den passenden Taxpunktwert fuer einen Tariftyp"""
    if ref_date is None:
        ref_date = date.today()

    query = TaxPointValue.query.filter_by(
        organization_id=org_id,
        tariff_type=tariff_type
    ).filter(TaxPointValue.valid_from <= ref_date)

    if canton:
        query = query.filter(db.or_(TaxPointValue.canton == canton, TaxPointValue.canton.is_(None)))
    if insurer_id:
        query = query.filter(db.or_(TaxPointValue.insurer_id == insurer_id, TaxPointValue.insurer_id.is_(None)))

    # Optionaler valid_to-Filter
    query = query.filter(db.or_(TaxPointValue.valid_to.is_(None), TaxPointValue.valid_to >= ref_date))

    tpv = query.order_by(TaxPointValue.valid_from.desc()).first()
    return tpv.value if tpv else 1.0


def calculate_invoice_from_series(series_id, org_id):
    """Berechnet Rechnungspositionen aus einer Behandlungsserie"""
    series = TreatmentSeries.query.get(series_id)
    if not series:
        return None, 'Behandlungsserie nicht gefunden.'

    # Pruefen ob Serie bereits abgerechnet wurde
    existing = Invoice.query.filter_by(series_id=series_id).filter(
        Invoice.status.notin_(['cancelled'])
    ).first()
    if existing:
        return None, f'Serie wurde bereits abgerechnet (Rechnung {existing.invoice_number}).'

    template = series.template
    if not template:
        return None, 'Keine Serienvorlage gefunden.'

    # Abgeschlossene Termine zaehlen
    completed_count = Appointment.query.filter_by(
        series_id=series_id,
        status='completed'
    ).count()

    # Falls keine abgeschlossenen Termine, alle geplanten/durchgefuehrten zaehlen
    if completed_count == 0:
        completed_count = Appointment.query.filter(
            Appointment.series_id == series_id,
            Appointment.status.in_(['scheduled', 'completed'])
        ).count()

    if completed_count == 0:
        return None, 'Keine Termine in dieser Serie gefunden.'

    # Taxpunktwert ermitteln
    tariff_type = template.tariff_type or 'Tarif 312'
    tp_value = get_tax_point_value(org_id, tariff_type)

    # Taxpunkte aus Vorlage (Standardwerte fuer Physiotherapie)
    tariff_code = _get_tariff_code(tariff_type, template.duration_minutes)
    tax_points = _get_default_tax_points(tariff_type, template.duration_minutes)

    # MwSt-Satz: 0% fuer KVG/UVG/MVG/IVG, 8.1% fuer Privat
    vat_rate = 0.0
    if series.insurance_type in ('Privat', 'Selbstzahler'):
        vat_rate = 8.1

    amount_per_session = round(tax_points * tp_value, 2)
    total_amount = round(amount_per_session * completed_count, 2)
    vat_amount = round(total_amount * vat_rate / 100, 2)

    item = {
        'position': 1,
        'tariff_code': tariff_code,
        'description': f'{template.name} ({template.duration_minutes} Min.)',
        'quantity': completed_count,
        'tax_points': tax_points,
        'tax_point_value': tp_value,
        'amount': total_amount,
        'vat_rate': vat_rate,
        'vat_amount': vat_amount
    }

    return {
        'items': [item],
        'patient_id': series.patient_id,
        'insurance_provider_id': series.patient.insurance_provider_id if series.patient else None,
        'billing_type': series.insurance_type or 'KVG',
        'billing_model': series.billing_model or 'tiers_garant',
        'tax_point_value': tp_value,
        'amount_total': total_amount + vat_amount,
        'series': series
    }, None


def calculate_invoice_from_tariff_positions(series_id, org_id):
    """Berechnet Rechnungspositionen aus Tarmed-Positionen der Termine.

    Wenn Termine eigene Tarmed-Positionen haben, werden diese statt der
    Standard-Berechnung verwendet. Termine mit charge_despite_cancel=True
    werden ebenfalls beruecksichtigt.
    """
    from models import AppointmentTariffPosition

    series = TreatmentSeries.query.get(series_id)
    if not series or series.patient.organization_id != org_id:
        return None, 'Serie nicht gefunden'

    # Alle abrechnbaren Termine (completed + appeared + charge_despite_cancel)
    appointments = Appointment.query.filter(
        Appointment.series_id == series_id,
        db.or_(
            Appointment.status.in_(['completed', 'appeared']),
            Appointment.charge_despite_cancel == True
        )
    ).order_by(Appointment.start_time).all()

    if not appointments:
        return None, 'Keine abrechnbaren Termine gefunden'

    items = []
    position_nr = 0

    for appt in appointments:
        # Pruefen ob Tarmed-Positionen erfasst wurden
        tariff_positions = AppointmentTariffPosition.query.filter_by(
            appointment_id=appt.id
        ).order_by(AppointmentTariffPosition.position).all()

        if tariff_positions:
            # Verwende die manuell erfassten Tarmed-Positionen
            for tp in tariff_positions:
                position_nr += 1
                items.append({
                    'position': position_nr,
                    'tariff_type': tp.tariff_type,
                    'tariff_code': tp.tariff_code,
                    'description': tp.description or f'{tp.tariff_type} {tp.tariff_code}',
                    'quantity': float(tp.quantity),
                    'tax_points': float(tp.tax_points),
                    'tax_point_value': float(tp.tax_point_value),
                    'amount': float(tp.amount),
                    'vat_rate': float(tp.vat_rate or 0),
                    'vat_amount': float(tp.vat_amount or 0),
                    'appointment_id': appt.id,
                    'appointment_date': appt.start_time.strftime('%d.%m.%Y') if appt.start_time else '',
                    'is_termin_0': appt.is_termin_0,
                })
        else:
            # Fallback: Standard-Berechnung (wie bisher)
            position_nr += 1
            tariff_type = series.insurance_type or 'Tarif 590'
            duration = appt.duration_minutes or 30
            tp_val = get_tax_point_value(org_id, tariff_type)
            tax_points = _get_default_tax_points(tariff_type, duration)
            amount = round(tax_points * float(tp_val), 2)

            items.append({
                'position': position_nr,
                'tariff_type': tariff_type,
                'tariff_code': _get_tariff_code(tariff_type, duration),
                'description': f'Physiotherapie {duration} Min.',
                'quantity': 1,
                'tax_points': tax_points,
                'tax_point_value': float(tp_val),
                'amount': amount,
                'vat_rate': 0,
                'vat_amount': 0,
                'appointment_id': appt.id,
                'appointment_date': appt.start_time.strftime('%d.%m.%Y') if appt.start_time else '',
                'is_termin_0': appt.is_termin_0,
            })

    total = sum(item['amount'] + item['vat_amount'] for item in items)

    return {
        'items': items,
        'total': round(total, 2),
        'appointment_count': len(appointments),
        'has_tariff_positions': any(
            AppointmentTariffPosition.query.filter_by(appointment_id=a.id).first()
            for a in appointments
        ),
    }, None


def _get_tariff_code(tariff_type, duration_minutes):
    """Ermittelt die Tarifziffer basierend auf Tariftyp und Dauer"""
    codes = {
        ('TarReha', 30): '7301',
        ('TarReha', 45): '7302',
        ('TarReha', 60): '7303',
        ('Tarif 312', 30): '7301',
        ('Tarif 312', 45): '7302',
        ('Tarif 311', 30): '7311',
        ('Tarif 311', 45): '7312',
        ('Physiotarif', 30): '7301',
        ('Physiotarif', 45): '7302',
        ('Tarif 590', 30): '5901',
        ('Tarif 590', 45): '5902',
    }
    return codes.get((tariff_type, duration_minutes), '7301')


def _get_default_tax_points(tariff_type, duration_minutes):
    """Standard-Taxpunkte je nach Tarif und Dauer"""
    points = {
        ('TarReha', 30): 48.0,
        ('TarReha', 45): 72.0,
        ('TarReha', 60): 96.0,
        ('Tarif 312', 30): 48.0,
        ('Tarif 312', 45): 72.0,
        ('Tarif 311', 30): 48.0,
        ('Tarif 311', 45): 72.0,
        ('Physiotarif', 30): 60.0,
        ('Physiotarif', 45): 90.0,
        ('Tarif 590', 30): 60.0,
        ('Tarif 590', 45): 90.0,
    }
    return points.get((tariff_type, duration_minutes), 48.0)


def generate_invoice_number(org_id):
    """Thread-sichere Rechnungsnummer-Generierung mit DB-Lock."""
    fmt = get_setting(org_id, 'billing_invoice_format', 'RE-{JAHR}-{NR}')

    # SELECT ... FOR UPDATE verhindert Race-Conditions bei gleichzeitigen Anfragen
    setting = SystemSetting.query.filter_by(
        organization_id=org_id, key='billing_next_invoice_number'
    ).with_for_update().first()

    if not setting:
        setting = SystemSetting(
            organization_id=org_id,
            key='billing_next_invoice_number',
            value='1',
            value_type='integer',
            category='billing'
        )
        db.session.add(setting)
        db.session.flush()

    try:
        next_nr = int(setting.value)
    except (ValueError, TypeError):
        next_nr = 1

    # Nummer sofort inkrementieren (wird mit der Rechnung zusammen committed)
    setting.value = str(next_nr + 1)

    year = date.today().year
    invoice_number = fmt.replace('{JAHR}', str(year)).replace('{NR}', f'{next_nr:04d}')

    return invoice_number


def create_invoice_from_series(series_id, org_id, user_id=None):
    """Erstellt eine komplette Rechnung aus einer Behandlungsserie.

    Versucht zuerst die Berechnung ueber Tarmed-Positionen. Nur wenn das
    fehlschlaegt, wird die Standard-Berechnung verwendet.
    """
    # Zuerst versuchen: Tarmed-Positionen pro Termin
    tariff_result, tariff_error = calculate_invoice_from_tariff_positions(series_id, org_id)
    if tariff_result:
        # Tarmed-Positionen vorhanden, verwende diese als Basis
        result, error = calculate_invoice_from_series(series_id, org_id)
        if error:
            return None, error
        # Items aus Tarmed-Berechnung uebernehmen
        result['items'] = tariff_result['items']
        result['amount_total'] = tariff_result['total']
    else:
        # Fallback: Standard-Berechnung
        result, error = calculate_invoice_from_series(series_id, org_id)
    if error:
        return None, error

    payment_term = int(get_setting(org_id, 'billing_payment_term', '30') or 30)
    invoice_number = generate_invoice_number(org_id)

    invoice = Invoice(
        organization_id=org_id,
        series_id=series_id,
        patient_id=result['patient_id'],
        insurance_provider_id=result['insurance_provider_id'],
        invoice_number=invoice_number,
        amount_total=result['amount_total'],
        amount_paid=0.0,
        amount_open=result['amount_total'],
        status='draft',
        billing_type=result['billing_type'],
        billing_model=result['billing_model'],
        tax_point_value=result['tax_point_value'],
        due_date=date.today() + timedelta(days=payment_term)
    )
    db.session.add(invoice)
    db.session.flush()

    for item_data in result['items']:
        item = InvoiceItem(
            invoice_id=invoice.id,
            position=item_data['position'],
            tariff_code=item_data['tariff_code'],
            description=item_data['description'],
            quantity=item_data['quantity'],
            tax_points=item_data['tax_points'],
            tax_point_value=item_data['tax_point_value'],
            amount=item_data['amount'],
            vat_rate=item_data['vat_rate'],
            vat_amount=item_data['vat_amount']
        )
        db.session.add(item)

    db.session.commit()
    return invoice, None


def record_payment(invoice_id, amount, payment_date, payment_method, reference='', notes=''):
    """Verbucht eine Zahlung auf eine Rechnung mit umfassender Validierung"""
    invoice = Invoice.query.get(invoice_id)
    if not invoice:
        return None, 'Rechnung nicht gefunden.'

    # Validierung: Nur versendete/ueberfaellige/teilbezahlte Rechnungen
    if invoice.status not in ('sent', 'overdue', 'partially_paid'):
        return None, f'Zahlung nicht moeglich bei Status: {invoice.status}'

    # Validierung: Betrag muss positiv sein
    if not amount or amount <= 0:
        return None, 'Zahlungsbetrag muss groesser als 0 sein.'

    # Validierung: Keine Ueberzahlung (mit Toleranz fuer Rundung, 5 Rappen)
    max_payment = float(invoice.amount_open or 0) + 0.05
    if amount > max_payment:
        return None, (f'Zahlungsbetrag ({amount:.2f}) uebersteigt den '
                      f'offenen Betrag ({invoice.amount_open:.2f}).')

    # Zahlungsdatum parsen und validieren
    if isinstance(payment_date, str):
        try:
            payment_date = datetime.strptime(payment_date, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return None, 'Ungueltiges Zahlungsdatum.'

    # Zahlungsdatum darf nicht in der Zukunft liegen
    if payment_date and payment_date > date.today():
        return None, 'Zahlungsdatum darf nicht in der Zukunft liegen.'

    payment = Payment(
        invoice_id=invoice_id,
        amount=amount,
        payment_date=payment_date,
        payment_method=payment_method,
        reference=reference,
        notes=notes
    )
    db.session.add(payment)

    # Betraege aktualisieren
    invoice.amount_paid = round(float(invoice.amount_paid or 0) + float(amount), 2)
    invoice.amount_open = round(float(invoice.amount_total) - float(invoice.amount_paid), 2)

    # Status aktualisieren
    if invoice.amount_open <= 0:
        invoice.status = 'paid'
        invoice.paid_at = datetime.utcnow()
        invoice.amount_open = 0.0
    elif invoice.amount_paid > 0:
        invoice.status = 'partially_paid'

    db.session.commit()
    return payment, None


def process_dunning(invoice_id, org_id):
    """Fuehrt die naechste Mahnstufe fuer eine Rechnung aus"""
    invoice = Invoice.query.get(invoice_id)
    if not invoice:
        return None, 'Rechnung nicht gefunden.'

    if invoice.status in ('paid', 'cancelled', 'draft'):
        return None, 'Mahnung nur fuer offene/gesendete Rechnungen moeglich.'

    current_level = invoice.dunning_level or 0
    next_level = current_level + 1

    if next_level > 3:
        return None, 'Maximale Mahnstufe (3) bereits erreicht.'

    # Mahngebuehr und Text aus Einstellungen
    fee = float(get_setting(org_id, f'dunning_{next_level}_fee', '0') or 0)
    text = get_setting(org_id, f'dunning_{next_level}_text', f'Mahnung Stufe {next_level}')

    # Mahngebuehr nur bei Tiers Garant
    if invoice.billing_model != 'tiers_garant':
        fee = 0.0

    # Mahnungshistorie erstellen
    record = DunningRecord(
        invoice_id=invoice_id,
        dunning_level=next_level,
        dunning_date=date.today(),
        dunning_fee=fee,
        dunning_text=text,
        sent_via='print'
    )
    db.session.add(record)

    # Rechnung aktualisieren
    invoice.dunning_level = next_level
    if next_level == 1:
        invoice.dunning_1_date = date.today()
    elif next_level == 2:
        invoice.dunning_2_date = date.today()
    elif next_level == 3:
        invoice.dunning_3_date = date.today()

    # Mahngebuehr zum offenen Betrag addieren
    if fee > 0:
        invoice.amount_total = round(invoice.amount_total + fee, 2)
        invoice.amount_open = round(invoice.amount_open + fee, 2)

    invoice.status = 'overdue'
    db.session.commit()

    return record, None


def run_dunning_batch(org_id):
    """Automatischer Mahnlauf: Prueft alle offenen Rechnungen und mahnt faellige"""
    results = []

    for level in [1, 2, 3]:
        days_setting = f'dunning_{level}_days'
        days = int(get_setting(org_id, days_setting, str(level * 30)) or level * 30)
        cutoff_date = date.today() - timedelta(days=days)

        invoices = Invoice.query.filter(
            Invoice.organization_id == org_id,
            Invoice.status.in_(['sent', 'overdue', 'partially_paid']),
            Invoice.due_date <= cutoff_date,
            Invoice.dunning_level == level - 1,
            Invoice.amount_open > 0
        ).all()

        for inv in invoices:
            record, error = process_dunning(inv.id, org_id)
            if record:
                results.append({
                    'invoice_id': inv.id,
                    'invoice_number': inv.invoice_number,
                    'level': level,
                    'fee': record.dunning_fee
                })

    return results


def generate_qr_bill_data(invoice):
    """Generiert die Daten fuer einen Swiss QR-Einzahlungsschein"""
    org = Organization.query.get(invoice.organization_id)
    patient = Patient.query.get(invoice.patient_id) if invoice.patient_id else None
    bank = BankAccount.query.filter_by(
        organization_id=invoice.organization_id, is_default=True
    ).first()

    if not bank:
        bank = BankAccount.query.filter_by(organization_id=invoice.organization_id).first()

    if not bank:
        return None

    # QR-IBAN oder normales IBAN
    iban = bank.qr_iban or bank.iban

    # Strukturierte Referenz (26-stellig, basierend auf Rechnungsnummer)
    ref_digits = ''.join(filter(str.isdigit, invoice.invoice_number or '0'))
    ref_digits = ref_digits.ljust(26, '0')[:26]
    # Pruefsumme (Modulo 10 rekursiv) fuer QR-Referenz
    check_table = [0, 9, 4, 6, 8, 2, 7, 1, 3, 5]
    carry = 0
    for digit in ref_digits:
        carry = check_table[(carry + int(digit)) % 10]
    check_digit = (10 - carry) % 10
    reference = ref_digits + str(check_digit)

    qr_data = {
        'header': {
            'qr_type': 'SPC',
            'version': '0200',
            'coding': '1'
        },
        'creditor': {
            'iban': iban,
            'name': org.name if org else '',
            'address': org.address if org else '',
            'zip_code': org.zip_code if org else '',
            'city': org.city if org else '',
            'country': 'CH'
        },
        'amount': {
            'amount': f'{invoice.amount_open:.2f}',
            'currency': 'CHF'
        },
        'debtor': {
            'name': f'{patient.first_name} {patient.last_name}' if patient else '',
            'address': patient.address if patient else '',
            'zip_code': patient.zip_code if patient else '',
            'city': patient.city if patient else '',
            'country': 'CH'
        },
        'reference': {
            'type': 'QRR',
            'reference': reference
        },
        'additional_info': f'Rechnung {invoice.invoice_number}'
    }

    # QR-Payload als String (Swiss Payment Standard)
    payload_lines = [
        'SPC', '0200', '1',
        iban,
        'S', org.name if org else '', org.address if org else '', '', org.zip_code if org else '', org.city if org else '', 'CH',
        '', '', '', '', '', '', '',
        invoice.amount_open if invoice.amount_open else 0, 'CHF',
        'S',
        f'{patient.first_name} {patient.last_name}' if patient else '',
        patient.address if patient else '', '',
        patient.zip_code if patient else '',
        patient.city if patient else '', 'CH',
        'QRR', reference,
        f'Rechnung {invoice.invoice_number}',
        'EPD'
    ]
    qr_data['payload'] = '\n'.join(str(line) for line in payload_lines)

    return qr_data


def generate_invoice_pdf(invoice_id):
    """Generiert ein PDF fuer eine Rechnung mit QR-Einzahlungsschein"""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_RIGHT, TA_LEFT
    except ImportError:
        return None, 'ReportLab ist nicht installiert. Bitte installieren: pip install reportlab'

    invoice = Invoice.query.get(invoice_id)
    if not invoice:
        return None, 'Rechnung nicht gefunden.'

    org = Organization.query.get(invoice.organization_id)
    patient = Patient.query.get(invoice.patient_id) if invoice.patient_id else None
    items = InvoiceItem.query.filter_by(invoice_id=invoice_id).order_by(InvoiceItem.position).all()

    # PDF erstellen
    pdf_dir = os.path.join('static', 'invoices')
    os.makedirs(pdf_dir, exist_ok=True)
    pdf_filename = f'rechnung_{invoice.invoice_number}.pdf'
    pdf_path = os.path.join(pdf_dir, pdf_filename)

    doc = SimpleDocTemplate(pdf_path, pagesize=A4,
                            topMargin=20*mm, bottomMargin=20*mm,
                            leftMargin=20*mm, rightMargin=20*mm)

    styles = getSampleStyleSheet()
    style_normal = styles['Normal']
    style_heading = ParagraphStyle('Heading', parent=styles['Heading1'], fontSize=16, spaceAfter=6*mm)
    style_right = ParagraphStyle('Right', parent=style_normal, alignment=TA_RIGHT)
    style_small = ParagraphStyle('Small', parent=style_normal, fontSize=8, textColor=colors.grey)

    elements = []

    # Praxis-Header
    praxis_info = f"""<b>{org.name if org else 'Praxis'}</b><br/>
    {org.address if org else ''}, {org.zip_code if org else ''} {org.city if org else ''}<br/>
    Tel: {org.phone if org else ''} | E-Mail: {org.email if org else ''}<br/>
    ZSR: {org.zsr_number if org else ''} | GLN: {org.gln_number if org else ''}"""
    elements.append(Paragraph(praxis_info, style_normal))
    elements.append(Spacer(1, 15*mm))

    # Patientenadresse
    if patient:
        pat_info = f"""{patient.salutation or ''} {patient.first_name} {patient.last_name}<br/>
        {patient.address or ''}<br/>
        {patient.zip_code or ''} {patient.city or ''}"""
        elements.append(Paragraph(pat_info, style_normal))
    elements.append(Spacer(1, 10*mm))

    # Rechnungsinfo
    elements.append(Paragraph(f'Rechnung Nr. {invoice.invoice_number}', style_heading))

    info_data = [
        ['Rechnungsdatum:', invoice.created_at.strftime('%d.%m.%Y') if invoice.created_at else '-',
         'Fällig am:', invoice.due_date.strftime('%d.%m.%Y') if invoice.due_date else '-'],
    ]
    if invoice.insurance_provider:
        info_data.append(['Versicherung:', invoice.insurance_provider.name, 'Typ:', invoice.billing_type or '-'])
    info_data.append(['Abrechnungsmodell:', 'Tiers Garant' if invoice.billing_model == 'tiers_garant' else 'Tiers Payant', '', ''])

    info_table = Table(info_data, colWidths=[35*mm, 50*mm, 30*mm, 50*mm])
    info_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('FONT', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONT', (2, 0), (2, -1), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 8*mm))

    # Leistungstabelle
    header = ['Pos.', 'Tarifziffer', 'Beschreibung', 'Anzahl', 'TP', 'TP-Wert', 'Betrag CHF', 'MwSt %']
    table_data = [header]
    subtotal = 0.0
    total_vat = 0.0

    for item in items:
        table_data.append([
            str(item.position or ''),
            item.tariff_code or '',
            item.description or '',
            f'{item.quantity:.0f}' if item.quantity == int(item.quantity) else f'{item.quantity:.1f}',
            f'{item.tax_points:.1f}',
            f'{item.tax_point_value:.2f}',
            f'{item.amount:.2f}',
            f'{item.vat_rate:.1f}' if item.vat_rate else '0.0'
        ])
        subtotal += item.amount
        total_vat += item.vat_amount or 0

    col_widths = [12*mm, 20*mm, 50*mm, 15*mm, 15*mm, 18*mm, 22*mm, 18*mm]
    positions_table = Table(table_data, colWidths=col_widths)
    positions_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4a90d9')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (3, 0), (-1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dddddd')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(positions_table)
    elements.append(Spacer(1, 5*mm))

    # Summen
    sum_data = [
        ['', '', '', '', '', '', 'Subtotal:', f'CHF {subtotal:.2f}'],
    ]
    if total_vat > 0:
        sum_data.append(['', '', '', '', '', '', 'MwSt:', f'CHF {total_vat:.2f}'])
    sum_data.append(['', '', '', '', '', '', 'Total:', f'CHF {invoice.amount_total:.2f}'])
    if invoice.amount_paid > 0:
        sum_data.append(['', '', '', '', '', '', 'Bezahlt:', f'CHF {invoice.amount_paid:.2f}'])
        sum_data.append(['', '', '', '', '', '', 'Offen:', f'CHF {invoice.amount_open:.2f}'])

    sum_table = Table(sum_data, colWidths=col_widths)
    sum_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('FONT', (-2, -1), (-1, -1), 'Helvetica-Bold'),
        ('ALIGN', (-2, 0), (-1, -1), 'RIGHT'),
        ('LINEABOVE', (-2, -1), (-1, -1), 1, colors.black),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    elements.append(sum_table)
    elements.append(Spacer(1, 10*mm))

    # Zahlungshinweis
    payment_term = get_setting(invoice.organization_id, 'billing_payment_term', '30')
    elements.append(Paragraph(
        f'Zahlbar innert {payment_term} Tagen. Vielen Dank für Ihr Vertrauen.',
        style_normal
    ))
    elements.append(Spacer(1, 5*mm))

    # QR-Code generieren
    qr_data = generate_qr_bill_data(invoice)
    if qr_data and qr_data.get('payload'):
        try:
            import qrcode
            qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=3, border=2)
            qr.add_data(qr_data['payload'])
            qr.make(fit=True)
            qr_img = qr.make_image(fill_color='black', back_color='white')

            img_buffer = io.BytesIO()
            qr_img.save(img_buffer, format='PNG')
            img_buffer.seek(0)

            from reportlab.lib.utils import ImageReader
            qr_image = Image(img_buffer, width=46*mm, height=46*mm)
            elements.append(Spacer(1, 5*mm))
            elements.append(Paragraph('<b>QR-Einzahlungsschein</b>', style_normal))
            elements.append(Spacer(1, 2*mm))
            elements.append(qr_image)
        except ImportError:
            elements.append(Paragraph('<i>QR-Code: qrcode-Library nicht installiert</i>', style_small))

    # Footer
    elements.append(Spacer(1, 10*mm))
    footer_text = f'{org.name if org else ""} | {org.address if org else ""}, {org.zip_code if org else ""} {org.city if org else ""} | {org.phone if org else ""}'
    elements.append(Paragraph(footer_text, style_small))

    doc.build(elements)

    # Pfad in der Rechnung speichern
    invoice.pdf_path = pdf_path
    db.session.commit()

    return pdf_path, None
