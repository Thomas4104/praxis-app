# Abrechnungs-Routen: Rechnungen, Zahlungen, Mahnwesen, VESR-Import, PDF-Generierung

import io
import os
from datetime import datetime, date, timedelta
from flask import render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import login_required, current_user
from blueprints.billing import billing_bp
from models import (db, Invoice, InvoiceItem, Payment, Patient, TreatmentSeries,
                    Employee, InsuranceProvider, Doctor, TaxPointValue,
                    DunningConfig, Organization, Appointment)


@billing_bp.route('/')
@login_required
def index():
    """Rechnungsübersicht mit Status-Filter"""
    status_filter = request.args.get('status', '')
    search = request.args.get('search', '')

    query = Invoice.query.order_by(Invoice.created_at.desc())

    if status_filter:
        query = query.filter(Invoice.status == status_filter)
    if search:
        query = query.join(Patient).filter(
            db.or_(
                Patient.first_name.ilike(f'%{search}%'),
                Patient.last_name.ilike(f'%{search}%'),
                Invoice.invoice_number.ilike(f'%{search}%'),
            )
        )

    rechnungen = query.all()

    # Statistiken
    stats = {
        'total': Invoice.query.count(),
        'open': Invoice.query.filter(Invoice.status.in_(['open', 'sent', 'answered'])).count(),
        'overdue': sum(1 for r in Invoice.query.filter(
            Invoice.status.in_(['open', 'sent', 'answered', 'partially_paid']),
            Invoice.due_date < date.today()
        ).all()),
        'paid': Invoice.query.filter_by(status='paid').count(),
    }

    return render_template('billing/index.html',
                           rechnungen=rechnungen,
                           stats=stats,
                           status_filter=status_filter,
                           search=search)


@billing_bp.route('/neu', methods=['GET', 'POST'])
@login_required
def create():
    """Rechnung erstellen aus Behandlungsserie"""
    if request.method == 'POST':
        series_id = request.form.get('series_id', type=int)
        if not series_id:
            flash('Bitte eine Behandlungsserie auswählen.', 'error')
            return redirect(url_for('billing.create'))

        serie = TreatmentSeries.query.get_or_404(series_id)
        patient = Patient.query.get(serie.patient_id)

        # Rechnung erstellen
        invoice = Invoice(
            invoice_number=Invoice.generate_invoice_number(),
            series_id=serie.id,
            patient_id=patient.id,
            insurance_provider_id=patient.insurance_provider_id,
            therapist_id=serie.therapist_id,
            doctor_id=serie.prescribing_doctor_id,
            billing_type=serie.insurance_type or 'KVG',
            billing_model=serie.billing_model or 'tiers_garant',
            tariff_type=serie.template.tariff_type if serie.template else '312',
            due_date=date.today() + timedelta(days=30),
        )
        db.session.add(invoice)
        db.session.flush()

        # Positionen aus abgeschlossenen Terminen erstellen
        tariff_type = serie.template.tariff_type if serie.template else '312'
        tp_value = TaxPointValue.get_value(tariff_type, 'ZH', patient.insurance_provider_id)
        duration = serie.template.duration_minutes if serie.template else 30

        # Taxpunkte pro Position berechnen (basierend auf Dauer)
        tax_points = _calculate_tax_points(tariff_type, duration)

        completed_appointments = serie.appointments.filter_by(status='completed').all()
        if not completed_appointments:
            # Auch geplante Termine als Positionen nehmen (falls keine abgeschlossenen)
            completed_appointments = serie.appointments.filter(
                Appointment.status.in_(['completed', 'scheduled'])
            ).all()

        total = 0
        for i, appt in enumerate(completed_appointments):
            amount = round(tax_points * tp_value * 1, 2)  # quantity=1
            item = InvoiceItem(
                invoice_id=invoice.id,
                tariff_code=tariff_type,
                description=f'Behandlung {serie.template.name if serie.template else "Therapie"} ({duration} Min.)',
                quantity=1,
                tax_points=tax_points,
                tax_point_value=tp_value,
                amount=amount,
                appointment_id=appt.id,
                position=i + 1,
            )
            db.session.add(item)
            total += amount

        invoice.amount = round(total, 2)

        # QR-Referenz generieren
        invoice.qr_reference = _generate_qr_reference(invoice.id)

        db.session.commit()
        flash(f'Rechnung {invoice.invoice_number} über CHF {invoice.amount:.2f} erstellt.', 'success')
        return redirect(url_for('billing.detail', id=invoice.id))

    # GET: Serien zum Auswählen laden
    serien = TreatmentSeries.query.filter(
        TreatmentSeries.status.in_(['active', 'completed'])
    ).order_by(TreatmentSeries.created_at.desc()).all()

    return render_template('billing/form.html', serien=serien)


@billing_bp.route('/<int:id>')
@login_required
def detail(id):
    """Rechnungsdetails anzeigen"""
    rechnung = Invoice.query.get_or_404(id)
    positionen = rechnung.items.order_by(InvoiceItem.position).all()
    zahlungen = rechnung.payments.order_by(Payment.payment_date.desc()).all()
    return render_template('billing/detail.html',
                           rechnung=rechnung,
                           positionen=positionen,
                           zahlungen=zahlungen)


@billing_bp.route('/<int:id>/zahlung', methods=['POST'])
@login_required
def add_payment(id):
    """Zahlung verbuchen"""
    rechnung = Invoice.query.get_or_404(id)
    amount = request.form.get('amount', type=float)
    payment_date_str = request.form.get('payment_date', '')
    reference = request.form.get('reference', '')
    source = request.form.get('source', 'manual')

    if not amount or amount <= 0:
        flash('Bitte einen gültigen Betrag eingeben.', 'error')
        return redirect(url_for('billing.detail', id=id))

    try:
        payment_date = datetime.strptime(payment_date_str, '%Y-%m-%d').date() if payment_date_str else date.today()
    except ValueError:
        payment_date = date.today()

    zahlung = Payment(
        invoice_id=rechnung.id,
        amount=amount,
        payment_date=payment_date,
        reference=reference,
        source=source,
    )
    db.session.add(zahlung)

    # Status aktualisieren
    total_paid = rechnung.total_paid + amount
    total_due = (rechnung.amount or 0) + (rechnung.dunning_fees or 0)

    if total_paid >= total_due:
        rechnung.status = 'paid'
        rechnung.paid_at = datetime.utcnow()
    elif total_paid > 0:
        rechnung.status = 'partially_paid'

    db.session.commit()
    flash(f'Zahlung über CHF {amount:.2f} verbucht.', 'success')
    return redirect(url_for('billing.detail', id=id))


@billing_bp.route('/<int:id>/senden', methods=['POST'])
@login_required
def send_invoice(id):
    """Rechnung als gesendet markieren"""
    rechnung = Invoice.query.get_or_404(id)
    rechnung.status = 'sent'
    rechnung.sent_at = datetime.utcnow()

    # Bei Tiers Payant: TP-Copy-Flag setzen
    if rechnung.billing_model == 'tiers_payant':
        rechnung.tp_copy_sent = True

    db.session.commit()
    flash(f'Rechnung {rechnung.invoice_number} als gesendet markiert.', 'success')
    return redirect(url_for('billing.detail', id=id))


@billing_bp.route('/<int:id>/mahnung', methods=['POST'])
@login_required
def send_dunning(id):
    """Mahnung senden (nächste Stufe)"""
    rechnung = Invoice.query.get_or_404(id)

    if rechnung.dunning_level >= 3:
        flash('Maximale Mahnstufe erreicht.', 'warning')
        return redirect(url_for('billing.detail', id=id))

    new_level = rechnung.dunning_level + 1

    # Mahngebühr laden (nur bei Tiers Garant)
    fee = 0
    if rechnung.billing_model == 'tiers_garant':
        config = DunningConfig.query.filter_by(level=new_level).first()
        if config:
            fee = config.fee

    rechnung.dunning_level = new_level
    rechnung.last_dunning_date = date.today()
    rechnung.dunning_fees = (rechnung.dunning_fees or 0) + fee

    if new_level == 3:
        rechnung.status = 'in_collection'

    db.session.commit()
    flash(f'Mahnung Stufe {new_level} versendet.' +
          (f' Mahngebühr: CHF {fee:.2f}' if fee > 0 else ''), 'success')
    return redirect(url_for('billing.detail', id=id))


@billing_bp.route('/mahnungen')
@login_required
def dunning_overview():
    """Mahnungsübersicht: Alle überfälligen Rechnungen"""
    today = date.today()
    ueberfaellig = Invoice.query.filter(
        Invoice.status.in_(['open', 'sent', 'answered', 'partially_paid']),
        Invoice.due_date < today,
    ).order_by(Invoice.due_date).all()

    return render_template('billing/mahnungen.html', rechnungen=ueberfaellig)


@billing_bp.route('/zahlungen')
@login_required
def payments_overview():
    """Zahlungsübersicht"""
    zahlungen = Payment.query.order_by(Payment.payment_date.desc()).limit(50).all()
    return render_template('billing/zahlungen.html', zahlungen=zahlungen)


@billing_bp.route('/vesr-import', methods=['GET', 'POST'])
@login_required
def vesr_import():
    """VESR-Datei importieren für automatischen Zahlungsabgleich"""
    if request.method == 'POST':
        if 'vesr_file' not in request.files:
            flash('Keine Datei ausgewählt.', 'error')
            return redirect(url_for('billing.vesr_import'))

        file = request.files['vesr_file']
        if file.filename == '':
            flash('Keine Datei ausgewählt.', 'error')
            return redirect(url_for('billing.vesr_import'))

        content = file.read().decode('utf-8', errors='ignore')
        results = _process_vesr_file(content)

        flash(f'VESR-Import: {results["matched"]} Zahlungen zugeordnet, '
              f'{results["unmatched"]} nicht zugeordnet.', 'success')
        return redirect(url_for('billing.payments_overview'))

    return render_template('billing/vesr_import.html')


@billing_bp.route('/<int:id>/pdf')
@login_required
def generate_pdf(id):
    """Rechnung als PDF generieren mit QR-Code"""
    rechnung = Invoice.query.get_or_404(id)
    positionen = rechnung.items.order_by(InvoiceItem.position).all()
    org = Organization.query.first()

    pdf_buffer = _generate_invoice_pdf(rechnung, positionen, org)

    return send_file(
        pdf_buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'{rechnung.invoice_number}.pdf',
    )


@billing_bp.route('/taxpunktwerte')
@login_required
def tax_point_values():
    """Taxpunktwerte-Übersicht"""
    werte = TaxPointValue.query.order_by(TaxPointValue.tariff_type, TaxPointValue.canton).all()
    return render_template('billing/taxpunktwerte.html', werte=werte)


# ============================================================
# Hilfsfunktionen
# ============================================================

def _calculate_tax_points(tariff_type, duration_minutes):
    """Berechnet Taxpunkte basierend auf Tarif und Dauer.

    Schweizer Tarif-Systeme:
    - Tarif 311: UVG/IVG/MVG Physiotherapie (ca. 48 TP pro 30 Min.)
    - Tarif 312: KVG Physiotherapie (ca. 48 TP pro 30 Min.)
    - Tarif 338/325: Ergotherapie (ca. 56 TP pro 30 Min.)
    - Tarif 590/999: EMR Komplementärmedizin (Pauschal, z.B. 108 TP pro 60 Min.)
    - Pauschal/Privat: Keine Taxpunkte, direkter Betrag
    """
    tp_map = {
        '311': 48.0,   # pro 30 Min
        '312': 48.0,   # pro 30 Min
        '338': 56.0,   # pro 30 Min
        '325': 56.0,   # pro 30 Min
        '590': 54.0,   # pro 30 Min (108 pro 60)
        '999': 54.0,   # pro 30 Min
    }
    base_tp = tp_map.get(tariff_type, 48.0)
    # Skalierung nach Dauer (Basis: 30 Minuten)
    return round(base_tp * (duration_minutes / 30.0), 1)


def _generate_qr_reference(invoice_id):
    """Generiert eine QR-Referenznummer (26 Stellen + Prüfziffer)"""
    ref_base = str(invoice_id).zfill(26)
    # Prüfziffer nach Modulo 10 rekursiv (vereinfacht)
    checksum = sum(int(d) for d in ref_base) % 10
    return ref_base + str(checksum)


def _process_vesr_file(content):
    """Verarbeitet eine VESR-Datei (Typ 3 Records) und gleicht Zahlungen ab.

    VESR-Format: Zeilenbasiert, Typ 3 = Gutschrift
    Position 0-1: Record-Typ (03 = Gutschrift)
    Position 2-11: Teilnehmernummer
    Position 12-38: Referenznummer (27 Stellen)
    Position 39-48: Betrag in Rappen (10 Stellen)
    """
    matched = 0
    unmatched = 0

    for line in content.strip().split('\n'):
        line = line.strip()
        if len(line) < 49:
            continue

        record_type = line[0:2]
        if record_type != '03':
            continue

        reference = line[12:39].strip()
        amount_rappen = line[39:49].strip()

        try:
            amount = int(amount_rappen) / 100.0
        except ValueError:
            unmatched += 1
            continue

        # Rechnung über QR-Referenz finden
        invoice = Invoice.query.filter_by(qr_reference=reference).first()
        if not invoice:
            # Versuch über Rechnungsnummer in der Referenz
            unmatched += 1
            continue

        # Zahlung verbuchen
        zahlung = Payment(
            invoice_id=invoice.id,
            amount=amount,
            payment_date=date.today(),
            reference=f'VESR-{reference}',
            source='vesr',
        )
        db.session.add(zahlung)

        # Status aktualisieren
        total_paid = invoice.total_paid + amount
        total_due = (invoice.amount or 0) + (invoice.dunning_fees or 0)
        if total_paid >= total_due:
            invoice.status = 'paid'
            invoice.paid_at = datetime.utcnow()
        elif total_paid > 0:
            invoice.status = 'partially_paid'

        matched += 1

    db.session.commit()
    return {'matched': matched, 'unmatched': unmatched}


def _generate_invoice_pdf(rechnung, positionen, org):
    """Generiert ein Rechnungs-PDF mit QR-Zahlteil (Swiss QR Bill)."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas
        from reportlab.lib import colors
    except ImportError:
        # Fallback: Einfaches Text-PDF
        return _generate_simple_pdf(rechnung, positionen, org)

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    # --- Kopfbereich ---
    c.setFont('Helvetica-Bold', 16)
    c.drawString(20 * mm, height - 25 * mm, org.name if org else 'OMNIA Health Services AG')

    c.setFont('Helvetica', 9)
    if org:
        c.drawString(20 * mm, height - 32 * mm, org.address or '')
        c.drawString(20 * mm, height - 36 * mm, f'Tel: {org.phone or ""} | {org.email or ""}')
        c.drawString(20 * mm, height - 40 * mm, f'ZSR: {org.zsr_number or ""} | GLN: {org.gln_number or ""}')

    # --- Rechnungstitel ---
    c.setFont('Helvetica-Bold', 14)
    c.drawString(20 * mm, height - 55 * mm, f'Rechnung {rechnung.invoice_number}')

    # --- Rechnungsdaten ---
    c.setFont('Helvetica', 10)
    y = height - 65 * mm
    patient = rechnung.patient
    if patient:
        c.drawString(20 * mm, y, f'Patient: {patient.full_name}')
        y -= 5 * mm
        if patient.address:
            c.drawString(20 * mm, y, f'Adresse: {patient.address}')
            y -= 5 * mm
        if patient.date_of_birth:
            c.drawString(20 * mm, y, f'Geburtsdatum: {patient.date_of_birth.strftime("%d.%m.%Y")}')
            y -= 5 * mm
        if patient.ahv_number:
            c.drawString(20 * mm, y, f'AHV-Nr.: {patient.ahv_number}')
            y -= 5 * mm

    y -= 3 * mm
    c.drawString(120 * mm, height - 65 * mm, f'Datum: {rechnung.created_at.strftime("%d.%m.%Y")}')
    c.drawString(120 * mm, height - 70 * mm, f'Fällig: {rechnung.due_date.strftime("%d.%m.%Y") if rechnung.due_date else "-"}')
    c.drawString(120 * mm, height - 75 * mm, f'Typ: {rechnung.billing_type_label}')
    c.drawString(120 * mm, height - 80 * mm, f'Modell: {"Tiers Garant" if rechnung.billing_model == "tiers_garant" else "Tiers Payant"}')

    if rechnung.insurance_provider:
        c.drawString(120 * mm, height - 85 * mm, f'Versicherer: {rechnung.insurance_provider.name}')

    # --- Empfänger bei Tiers Payant ---
    if rechnung.billing_model == 'tiers_payant' and rechnung.insurance_provider:
        y -= 5 * mm
        c.setFont('Helvetica-Bold', 10)
        c.drawString(20 * mm, y, 'Rechnungsempfänger: Versicherer')
        c.setFont('Helvetica', 10)
        y -= 5 * mm
        c.drawString(20 * mm, y, rechnung.insurance_provider.name)

    # --- Positionen-Tabelle ---
    y -= 10 * mm
    c.setFont('Helvetica-Bold', 9)
    c.drawString(20 * mm, y, 'Pos.')
    c.drawString(32 * mm, y, 'Tarif')
    c.drawString(50 * mm, y, 'Beschreibung')
    c.drawString(120 * mm, y, 'Anz.')
    c.drawString(135 * mm, y, 'TP')
    c.drawString(150 * mm, y, 'TP-Wert')
    c.drawString(170 * mm, y, 'Betrag')

    y -= 2 * mm
    c.setStrokeColor(colors.grey)
    c.line(20 * mm, y, 190 * mm, y)
    y -= 4 * mm

    c.setFont('Helvetica', 9)
    for pos in positionen:
        if y < 80 * mm:  # Platz für QR-Teil lassen
            c.showPage()
            y = height - 25 * mm
            c.setFont('Helvetica', 9)

        c.drawString(20 * mm, y, str(pos.position))
        c.drawString(32 * mm, y, pos.tariff_code or '')
        # Beschreibung kürzen wenn nötig
        desc = (pos.description or '')[:50]
        c.drawString(50 * mm, y, desc)
        c.drawString(120 * mm, y, f'{pos.quantity:.0f}')
        c.drawString(135 * mm, y, f'{pos.tax_points:.1f}')
        c.drawString(150 * mm, y, f'{pos.tax_point_value:.2f}')
        c.drawRightString(190 * mm, y, f'CHF {pos.amount:.2f}')
        y -= 5 * mm

    # --- Summe ---
    y -= 3 * mm
    c.line(20 * mm, y, 190 * mm, y)
    y -= 5 * mm
    c.setFont('Helvetica-Bold', 10)
    c.drawString(120 * mm, y, 'Total:')
    c.drawRightString(190 * mm, y, f'CHF {rechnung.amount:.2f}')

    if rechnung.dunning_fees and rechnung.dunning_fees > 0:
        y -= 5 * mm
        c.drawString(120 * mm, y, 'Mahngebühren:')
        c.drawRightString(190 * mm, y, f'CHF {rechnung.dunning_fees:.2f}')
        y -= 5 * mm
        c.drawString(120 * mm, y, 'Gesamtbetrag:')
        c.drawRightString(190 * mm, y, f'CHF {(rechnung.amount + rechnung.dunning_fees):.2f}')

    # Bezahlt-Vermerk
    total_paid = rechnung.total_paid
    if total_paid > 0:
        y -= 5 * mm
        c.setFont('Helvetica', 10)
        c.drawString(120 * mm, y, f'Bereits bezahlt: CHF {total_paid:.2f}')
        y -= 5 * mm
        c.setFont('Helvetica-Bold', 10)
        c.drawString(120 * mm, y, f'Offener Betrag: CHF {rechnung.outstanding:.2f}')

    # --- QR-Zahlteil (vereinfacht) ---
    _draw_qr_payment_slip(c, rechnung, org, width, height)

    # --- TP-Copy Hinweis ---
    if rechnung.billing_model == 'tiers_payant' and rechnung.tp_copy_sent:
        c.setFont('Helvetica-Oblique', 8)
        c.drawString(20 * mm, 75 * mm, 'KOPIE - Rechnungskopie für den Patienten (Tiers Payant)')

    c.save()
    buffer.seek(0)
    return buffer


def _draw_qr_payment_slip(c, rechnung, org, width, height):
    """Zeichnet den QR-Zahlteil auf die Rechnung (Swiss QR Bill Format)."""
    from reportlab.lib.units import mm
    from reportlab.lib import colors

    # Trennlinie
    y_sep = 65 * mm
    c.setStrokeColor(colors.black)
    c.setDash(3, 3)
    c.line(0, y_sep, width, y_sep)
    c.setDash()

    # Empfangsschein (links)
    c.setFont('Helvetica-Bold', 8)
    c.drawString(5 * mm, 60 * mm, 'Empfangsschein')

    c.setFont('Helvetica', 7)
    c.drawString(5 * mm, 55 * mm, 'Konto / Zahlbar an')
    c.setFont('Helvetica', 8)
    c.drawString(5 * mm, 51 * mm, 'CH93 0076 2011 6238 5295 7')  # Demo QR-IBAN
    c.drawString(5 * mm, 47 * mm, org.name if org else 'OMNIA Health Services AG')
    c.drawString(5 * mm, 43 * mm, org.address.split(',')[0] if org and org.address else '')

    c.setFont('Helvetica', 7)
    c.drawString(5 * mm, 36 * mm, 'Referenz')
    c.setFont('Helvetica', 8)
    c.drawString(5 * mm, 32 * mm, rechnung.qr_reference or '')

    c.setFont('Helvetica', 7)
    c.drawString(5 * mm, 25 * mm, 'Zahlbar durch')
    c.setFont('Helvetica', 8)
    patient = rechnung.patient
    if rechnung.billing_model == 'tiers_payant' and rechnung.insurance_provider:
        c.drawString(5 * mm, 21 * mm, rechnung.insurance_provider.name)
    elif patient:
        c.drawString(5 * mm, 21 * mm, patient.full_name)
        if patient.address:
            c.drawString(5 * mm, 17 * mm, patient.address.split(',')[0])

    c.setFont('Helvetica-Bold', 8)
    c.drawString(5 * mm, 10 * mm, 'Währung    Betrag')
    c.setFont('Helvetica', 8)
    c.drawString(5 * mm, 6 * mm, f'CHF        {rechnung.outstanding:.2f}')

    # Zahlteil (rechts)
    c.setFont('Helvetica-Bold', 8)
    c.drawString(67 * mm, 60 * mm, 'Zahlteil')

    # QR-Code Platzhalter (Quadrat)
    c.setStrokeColor(colors.black)
    c.rect(67 * mm, 30 * mm, 26 * mm, 26 * mm)
    c.setFont('Helvetica', 6)
    c.drawCentredString(80 * mm, 42 * mm, 'QR-Code')
    c.drawCentredString(80 * mm, 38 * mm, 'Swiss QR Bill')

    # QR-Code generieren (wenn qrcode-Modul verfügbar)
    try:
        import qrcode
        qr_data = _build_swiss_qr_data(rechnung, org)
        qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=2, border=0)
        qr.add_data(qr_data)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color='black', back_color='white')
        # QR-Bild in Buffer
        img_buffer = io.BytesIO()
        qr_img.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        from reportlab.lib.utils import ImageReader
        c.drawImage(ImageReader(img_buffer), 67 * mm, 30 * mm, 26 * mm, 26 * mm)
    except ImportError:
        pass  # QR-Code-Platzhalter bleibt

    # Angaben rechts neben QR
    c.setFont('Helvetica', 7)
    c.drawString(100 * mm, 55 * mm, 'Konto / Zahlbar an')
    c.setFont('Helvetica', 8)
    c.drawString(100 * mm, 51 * mm, 'CH93 0076 2011 6238 5295 7')
    c.drawString(100 * mm, 47 * mm, org.name if org else 'OMNIA Health Services AG')

    c.setFont('Helvetica', 7)
    c.drawString(100 * mm, 40 * mm, 'Referenz')
    c.setFont('Helvetica', 8)
    c.drawString(100 * mm, 36 * mm, rechnung.qr_reference or '')

    c.setFont('Helvetica-Bold', 8)
    c.drawString(100 * mm, 10 * mm, 'Währung    Betrag')
    c.setFont('Helvetica', 8)
    c.drawString(100 * mm, 6 * mm, f'CHF        {rechnung.outstanding:.2f}')


def _build_swiss_qr_data(rechnung, org):
    """Baut die Swiss QR Bill Payload (SPC-Format)."""
    lines = [
        'SPC',                                      # QR-Typ
        '0200',                                     # Version
        '1',                                        # Coding
        'CH9300762011623852957',                     # QR-IBAN (Demo)
        'K',                                        # Adresstyp
        org.name if org else 'OMNIA Health',        # Name
        org.address.split(',')[0] if org and org.address else '',  # Strasse
        org.address.split(',')[1].strip() if org and org.address and ',' in org.address else '',  # PLZ Ort
        '',                                         # Land (leer)
        '',                                         # Land (leer)
        '',                                         # Betrag (leer = offen)
        f'{rechnung.outstanding:.2f}',              # Betrag
        'CHF',                                      # Währung
    ]
    # Zahlungspflichtiger
    patient = rechnung.patient
    if rechnung.billing_model == 'tiers_payant' and rechnung.insurance_provider:
        lines.extend(['K', rechnung.insurance_provider.name, '', '', '', ''])
    elif patient:
        lines.extend(['K', patient.full_name, patient.address or '', '', '', ''])
    else:
        lines.extend(['', '', '', '', '', ''])
    # Referenztyp + Referenz
    lines.extend(['QRR', rechnung.qr_reference or '', '', 'EPD'])
    return '\n'.join(lines)


def _generate_simple_pdf(rechnung, positionen, org):
    """Fallback-PDF ohne reportlab (einfacher Text-Export)."""
    buffer = io.BytesIO()
    text = f"""RECHNUNG {rechnung.invoice_number}
{'=' * 50}
{org.name if org else 'OMNIA Health Services AG'}
{org.address if org else ''}

Patient: {rechnung.patient.full_name if rechnung.patient else '-'}
Datum: {rechnung.created_at.strftime('%d.%m.%Y')}
Fällig: {rechnung.due_date.strftime('%d.%m.%Y') if rechnung.due_date else '-'}
Typ: {rechnung.billing_type_label}
Modell: {'Tiers Garant' if rechnung.billing_model == 'tiers_garant' else 'Tiers Payant'}

POSITIONEN
{'-' * 50}
"""
    for pos in positionen:
        text += f"{pos.position}. {pos.tariff_code or ''} | {pos.description or ''} | "
        text += f"{pos.quantity:.0f} x {pos.tax_points:.1f} TP x {pos.tax_point_value:.2f} = CHF {pos.amount:.2f}\n"

    text += f"\n{'=' * 50}\nTotal: CHF {rechnung.amount:.2f}\n"

    if rechnung.dunning_fees and rechnung.dunning_fees > 0:
        text += f"Mahngebühren: CHF {rechnung.dunning_fees:.2f}\n"
        text += f"Gesamtbetrag: CHF {(rechnung.amount + rechnung.dunning_fees):.2f}\n"

    buffer.write(text.encode('utf-8'))
    buffer.seek(0)
    return buffer
