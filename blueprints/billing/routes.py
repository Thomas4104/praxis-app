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
    run_dunning_batch, generate_invoice_pdf, get_tax_point_value,
    get_invoice_type_label, get_billing_case_label, get_payment_type_label,
    get_reduction_reason_label, calculate_invoice_totals,
    approve_invoice, disapprove_invoice, close_invoice,
    generate_reference_number
)
from services.settings_service import get_setting
from services.accounting_service import book_invoice, book_payment
from utils.auth import check_org, get_org_id
from utils.permissions import require_permission
from services.audit_service import log_action


# Status-Set fuer unveraenderbare Rechnungen
IMMUTABLE_STATUSES = {'sent', 'paid', 'overdue', 'cancelled'}


def _check_invoice_immutable(invoice):
    """Prueft ob eine Rechnung unveraenderbar ist. Gibt True zurueck wenn immutable."""
    return invoice.status in IMMUTABLE_STATUSES


# ============================================================
# Rechnungsuebersicht
# ============================================================

@billing_bp.route('/')
@login_required
@require_permission('billing.view')
def index():
    """Abrechnungsuebersicht mit Tabs und Filtern"""
    search = request.args.get('search', '').strip()
    status_filter = request.args.get('status', '')
    tab = request.args.get('tab', 'alle')
    billing_type = request.args.get('billing_type', '')
    billing_model_filter = request.args.get('billing_model', '')
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

    # Abrechnungsmodell (Tiers Payant / Tiers Garant)
    if billing_model_filter:
        query = query.filter(Invoice.billing_model == billing_model_filter)

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

    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = 25
    total = query.count()
    rechnungen = query.offset((page - 1) * per_page).limit(per_page).all()
    total_pages = (total + per_page - 1) // per_page

    # Statistiken berechnen (SQL-Aggregationen statt Python sum())
    total_offen = db.session.query(db.func.sum(Invoice.amount_open)).filter(
        Invoice.organization_id == org_id,
        Invoice.status.in_(['sent', 'partially_paid', 'overdue'])
    ).scalar() or 0

    total_ueberfaellig = db.session.query(db.func.sum(Invoice.amount_open)).filter(
        Invoice.organization_id == org_id,
        db.or_(
            Invoice.status == 'overdue',
            db.and_(
                Invoice.status.in_(['sent', 'partially_paid']),
                Invoice.due_date < date.today(),
                Invoice.amount_open > 0
            )
        )
    ).scalar() or 0

    count_offen = Invoice.query.filter_by(organization_id=org_id).filter(
        Invoice.status.in_(['sent', 'partially_paid'])
    ).count()

    count_ueberfaellig = Invoice.query.filter_by(organization_id=org_id).filter(
        db.or_(
            Invoice.status == 'overdue',
            db.and_(
                Invoice.status.in_(['sent', 'partially_paid']),
                Invoice.due_date < date.today(),
                Invoice.amount_open > 0
            )
        )
    ).count()

    stats = {
        'total_offen': total_offen,
        'total_ueberfaellig': total_ueberfaellig,
        'count_offen': count_offen,
        'count_ueberfaellig': count_ueberfaellig,
    }

    return render_template('billing/index.html',
                           rechnungen=rechnungen,
                           search=search,
                           status_filter=status_filter,
                           tab=tab,
                           billing_type=billing_type,
                           billing_model_filter=billing_model_filter,
                           date_from=date_from,
                           date_to=date_to,
                           sort_by=sort_by,
                           stats=stats,
                           page=page,
                           total_pages=total_pages,
                           total=total,
                           today=date.today())


# ============================================================
# Rechnung erstellen
# ============================================================

@billing_bp.route('/new', methods=['GET', 'POST'])
@login_required
@require_permission('billing.create_invoice')
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

            log_action('create', 'invoice', invoice.id, changes={
                'invoice_number': {'new': invoice.invoice_number},
                'amount_total': {'new': str(invoice.amount_total)},
                'patient_id': {'new': invoice.patient_id},
            })
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
@require_permission('billing.view')
def detail(id):
    """Rechnungsdetail-Ansicht"""
    invoice = Invoice.query.get_or_404(id)
    check_org(invoice)
    items = InvoiceItem.query.filter_by(invoice_id=id).order_by(InvoiceItem.position).all()
    payments = Payment.query.filter_by(invoice_id=id).order_by(Payment.payment_date.desc()).all()
    dunnings = DunningRecord.query.filter_by(invoice_id=id).order_by(DunningRecord.dunning_date.desc()).all()

    # Cenplex-Labels und Totale berechnen
    invoice_type_label = get_invoice_type_label(invoice.invoice_type) if invoice.invoice_type is not None else None
    billing_case_label = get_billing_case_label(invoice.billing_case) if invoice.billing_case is not None else None
    totals = calculate_invoice_totals(invoice)

    # Mitarbeiter fuer Genehmigung laden
    employees = Employee.query.filter_by(
        organization_id=invoice.organization_id, is_active=True
    ).order_by(Employee.last_name).all()

    return render_template('billing/detail.html',
                           invoice=invoice,
                           items=items,
                           payments=payments,
                           dunnings=dunnings,
                           today=date.today(),
                           invoice_type_label=invoice_type_label,
                           billing_case_label=billing_case_label,
                           totals=totals,
                           employees=employees,
                           get_payment_type_label=get_payment_type_label,
                           get_reduction_reason_label=get_reduction_reason_label)


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
    log_action('update', 'invoice', invoice.id, changes={'status': {'old': 'draft', 'new': 'checked'}})
    db.session.commit()
    flash('Rechnung wurde geprüft.', 'success')
    return redirect(url_for('billing.detail', id=id))


@billing_bp.route('/<int:id>/send', methods=['POST'])
@login_required
@require_permission('billing.send_invoice')
def send_invoice(id):
    """Rechnung senden (Geprueft -> Gesendet)"""
    invoice = Invoice.query.get_or_404(id)
    check_org(invoice)
    if invoice.status not in ('draft', 'checked'):
        flash('Diese Rechnung kann nicht gesendet werden.', 'error')
        return redirect(url_for('billing.detail', id=id))

    old_status = invoice.status
    send_via = request.form.get('send_via', 'print')
    invoice.status = 'sent'
    invoice.sent_at = datetime.utcnow()
    invoice.sent_via = send_via
    log_action('update', 'invoice', invoice.id, changes={'status': {'old': old_status, 'new': 'sent'}})
    db.session.commit()
    # Automatische Buchung in FiBu
    try:
        book_invoice(invoice, current_user.organization_id)
    except Exception:
        pass  # FiBu-Buchung optional, Rechnung trotzdem gesendet
    # Automatischer TP-Rechnungskopie-Versand (seit 01.01.2022 Pflicht)
    from services.tp_copy_service import should_send_tp_copy, send_tp_copy_to_patient
    if should_send_tp_copy(invoice):
        copy, error = send_tp_copy_to_patient(invoice.id)
        if error:
            flash(f'Rechnung gesendet, aber TP-Kopie fehlgeschlagen: {error}', 'warning')
        else:
            flash('Rechnung gesendet. TP-Rechnungskopie an Patient versendet.', 'success')
    else:
        flash(f'Rechnung wurde als "{send_via}" gesendet.', 'success')
    return redirect(url_for('billing.detail', id=id))


@billing_bp.route('/<int:id>/cancel', methods=['POST'])
@login_required
@require_permission('billing.cancel_invoice')
def cancel_invoice(id):
    """Rechnung stornieren"""
    invoice = Invoice.query.get_or_404(id)
    check_org(invoice)
    if invoice.status == 'cancelled':
        flash('Rechnung ist bereits storniert.', 'error')
        return redirect(url_for('billing.detail', id=id))
    if invoice.status == 'paid':
        flash('Bezahlte Rechnungen koennen nicht storniert werden. '
              'Erstellen Sie stattdessen eine Korrekturrechnung.', 'error')
        return redirect(url_for('billing.detail', id=id))

    old_status = invoice.status
    invoice.status = 'cancelled'
    log_action('update', 'invoice', invoice.id, changes={'status': {'old': old_status, 'new': 'cancelled'}})
    db.session.commit()
    flash('Rechnung wurde storniert.', 'success')
    return redirect(url_for('billing.detail', id=id))


@billing_bp.route('/<int:id>/payment', methods=['POST'])
@login_required
@require_permission('billing.record_payment')
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
        log_action('create', 'payment', payment.id, changes={'amount': {'new': amount}, 'invoice_id': {'new': id}})
        # Automatische Buchung in FiBu
        try:
            book_payment(payment, current_user.organization_id)
        except Exception:
            pass  # FiBu-Buchung optional, Zahlung trotzdem erfasst
        flash(f'Zahlung von CHF {amount:.2f} wurde erfasst.', 'success')

    return redirect(url_for('billing.detail', id=id))


@billing_bp.route('/<int:id>/dunning', methods=['POST'])
@login_required
@require_permission('billing.start_dunning')
def send_dunning(id):
    """Mahnung senden"""
    invoice = Invoice.query.get_or_404(id)
    check_org(invoice)
    org_id = current_user.organization_id
    record, error = process_dunning(id, org_id)
    if error:
        flash(f'Fehler: {error}', 'error')
    else:
        log_action('create', 'dunning', invoice.id, changes={'level': {'new': record.dunning_level}})
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
# Cenplex-Workflow: Genehmigen, Ablehnen, Abschliessen
# ============================================================

@billing_bp.route('/<int:id>/approve', methods=['POST'])
@login_required
@require_permission('billing.send_invoice')
def approve(id):
    """Rechnung genehmigen (Cenplex-Workflow)"""
    invoice = Invoice.query.get_or_404(id)
    check_org(invoice)

    employee_id = request.form.get('employee_id', type=int)
    if not employee_id:
        flash('Bitte waehlen Sie einen Mitarbeiter fuer die Genehmigung aus.', 'error')
        return redirect(url_for('billing.detail', id=id))

    result = approve_invoice(id, employee_id)
    if result:
        log_action('update', 'invoice', id, changes={
            'approved_by_id': {'new': employee_id},
            'approved_date': {'new': str(result.approved_date)},
        })
        flash('Rechnung wurde genehmigt.', 'success')
    else:
        flash('Rechnung nicht gefunden.', 'error')

    return redirect(url_for('billing.detail', id=id))


@billing_bp.route('/<int:id>/disapprove', methods=['POST'])
@login_required
@require_permission('billing.send_invoice')
def disapprove(id):
    """Genehmigung zurueckziehen"""
    invoice = Invoice.query.get_or_404(id)
    check_org(invoice)

    result = disapprove_invoice(id)
    if result:
        log_action('update', 'invoice', id, changes={
            'was_disapproved': {'new': True},
            'approved_by_id': {'old': str(invoice.approved_by_id), 'new': None},
        })
        flash('Genehmigung wurde zurueckgezogen.', 'success')
    else:
        flash('Rechnung nicht gefunden.', 'error')

    return redirect(url_for('billing.detail', id=id))


@billing_bp.route('/<int:id>/close', methods=['POST'])
@login_required
@require_permission('billing.record_payment')
def close(id):
    """Rechnung abschliessen (Cenplex: CloseInvoice)"""
    invoice = Invoice.query.get_or_404(id)
    check_org(invoice)

    reduction_reason = request.form.get('reduction_reason', type=int)
    open_amount = float(invoice.amount_open or 0)

    result = close_invoice(id, reduction_reason=reduction_reason, open_amount=open_amount)
    if result:
        log_action('update', 'invoice', id, changes={
            'status': {'old': invoice.status, 'new': 'paid'},
            'closed_date': {'new': str(result.closed_date)},
            'reduction_reason': {'new': reduction_reason},
        })
        flash('Rechnung wurde abgeschlossen.', 'success')
    else:
        flash('Rechnung nicht gefunden.', 'error')

    return redirect(url_for('billing.detail', id=id))


# ============================================================
# Mahnungen
# ============================================================

@billing_bp.route('/mahnungen')
@login_required
@require_permission('billing.start_dunning')
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
@require_permission('billing.start_dunning')
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
@require_permission('billing.view')
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

    # Summe per SQL berechnen
    total = query.with_entities(db.func.sum(Payment.amount)).scalar() or 0

    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = 25
    zahlungen_count = query.count()
    zahlungen_list = query.order_by(Payment.payment_date.desc()) \
        .offset((page - 1) * per_page).limit(per_page).all()
    total_pages = (zahlungen_count + per_page - 1) // per_page

    return render_template('billing/zahlungen.html',
                           zahlungen=zahlungen_list,
                           total=total,
                           date_from=date_from,
                           date_to=date_to,
                           method_filter=method_filter,
                           page=page,
                           total_pages=total_pages)


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

    # Cenplex-Totale berechnen
    totals = calculate_invoice_totals(invoice)

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
        # Cenplex-Felder
        'invoice_type': invoice.invoice_type,
        'invoice_type_label': get_invoice_type_label(invoice.invoice_type) if invoice.invoice_type is not None else None,
        'billing_case': invoice.billing_case,
        'billing_case_label': get_billing_case_label(invoice.billing_case) if invoice.billing_case is not None else None,
        'reference_number': invoice.reference_number,
        'approved_by_id': invoice.approved_by_id,
        'approved_date': invoice.approved_date.strftime('%d.%m.%Y %H:%M') if invoice.approved_date else None,
        'was_disapproved': invoice.was_disapproved,
        'closed_date': invoice.closed_date.strftime('%d.%m.%Y %H:%M') if invoice.closed_date else None,
        'medidata_state': invoice.medidata_state,
        'totals': totals,
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
            'reference': p.reference,
            'payment_type': p.payment_type,
            'payment_type_label': get_payment_type_label(p.payment_type) if p.payment_type is not None else None,
            'reduction_reason': p.reduction_reason,
            'reduction_reason_label': get_reduction_reason_label(p.reduction_reason) if p.reduction_reason else None
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


# ============================================================
# Rechnungspositionen bearbeiten/loeschen (mit Immutabilitaets-Schutz)
# ============================================================

@billing_bp.route('/<int:id>/edit', methods=['POST'])
@login_required
@require_permission('billing.create_invoice')
def edit_invoice(id):
    """Rechnungsdaten aendern (nur Entwurf/Geprueft)"""
    invoice = Invoice.query.get_or_404(id)
    check_org(invoice)

    if _check_invoice_immutable(invoice):
        flash('Versendete Rechnungen koennen nicht mehr geaendert werden. '
              'Erstellen Sie stattdessen eine Korrekturrechnung.', 'error')
        return redirect(url_for('billing.detail', id=id))

    old_values = {}
    new_values = {}

    billing_type = request.form.get('billing_type', '').strip()
    if billing_type and billing_type != invoice.billing_type:
        old_values['billing_type'] = invoice.billing_type
        new_values['billing_type'] = billing_type
        invoice.billing_type = billing_type

    billing_model = request.form.get('billing_model', '').strip()
    if billing_model and billing_model != invoice.billing_model:
        old_values['billing_model'] = invoice.billing_model
        new_values['billing_model'] = billing_model
        invoice.billing_model = billing_model

    notes = request.form.get('notes', '').strip()
    if notes != (invoice.notes or ''):
        old_values['notes'] = invoice.notes
        new_values['notes'] = notes
        invoice.notes = notes

    due_date_str = request.form.get('due_date', '').strip()
    if due_date_str:
        try:
            new_due = datetime.strptime(due_date_str, '%Y-%m-%d').date()
            if new_due != invoice.due_date:
                old_values['due_date'] = str(invoice.due_date)
                new_values['due_date'] = str(new_due)
                invoice.due_date = new_due
        except ValueError:
            pass

    if old_values:
        changes = {k: {'old': old_values.get(k), 'new': new_values.get(k)} for k in old_values}
        log_action('update', 'invoice', invoice.id, changes=changes)
        db.session.commit()
        flash('Rechnung wurde aktualisiert.', 'success')
    else:
        flash('Keine Aenderungen vorgenommen.', 'info')

    return redirect(url_for('billing.detail', id=id))


@billing_bp.route('/<int:id>/items/add', methods=['POST'])
@login_required
@require_permission('billing.create_invoice')
def add_item(id):
    """Position zu Rechnung hinzufuegen (nur Entwurf/Geprueft)"""
    invoice = Invoice.query.get_or_404(id)
    check_org(invoice)

    if _check_invoice_immutable(invoice):
        flash('Versendete Rechnungen koennen nicht mehr geaendert werden. '
              'Erstellen Sie stattdessen eine Korrekturrechnung.', 'error')
        return redirect(url_for('billing.detail', id=id))

    tariff_code = request.form.get('tariff_code', '').strip()
    description = request.form.get('description', '').strip()
    quantity = request.form.get('quantity', type=float, default=1)
    tax_points = request.form.get('tax_points', type=float, default=0)
    tp_value = request.form.get('tp_value', type=float, default=1.0)
    vat_rate = request.form.get('vat_rate', type=float, default=0)

    if not tariff_code:
        flash('Tarifziffer ist erforderlich.', 'error')
        return redirect(url_for('billing.detail', id=id))

    amt = round(tax_points * tp_value * quantity, 2)
    vat_amt = round(amt * vat_rate / 100, 2)
    max_pos = db.session.query(db.func.max(InvoiceItem.position)).filter_by(invoice_id=invoice.id).scalar() or 0

    item = InvoiceItem(
        invoice_id=invoice.id,
        position=max_pos + 1,
        tariff_code=tariff_code,
        description=description,
        quantity=quantity,
        tax_points=tax_points,
        tax_point_value=tp_value,
        amount=amt,
        vat_rate=vat_rate,
        vat_amount=vat_amt
    )
    db.session.add(item)
    invoice.amount_total = round(invoice.amount_total + amt + vat_amt, 2)
    invoice.amount_open = round(invoice.amount_open + amt + vat_amt, 2)

    log_action('create', 'invoice_item', item.id, changes={
        'invoice_id': {'new': invoice.id},
        'tariff_code': {'new': tariff_code},
        'amount': {'new': str(amt)},
    })
    db.session.commit()
    flash(f'Position {tariff_code} wurde hinzugefuegt.', 'success')
    return redirect(url_for('billing.detail', id=id))


@billing_bp.route('/<int:id>/items/<int:item_id>/edit', methods=['POST'])
@login_required
@require_permission('billing.create_invoice')
def edit_item(id, item_id):
    """Position bearbeiten (nur Entwurf/Geprueft)"""
    invoice = Invoice.query.get_or_404(id)
    check_org(invoice)

    if _check_invoice_immutable(invoice):
        flash('Versendete Rechnungen koennen nicht mehr geaendert werden. '
              'Erstellen Sie stattdessen eine Korrekturrechnung.', 'error')
        return redirect(url_for('billing.detail', id=id))

    item = InvoiceItem.query.get_or_404(item_id)
    if item.invoice_id != invoice.id:
        flash('Position gehoert nicht zu dieser Rechnung.', 'error')
        return redirect(url_for('billing.detail', id=id))

    old_amount = (item.amount or 0) + (item.vat_amount or 0)

    item.tariff_code = request.form.get('tariff_code', item.tariff_code).strip()
    item.description = request.form.get('description', item.description or '').strip()
    item.quantity = request.form.get('quantity', type=float, default=item.quantity)
    item.tax_points = request.form.get('tax_points', type=float, default=item.tax_points)
    item.tax_point_value = request.form.get('tp_value', type=float, default=item.tax_point_value)
    item.vat_rate = request.form.get('vat_rate', type=float, default=item.vat_rate)
    item.amount = round(item.tax_points * item.tax_point_value * item.quantity, 2)
    item.vat_amount = round(item.amount * item.vat_rate / 100, 2)

    new_amount = item.amount + item.vat_amount
    diff = round(new_amount - old_amount, 2)
    invoice.amount_total = round(invoice.amount_total + diff, 2)
    invoice.amount_open = round(invoice.amount_open + diff, 2)

    log_action('update', 'invoice_item', item.id, changes={
        'amount': {'old': str(old_amount), 'new': str(new_amount)},
    })
    db.session.commit()
    flash('Position wurde aktualisiert.', 'success')
    return redirect(url_for('billing.detail', id=id))


@billing_bp.route('/<int:id>/items/<int:item_id>/delete', methods=['POST'])
@login_required
@require_permission('billing.create_invoice')
def delete_item(id, item_id):
    """Position loeschen (nur Entwurf/Geprueft)"""
    invoice = Invoice.query.get_or_404(id)
    check_org(invoice)

    if _check_invoice_immutable(invoice):
        flash('Versendete Rechnungen koennen nicht mehr geaendert werden. '
              'Erstellen Sie stattdessen eine Korrekturrechnung.', 'error')
        return redirect(url_for('billing.detail', id=id))

    item = InvoiceItem.query.get_or_404(item_id)
    if item.invoice_id != invoice.id:
        flash('Position gehoert nicht zu dieser Rechnung.', 'error')
        return redirect(url_for('billing.detail', id=id))

    removed_amount = round((item.amount or 0) + (item.vat_amount or 0), 2)
    invoice.amount_total = round(invoice.amount_total - removed_amount, 2)
    invoice.amount_open = round(invoice.amount_open - removed_amount, 2)

    log_action('delete', 'invoice_item', item.id, changes={
        'invoice_id': {'old': invoice.id},
        'tariff_code': {'old': item.tariff_code},
        'amount': {'old': str(removed_amount)},
    })
    db.session.delete(item)
    db.session.commit()
    flash('Position wurde geloescht.', 'success')
    return redirect(url_for('billing.detail', id=id))
