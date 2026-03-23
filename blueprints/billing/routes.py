"""Routen fuer Abrechnung: Rechnungen, Zahlungen, Mahnungen"""
import os
from datetime import datetime, date, timedelta
from flask import render_template, request, jsonify, redirect, url_for, flash, send_file
from flask_login import login_required, current_user
from blueprints.billing import billing_bp
from models import (db, Invoice, InvoiceItem, Payment, TaxPointValue, BankAccount,
                    TreatmentSeries, TreatmentSeriesTemplate, Patient, InsuranceProvider,
                    Organization, DunningRecord, Appointment, Employee)
from services.billing_service import (
    calculate_invoice_from_series, create_invoice_from_series,
    generate_invoice_number, record_payment, process_dunning,
    run_dunning_batch, generate_invoice_pdf, get_tax_point_value
)
from services.settings_service import get_setting
from services.accounting_service import book_invoice, book_payment
from utils.auth import check_org, get_org_id


# ============================================================
# Rechnungsuebersicht
# ============================================================

@billing_bp.route('/')
@login_required
def index():
    """Abrechnungsuebersicht mit Tabs und Filtern"""
    search = request.args.get('search', '').strip()
    status_filter = request.args.get('status', '')
    tab = request.args.get('tab', 'alle')
    billing_type = request.args.get('billing_type', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    sort_by = request.args.get('sort', 'date_desc')

    org_id = current_user.organization_id
    query = Invoice.query.filter_by(organization_id=org_id)

    # Tab-Filter
    if tab == 'offen':
        query = query.filter(Invoice.status.in_(['sent', 'partially_paid']))
    elif tab == 'gesendet':
        query = query.filter(Invoice.status == 'sent')
    elif tab == 'bezahlt':
        query = query.filter(Invoice.status == 'paid')
    elif tab == 'ueberfaellig':
        query = query.filter(db.or_(
            Invoice.status == 'overdue',
            db.and_(
                Invoice.status.in_(['sent', 'partially_paid']),
                Invoice.due_date < date.today(),
                Invoice.amount_open > 0
            )
        ))

    # Status-Filter (zusaetzlich zu Tab)
    if status_filter:
        query = query.filter(Invoice.status == status_filter)

    # Abrechnungstyp
    if billing_type:
        query = query.filter(Invoice.billing_type == billing_type)

    # Zeitraum
    if date_from:
        try:
            df = datetime.strptime(date_from, '%Y-%m-%d').date()
            query = query.filter(Invoice.created_at >= datetime.combine(df, datetime.min.time()))
        except ValueError:
            pass
    if date_to:
        try:
            dt = datetime.strptime(date_to, '%Y-%m-%d').date()
            query = query.filter(Invoice.created_at <= datetime.combine(dt, datetime.max.time()))
        except ValueError:
            pass

    # Suche
    if search:
        query = query.join(Patient, Invoice.patient_id == Patient.id, isouter=True)\
            .join(InsuranceProvider, Invoice.insurance_provider_id == InsuranceProvider.id, isouter=True)\
            .filter(db.or_(
                Patient.first_name.ilike(f'%{search}%'),
                Patient.last_name.ilike(f'%{search}%'),
                InsuranceProvider.name.ilike(f'%{search}%'),
                Invoice.invoice_number.ilike(f'%{search}%')
            ))

    # Sortierung
    if sort_by == 'amount_asc':
        query = query.order_by(Invoice.amount_total.asc())
    elif sort_by == 'amount_desc':
        query = query.order_by(Invoice.amount_total.desc())
    elif sort_by == 'due_asc':
        query = query.order_by(Invoice.due_date.asc())
    elif sort_by == 'due_desc':
        query = query.order_by(Invoice.due_date.desc())
    elif sort_by == 'date_asc':
        query = query.order_by(Invoice.created_at.asc())
    else:
        query = query.order_by(Invoice.created_at.desc())

    rechnungen = query.all()

    # Statistiken berechnen
    stats = {
        'total_offen': sum(r.amount_open or 0 for r in Invoice.query.filter_by(organization_id=org_id).filter(Invoice.status.in_(['sent', 'partially_paid', 'overdue'])).all()),
        'total_ueberfaellig': sum(r.amount_open or 0 for r in Invoice.query.filter_by(organization_id=org_id).filter(db.or_(Invoice.status == 'overdue', db.and_(Invoice.status.in_(['sent', 'partially_paid']), Invoice.due_date < date.today(), Invoice.amount_open > 0))).all()),
        'count_offen': Invoice.query.filter_by(organization_id=org_id).filter(Invoice.status.in_(['sent', 'partially_paid'])).count(),
        'count_ueberfaellig': Invoice.query.filter_by(organization_id=org_id).filter(db.or_(Invoice.status == 'overdue', db.and_(Invoice.status.in_(['sent', 'partially_paid']), Invoice.due_date < date.today(), Invoice.amount_open > 0))).count(),
    }

    return render_template('billing/index.html',
                           rechnungen=rechnungen,
                           search=search,
                           status_filter=status_filter,
                           tab=tab,
                           billing_type=billing_type,
                           date_from=date_from,
                           date_to=date_to,
                           sort_by=sort_by,
                           stats=stats,
                           today=date.today())


# ============================================================
# Rechnung erstellen
# ============================================================

@billing_bp.route('/new', methods=['GET', 'POST'])
@login_required
def create():
    """Neue Rechnung erstellen"""
    org_id = current_user.organization_id

    if request.method == 'POST':
        series_id = request.form.get('series_id', type=int)
        billing_type = request.form.get('billing_type', '')
        billing_model = request.form.get('billing_model', '')
        payment_term = request.form.get('payment_term', type=int, default=30)
        notes = request.form.get('notes', '').strip()

        if series_id:
            invoice, error = create_invoice_from_series(series_id, org_id)
            if error:
                flash(f'Fehler: {error}', 'error')
                return redirect(url_for('billing.create'))

            # Ueberschreibungen anwenden
            if billing_type:
                invoice.billing_type = billing_type
            if billing_model:
                invoice.billing_model = billing_model
            if payment_term:
                invoice.due_date = date.today() + timedelta(days=payment_term)
            if notes:
                invoice.notes = notes

            # Manuelle Positionen hinzufuegen
            manual_positions = request.form.getlist('manual_tariff_code')
            for i, tc in enumerate(manual_positions):
                if tc.strip():
                    desc = request.form.getlist('manual_description')[i] if i < len(request.form.getlist('manual_description')) else ''
                    qty = float(request.form.getlist('manual_quantity')[i]) if i < len(request.form.getlist('manual_quantity')) else 1
                    tp = float(request.form.getlist('manual_tax_points')[i]) if i < len(request.form.getlist('manual_tax_points')) else 0
                    tpv = float(request.form.getlist('manual_tp_value')[i]) if i < len(request.form.getlist('manual_tp_value')) else 1.0
                    vat = float(request.form.getlist('manual_vat_rate')[i]) if i < len(request.form.getlist('manual_vat_rate')) else 0
                    amt = round(tp * tpv * qty, 2)
                    vat_amt = round(amt * vat / 100, 2)

                    max_pos = db.session.query(db.func.max(InvoiceItem.position)).filter_by(invoice_id=invoice.id).scalar() or 0
                    item = InvoiceItem(
                        invoice_id=invoice.id,
                        position=max_pos + 1,
                        tariff_code=tc.strip(),
                        description=desc,
                        quantity=qty,
                        tax_points=tp,
                        tax_point_value=tpv,
                        amount=amt,
                        vat_rate=vat,
                        vat_amount=vat_amt
                    )
                    db.session.add(item)
                    invoice.amount_total = round(invoice.amount_total + amt + vat_amt, 2)
                    invoice.amount_open = round(invoice.amount_open + amt + vat_amt, 2)

            db.session.commit()
            flash(f'Rechnung {invoice.invoice_number} wurde erstellt.', 'success')
            return redirect(url_for('billing.detail', id=invoice.id))
        else:
            flash('Bitte wählen Sie eine Behandlungsserie aus.', 'error')
            return redirect(url_for('billing.create'))

    # GET: Verfuegbare Serien laden
    serien = TreatmentSeries.query.filter(
        TreatmentSeries.patient_id.in_(
            db.session.query(Patient.id).filter_by(organization_id=org_id)
        )
    ).order_by(TreatmentSeries.created_at.desc()).all()

    # Bereits abgerechnete Serien markieren
    billed_series_ids = set(
        inv.series_id for inv in Invoice.query.filter(
            Invoice.organization_id == org_id,
            Invoice.series_id.isnot(None),
            Invoice.status.notin_(['cancelled'])
        ).all()
    )

    patients = Patient.query.filter_by(organization_id=org_id, is_active=True).order_by(Patient.last_name).all()
    insurances = InsuranceProvider.query.filter_by(organization_id=org_id, is_active=True).all()

    default_model = get_setting(org_id, 'billing_default_model', 'tiers_garant')
    default_term = get_setting(org_id, 'billing_payment_term', '30')

    return render_template('billing/form.html',
                           serien=serien,
                           billed_series_ids=billed_series_ids,
                           patients=patients,
                           insurances=insurances,
                           default_model=default_model,
                           default_term=default_term)


# ============================================================
# Rechnung Detail
# ============================================================

@billing_bp.route('/<int:id>')
@login_required
def detail(id):
    """Rechnungsdetail-Ansicht"""
    invoice = Invoice.query.get_or_404(id)
    check_org(invoice)
    items = InvoiceItem.query.filter_by(invoice_id=id).order_by(InvoiceItem.position).all()
    payments = Payment.query.filter_by(invoice_id=id).order_by(Payment.payment_date.desc()).all()
    dunnings = DunningRecord.query.filter_by(invoice_id=id).order_by(DunningRecord.dunning_date.desc()).all()

    return render_template('billing/detail.html',
                           invoice=invoice,
                           items=items,
                           payments=payments,
                           dunnings=dunnings,
                           today=date.today())


# ============================================================
# Rechnung-Aktionen
# ============================================================

@billing_bp.route('/<int:id>/check', methods=['POST'])
@login_required
def check_invoice(id):
    """Rechnung pruefen (Entwurf -> Geprueft)"""
    invoice = Invoice.query.get_or_404(id)
    check_org(invoice)
    if invoice.status != 'draft':
        flash('Nur Entwürfe können geprüft werden.', 'error')
        return redirect(url_for('billing.detail', id=id))

    invoice.status = 'checked'
    db.session.commit()
    flash('Rechnung wurde geprüft.', 'success')
    return redirect(url_for('billing.detail', id=id))


@billing_bp.route('/<int:id>/send', methods=['POST'])
@login_required
def send_invoice(id):
    """Rechnung senden (Geprueft -> Gesendet)"""
    invoice = Invoice.query.get_or_404(id)
    check_org(invoice)
    if invoice.status not in ('draft', 'checked'):
        flash('Diese Rechnung kann nicht gesendet werden.', 'error')
        return redirect(url_for('billing.detail', id=id))

    send_via = request.form.get('send_via', 'print')
    invoice.status = 'sent'
    invoice.sent_at = datetime.utcnow()
    invoice.sent_via = send_via
    db.session.commit()
    # Automatische Buchung in FiBu
    try:
        book_invoice(invoice, current_user.organization_id)
    except Exception:
        pass  # FiBu-Buchung optional, Rechnung trotzdem gesendet
    flash(f'Rechnung wurde als "{send_via}" gesendet.', 'success')
    return redirect(url_for('billing.detail', id=id))


@billing_bp.route('/<int:id>/cancel', methods=['POST'])
@login_required
def cancel_invoice(id):
    """Rechnung stornieren"""
    invoice = Invoice.query.get_or_404(id)
    check_org(invoice)
    if invoice.status == 'cancelled':
        flash('Rechnung ist bereits storniert.', 'error')
        return redirect(url_for('billing.detail', id=id))

    invoice.status = 'cancelled'
    db.session.commit()
    flash('Rechnung wurde storniert.', 'success')
    return redirect(url_for('billing.detail', id=id))


@billing_bp.route('/<int:id>/payment', methods=['POST'])
@login_required
def add_payment(id):
    """Zahlung erfassen"""
    invoice = Invoice.query.get_or_404(id)
    check_org(invoice)

    amount = request.form.get('amount', type=float)
    payment_date = request.form.get('payment_date', '')
    payment_method = request.form.get('payment_method', '')
    reference = request.form.get('reference', '').strip()
    notes = request.form.get('payment_notes', '').strip()

    if not amount or amount <= 0:
        flash('Bitte geben Sie einen gültigen Betrag ein.', 'error')
        return redirect(url_for('billing.detail', id=id))

    if not payment_date:
        payment_date = date.today().strftime('%Y-%m-%d')

    payment, error = record_payment(id, amount, payment_date, payment_method, reference, notes)
    if error:
        flash(f'Fehler: {error}', 'error')
    else:
        # Automatische Buchung in FiBu
        try:
            book_payment(payment, current_user.organization_id)
        except Exception:
            pass  # FiBu-Buchung optional, Zahlung trotzdem erfasst
        flash(f'Zahlung von CHF {amount:.2f} wurde erfasst.', 'success')

    return redirect(url_for('billing.detail', id=id))


@billing_bp.route('/<int:id>/dunning', methods=['POST'])
@login_required
def send_dunning(id):
    """Mahnung senden"""
    invoice = Invoice.query.get_or_404(id)
    check_org(invoice)
    org_id = current_user.organization_id
    record, error = process_dunning(id, org_id)
    if error:
        flash(f'Fehler: {error}', 'error')
    else:
        flash(f'Mahnung Stufe {record.dunning_level} wurde erstellt.', 'success')
    return redirect(url_for('billing.detail', id=id))


@billing_bp.route('/<int:id>/pdf')
@login_required
def generate_pdf(id):
    """PDF generieren und herunterladen"""
    invoice = Invoice.query.get_or_404(id)
    check_org(invoice)
    pdf_path, error = generate_invoice_pdf(id)
    if error:
        flash(f'Fehler bei PDF-Erstellung: {error}', 'error')
        return redirect(url_for('billing.detail', id=id))

    return send_file(pdf_path, as_attachment=True, download_name=os.path.basename(pdf_path))


@billing_bp.route('/<int:id>/tp-copy', methods=['POST'])
@login_required
def send_tp_copy(id):
    """TP-Kopie an Patient senden (bei Tiers Payant)"""
    invoice = Invoice.query.get_or_404(id)
    check_org(invoice)
    if invoice.billing_model != 'tiers_payant':
        flash('TP-Kopie nur bei Tiers Payant möglich.', 'error')
        return redirect(url_for('billing.detail', id=id))

    flash('TP-Kopie wurde an den Patienten gesendet.', 'success')
    return redirect(url_for('billing.detail', id=id))


# ============================================================
# Mahnungen
# ============================================================

@billing_bp.route('/mahnungen')
@login_required
def mahnungen():
    """Mahnungsuebersicht: Alle ueberfaelligen Rechnungen"""
    org_id = current_user.organization_id

    ueberfaellige = Invoice.query.filter(
        Invoice.organization_id == org_id,
        Invoice.status.in_(['sent', 'overdue', 'partially_paid']),
        Invoice.due_date < date.today(),
        Invoice.amount_open > 0
    ).order_by(Invoice.due_date.asc()).all()

    return render_template('billing/mahnungen.html',
                           ueberfaellige=ueberfaellige,
                           today=date.today())


@billing_bp.route('/mahnlauf', methods=['POST'])
@login_required
def mahnlauf():
    """Batch-Mahnlauf fuer alle faelligen Rechnungen"""
    org_id = current_user.organization_id
    results = run_dunning_batch(org_id)

    if results:
        flash(f'Mahnlauf abgeschlossen: {len(results)} Mahnungen erstellt.', 'success')
    else:
        flash('Keine fälligen Rechnungen für Mahnungen gefunden.', 'info')

    return redirect(url_for('billing.mahnungen'))


# ============================================================
# Zahlungen
# ============================================================

@billing_bp.route('/zahlungen')
@login_required
def zahlungen():
    """Zahlungsuebersicht"""
    org_id = current_user.organization_id
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    method_filter = request.args.get('method', '')

    query = Payment.query.join(Invoice, Payment.invoice_id == Invoice.id)\
        .filter(Invoice.organization_id == org_id)

    if date_from:
        try:
            df = datetime.strptime(date_from, '%Y-%m-%d').date()
            query = query.filter(Payment.payment_date >= df)
        except ValueError:
            pass
    if date_to:
        try:
            dt = datetime.strptime(date_to, '%Y-%m-%d').date()
            query = query.filter(Payment.payment_date <= dt)
        except ValueError:
            pass
    if method_filter:
        query = query.filter(Payment.payment_method == method_filter)

    zahlungen_list = query.order_by(Payment.payment_date.desc()).all()

    total = sum(z.amount for z in zahlungen_list)

    return render_template('billing/zahlungen.html',
                           zahlungen=zahlungen_list,
                           total=total,
                           date_from=date_from,
                           date_to=date_to,
                           method_filter=method_filter)


# ============================================================
# API-Endpunkte
# ============================================================

@billing_bp.route('/api/series/<int:series_id>/calculate')
@login_required
def api_calculate_series(series_id):
    """Berechnet Positionen fuer eine Serie (fuer Formular-Vorschau)"""
    org_id = current_user.organization_id
    result, error = calculate_invoice_from_series(series_id, org_id)
    if error:
        return jsonify({'error': error}), 400

    return jsonify({
        'items': result['items'],
        'patient_id': result['patient_id'],
        'insurance_provider_id': result['insurance_provider_id'],
        'billing_type': result['billing_type'],
        'billing_model': result['billing_model'],
        'amount_total': result['amount_total']
    })


@billing_bp.route('/api/invoice/<int:id>')
@login_required
def api_invoice_detail(id):
    """Rechnungsdetails als JSON"""
    invoice = Invoice.query.get_or_404(id)
    check_org(invoice)
    items = InvoiceItem.query.filter_by(invoice_id=id).order_by(InvoiceItem.position).all()
    payments = Payment.query.filter_by(invoice_id=id).order_by(Payment.payment_date.desc()).all()

    return jsonify({
        'id': invoice.id,
        'invoice_number': invoice.invoice_number,
        'status': invoice.status,
        'amount_total': invoice.amount_total,
        'amount_paid': invoice.amount_paid,
        'amount_open': invoice.amount_open,
        'billing_type': invoice.billing_type,
        'billing_model': invoice.billing_model,
        'due_date': invoice.due_date.strftime('%d.%m.%Y') if invoice.due_date else None,
        'dunning_level': invoice.dunning_level,
        'patient': {
            'id': invoice.patient.id,
            'name': f'{invoice.patient.first_name} {invoice.patient.last_name}'
        } if invoice.patient else None,
        'insurance': {
            'id': invoice.insurance_provider.id,
            'name': invoice.insurance_provider.name
        } if invoice.insurance_provider else None,
        'items': [{
            'position': i.position,
            'tariff_code': i.tariff_code,
            'description': i.description,
            'quantity': i.quantity,
            'tax_points': i.tax_points,
            'tax_point_value': i.tax_point_value,
            'amount': i.amount,
            'vat_rate': i.vat_rate,
            'vat_amount': i.vat_amount
        } for i in items],
        'payments': [{
            'amount': p.amount,
            'date': p.payment_date.strftime('%d.%m.%Y') if p.payment_date else None,
            'method': p.payment_method,
            'reference': p.reference
        } for p in payments]
    })


@billing_bp.route('/api/stats')
@login_required
def api_stats():
    """Abrechnungsstatistiken als JSON"""
    org_id = current_user.organization_id

    total_open = db.session.query(db.func.sum(Invoice.amount_open)).filter(
        Invoice.organization_id == org_id,
        Invoice.status.in_(['sent', 'partially_paid', 'overdue']),
        Invoice.amount_open > 0
    ).scalar() or 0

    total_paid_month = db.session.query(db.func.sum(Payment.amount)).join(
        Invoice, Payment.invoice_id == Invoice.id
    ).filter(
        Invoice.organization_id == org_id,
        Payment.payment_date >= date.today().replace(day=1)
    ).scalar() or 0

    return jsonify({
        'total_open': round(total_open, 2),
        'total_paid_month': round(total_paid_month, 2),
    })
