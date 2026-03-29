"""Routen fuer Abrechnung: Rechnungen, Zahlungen, Mahnungen"""
import os
from datetime import datetime, date, timedelta
from flask import render_template, request, jsonify, redirect, url_for, flash, send_file, abort
from flask_login import login_required, current_user
from blueprints.billing import billing_bp
from models import (db, Invoice, InvoiceItem, Payment, TaxPointValue, BankAccount,
                    TreatmentSeries, TreatmentSeriesTemplate, Patient, InsuranceProvider,
                    Organization, DunningRecord, Appointment, Employee, InvoiceFix)
from services.billing_service import (
    calculate_invoice_from_series, create_invoice_from_series,
    generate_invoice_number, record_payment, process_dunning,
    run_dunning_batch, generate_invoice_pdf, get_tax_point_value,
    get_invoice_type_label, get_billing_case_label, get_payment_type_label,
    get_reduction_reason_label, calculate_invoice_totals,
    approve_invoice, disapprove_invoice, close_invoice,
    generate_reference_number,
    stop_reminder, resume_reminder, escalate_to_inkasso,
    toggle_discount, delete_payment as service_delete_payment,
    create_credit_note, create_invoice_fix, update_invoice_comments
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
    ).all()

    # Korrekturen laden
    fixes = InvoiceFix.query.filter_by(invoice_id=id).order_by(InvoiceFix.created_at.desc()).all()

    # MediData-Tracking laden
    from models import MedidataTracking, MedidataResponse
    medidata_trackings = MedidataTracking.query.filter_by(invoice_id=id).order_by(MedidataTracking.created_at.desc()).all()
    medidata_responses = MedidataResponse.query.filter_by(invoice_id=id).order_by(MedidataResponse.created_at.desc()).all()

    return render_template('billing/detail.html',
                           invoice=invoice,
                           items=items,
                           payments=payments,
                           dunnings=dunnings,
                           fixes=fixes,
                           medidata_trackings=medidata_trackings,
                           medidata_responses=medidata_responses,
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


# ============================================================
# CAMT/VESR-Import (Banking-Dateien)
# ============================================================

@billing_bp.route('/import-payments', methods=['GET', 'POST'])
@login_required
@require_permission('billing.record_payment')
def import_payments():
    """Zahlungen aus CAMT/VESR-Datei importieren"""
    from services.banking_service import import_payments as do_import

    if request.method == 'POST':
        file = request.files.get('payment_file')
        if not file:
            flash('Bitte eine Datei auswaehlen.', 'error')
            return redirect(url_for('billing.import_payments'))

        file_content = file.read()
        filename = file.filename.lower()

        # Dateityp erkennen
        if filename.endswith('.xml'):
            file_type = 'camt054'
        elif filename.endswith('.v11') or filename.endswith('.csv') or filename.endswith('.txt'):
            file_type = 'vesr'
        else:
            flash('Unbekanntes Dateiformat. Bitte XML (CAMT) oder V11/TXT (VESR) verwenden.', 'error')
            return redirect(url_for('billing.import_payments'))

        org_id = get_org_id()
        result = do_import(file_content, file_type, org_id)

        if result.get('error'):
            flash(f"Fehler beim Import: {result['error']}", 'error')
        else:
            flash(f"Import abgeschlossen: {result['imported']} Zahlungen importiert, "
                  f"{result['matched']} zugeordnet, {result['unmatched']} nicht zugeordnet.", 'success')

        return render_template('billing/import_result.html', result=result)

    return render_template('billing/import_payments.html')


# ============================================================
# Phase 5: Archiv, Mahnstopp, Inkasso, Rabatt, Korrekturen
# ============================================================

@billing_bp.route('/archiv')
@login_required
@require_permission('billing.view')
def archiv():
    """Rechnungsarchiv: Abgeschlossene und stornierte Rechnungen (Cenplex: InvoiceArchiveViewModel)"""
    org_id = current_user.organization_id
    search = request.args.get('search', '').strip()
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    invoice_type = request.args.get('invoice_type', '')

    query = Invoice.query.filter(
        Invoice.organization_id == org_id,
        Invoice.status.in_(['paid', 'cancelled'])
    )

    if search:
        query = query.join(Patient, Invoice.patient_id == Patient.id, isouter=True)\
            .filter(db.or_(
                Patient.first_name.ilike(f'%{search}%'),
                Patient.last_name.ilike(f'%{search}%'),
                Invoice.invoice_number.ilike(f'%{search}%'),
                Invoice.reference_number.ilike(f'%{search}%')
            ))

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
    if invoice_type:
        query = query.filter(Invoice.invoice_type == int(invoice_type))

    page = request.args.get('page', 1, type=int)
    per_page = 25
    total = query.count()
    rechnungen = query.order_by(Invoice.updated_at.desc()).offset((page - 1) * per_page).limit(per_page).all()
    total_pages = (total + per_page - 1) // per_page

    return render_template('billing/archiv.html',
                           rechnungen=rechnungen,
                           search=search,
                           date_from=date_from,
                           date_to=date_to,
                           invoice_type=invoice_type,
                           page=page,
                           total_pages=total_pages,
                           total=total,
                           get_invoice_type_label=get_invoice_type_label)


@billing_bp.route('/validierungen')
@login_required
@require_permission('billing.view')
def validierungen():
    """Rechnungsvalidierungen: Serien pruefen (Cenplex: InvoiceValidationViewModel)"""
    org_id = current_user.organization_id

    active_series = TreatmentSeries.query.filter_by(status='active').filter(
        TreatmentSeries.patient.has(organization_id=org_id)
    ).all()

    validations = []
    for s in active_series:
        appt_count = Appointment.query.filter_by(series_id=s.id).filter(
            Appointment.status.notin_(['cancelled', 'no_show'])
        ).count()
        max_appts = s.template.num_appointments if s.template else 0

        issues = []
        # Serie vollstaendig
        if max_appts > 0 and appt_count >= max_appts:
            issues.append({'type': 'ready', 'text': 'Serie vollständig - bereit zur Abrechnung'})
        # Auto-Abrechnung faellig
        if s.template and getattr(s.template, 'auto_billing_after', None) and appt_count >= s.template.auto_billing_after:
            issues.append({'type': 'auto', 'text': f'Auto-Abrechnung nach {s.template.auto_billing_after} Terminen fällig'})
        # Bereits abgerechnet pruefen
        existing_invoice = Invoice.query.filter_by(series_id=s.id).filter(
            Invoice.status.notin_(['cancelled'])
        ).first()
        if existing_invoice:
            issues.append({'type': 'billed', 'text': f'Bereits abgerechnet: {existing_invoice.invoice_number}'})
        # Patient ohne Versicherung
        if s.patient and not s.patient.insurance_provider_id:
            issues.append({'type': 'warning', 'text': 'Patient hat keine Versicherung hinterlegt'})

        if issues:
            validations.append({
                'series': s,
                'patient': s.patient,
                'appt_count': appt_count,
                'max_appts': max_appts,
                'issues': issues,
                'existing_invoice': existing_invoice if existing_invoice else None
            })

    return render_template('billing/validierungen.html',
                           validations=validations)


@billing_bp.route('/<int:id>/reminder-stop', methods=['POST'])
@login_required
@require_permission('billing.start_dunning')
def reminder_stop(id):
    """Mahnstopp setzen (Cenplex: ReminderstopDto)"""
    invoice = Invoice.query.get_or_404(id)
    check_org(invoice)
    result, error = stop_reminder(id)
    if error:
        flash(f'Fehler: {error}', 'error')
    else:
        log_action('update', 'invoice', id, changes={'reminder_stop': {'new': str(date.today())}})
        flash('Mahnstopp wurde gesetzt.', 'success')
    return redirect(url_for('billing.detail', id=id))


@billing_bp.route('/<int:id>/reminder-resume', methods=['POST'])
@login_required
@require_permission('billing.start_dunning')
def reminder_resume(id):
    """Mahnstopp aufheben"""
    invoice = Invoice.query.get_or_404(id)
    check_org(invoice)
    result, error = resume_reminder(id)
    if error:
        flash(f'Fehler: {error}', 'error')
    else:
        log_action('update', 'invoice', id, changes={'reminder_stop': {'old': str(invoice.reminder_stop), 'new': None}})
        flash('Mahnstopp wurde aufgehoben.', 'success')
    return redirect(url_for('billing.detail', id=id))


@billing_bp.route('/<int:id>/inkasso', methods=['POST'])
@login_required
@require_permission('billing.start_dunning')
def inkasso(id):
    """Zu Inkasso eskalieren (Cenplex: IsinkassoDto)"""
    invoice = Invoice.query.get_or_404(id)
    check_org(invoice)
    result, error = escalate_to_inkasso(id)
    if error:
        flash(f'Fehler: {error}', 'error')
    else:
        log_action('update', 'invoice', id, changes={'is_inkasso': {'new': True}})
        flash('Rechnung wurde an Inkasso übergeben.', 'warning')
    return redirect(url_for('billing.detail', id=id))


@billing_bp.route('/<int:id>/toggle-discount', methods=['POST'])
@login_required
@require_permission('billing.create_invoice')
def toggle_discount_route(id):
    """Rabatt ein-/ausschalten (Cenplex: ChangeDiscount)"""
    invoice = Invoice.query.get_or_404(id)
    check_org(invoice)
    exclude = request.form.get('exclude_discount') == '1'
    result, error = toggle_discount(id, exclude)
    if error:
        flash(f'Fehler: {error}', 'error')
    else:
        status_text = 'ausgeschlossen' if exclude else 'eingeschlossen'
        log_action('update', 'invoice', id, changes={'exclude_discount': {'new': exclude}})
        flash(f'Rabatte wurden {status_text}.', 'success')
    return redirect(url_for('billing.detail', id=id))


@billing_bp.route('/<int:id>/payment/<int:payment_id>/delete', methods=['POST'])
@login_required
@require_permission('billing.record_payment')
def delete_payment_route(id, payment_id):
    """Zahlung loeschen (Cenplex: DeletePayment)"""
    invoice = Invoice.query.get_or_404(id)
    check_org(invoice)

    payment = Payment.query.get_or_404(payment_id)
    if payment.invoice_id != invoice.id:
        flash('Zahlung gehoert nicht zu dieser Rechnung.', 'error')
        return redirect(url_for('billing.detail', id=id))

    log_action('delete', 'payment', payment_id, changes={
        'amount': {'old': str(payment.amount)},
        'invoice_id': {'old': id}
    })
    result, error = service_delete_payment(payment_id)
    if error:
        flash(f'Fehler: {error}', 'error')
    else:
        flash(f'Zahlung von CHF {payment.amount:.2f} wurde storniert.', 'success')
    return redirect(url_for('billing.detail', id=id))


@billing_bp.route('/<int:id>/credit-note', methods=['POST'])
@login_required
@require_permission('billing.create_invoice')
def create_credit_note_route(id):
    """Gutschrift erstellen (Cenplex: ProductCreditInvoice)"""
    invoice = Invoice.query.get_or_404(id)
    check_org(invoice)
    reason = request.form.get('reason', '').strip()
    credit, error = create_credit_note(id, current_user.organization_id, reason)
    if error:
        flash(f'Fehler: {error}', 'error')
        return redirect(url_for('billing.detail', id=id))

    log_action('create', 'invoice', credit.id, changes={
        'type': {'new': 'Gutschrift'},
        'original_invoice': {'new': id},
        'amount': {'new': str(credit.amount_total)},
    })
    flash(f'Gutschrift {credit.invoice_number} wurde erstellt.', 'success')
    return redirect(url_for('billing.detail', id=credit.id))


@billing_bp.route('/<int:id>/fix', methods=['POST'])
@login_required
@require_permission('billing.create_invoice')
def add_fix(id):
    """Rechnungskorrektur hinzufuegen (Cenplex: InvoicefixDto)"""
    invoice = Invoice.query.get_or_404(id)
    check_org(invoice)

    fix_type = request.form.get('fix_type', type=int, default=0)
    description = request.form.get('fix_description', '').strip()
    amount = request.form.get('fix_amount', type=float, default=0)
    employee_id = current_user.employee.id if current_user.employee else None

    if not description:
        flash('Bitte Beschreibung angeben.', 'error')
        return redirect(url_for('billing.detail', id=id))

    fix, error = create_invoice_fix(id, fix_type, description, amount, employee_id)
    if error:
        flash(f'Fehler: {error}', 'error')
    else:
        log_action('create', 'invoice_fix', fix.id, changes={
            'invoice_id': {'new': id},
            'fix_type': {'new': fix_type},
            'amount': {'new': str(amount)},
        })
        flash('Korrektur wurde hinzugefügt.', 'success')
    return redirect(url_for('billing.detail', id=id))


@billing_bp.route('/<int:id>/comments', methods=['POST'])
@login_required
@require_permission('billing.view')
def update_comments(id):
    """Kommentare aktualisieren (Cenplex: CommentDto / InternalcommentDto)"""
    invoice = Invoice.query.get_or_404(id)
    check_org(invoice)

    comment = request.form.get('inv_comment', '').strip()
    internal_comment = request.form.get('internal_comment', '').strip()

    result, error = update_invoice_comments(id, comment=comment, internal_comment=internal_comment)
    if error:
        flash(f'Fehler: {error}', 'error')
    else:
        log_action('update', 'invoice', id, changes={'comments': {'new': 'aktualisiert'}})
        flash('Kommentare wurden gespeichert.', 'success')
    return redirect(url_for('billing.detail', id=id))


# ============================================================
# Cenplex Phase 5: API-Endpunkte
# ============================================================

@billing_bp.route('/api/search')
@login_required
def api_search_invoices():
    """Rechnungssuche (Cenplex: FindInvoice) - nach Nummer, Patient, Betrag"""
    from models import Invoice, Patient
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify([])

    org_id = current_user.organization_id
    query = Invoice.query.filter_by(organization_id=org_id, is_deleted=False)

    query = query.filter(
        db.or_(
            Invoice.invoice_number.ilike(f'%{q}%'),
            Invoice.reference_number.ilike(f'%{q}%'),
            Invoice.patient.has(db.or_(
                Patient.first_name.ilike(f'%{q}%'),
                Patient.last_name.ilike(f'%{q}%'),
                Patient.patient_number.ilike(f'%{q}%')
            ))
        )
    )

    invoices = query.order_by(Invoice.created_at.desc()).limit(20).all()
    return jsonify([{
        'id': i.id,
        'invoice_number': i.invoice_number,
        'patient_name': f'{i.patient.last_name}, {i.patient.first_name}' if i.patient else '',
        'amount_total': float(i.amount_total or 0),
        'amount_open': float(i.amount_open or 0),
        'status': i.status,
        'created_at': i.created_at.isoformat() if i.created_at else ''
    } for i in invoices])


@billing_bp.route('/api/batch-send', methods=['POST'])
@login_required
@require_permission('billing.send_invoice')
def api_batch_send():
    """Batch-Versand von Rechnungen (Cenplex: FindInvoicesToSend)"""
    from models import Invoice
    data = request.get_json()
    invoice_ids = data.get('invoice_ids', [])

    if not invoice_ids:
        return jsonify({'error': 'Keine Rechnungen ausgewählt'}), 400

    org_id = current_user.organization_id
    sent_count = 0
    errors = []

    for inv_id in invoice_ids:
        inv = Invoice.query.filter_by(id=inv_id, organization_id=org_id).first()
        if not inv:
            errors.append(f'Rechnung {inv_id} nicht gefunden')
            continue
        if inv.status not in ('draft', 'approved'):
            errors.append(f'Rechnung {inv.invoice_number}: Status {inv.status} erlaubt keinen Versand')
            continue

        inv.status = 'sent'
        inv.sent_at = datetime.now()
        if current_user.employee:
            inv.sent_by_id = current_user.employee.id
        sent_count += 1

    db.session.commit()
    return jsonify({
        'success': True,
        'sent_count': sent_count,
        'errors': errors
    })


@billing_bp.route('/<int:id>/reset', methods=['POST'])
@login_required
@require_permission('billing.cancel_invoice')
def reset_invoice(id):
    """Rechnung zuruecksetzen (Cenplex: ResetInvoice)"""
    from models import Invoice
    invoice = Invoice.query.get_or_404(id)
    if invoice.organization_id != current_user.organization_id:
        abort(403)

    if invoice.status == 'paid':
        flash('Bezahlte Rechnungen können nicht zurückgesetzt werden.', 'error')
        return redirect(url_for('billing.detail', id=id))

    invoice.status = 'draft'
    invoice.sent_at = None
    invoice.approved_date = None
    invoice.approved_by_id = None
    invoice.was_disapproved = False
    invoice.medidata_state = None
    db.session.commit()

    flash('Rechnung wurde auf Entwurf zurückgesetzt.', 'success')
    return redirect(url_for('billing.detail', id=id))


@billing_bp.route('/api/voucher/<string:code>')
@login_required
def api_find_voucher(code):
    """Gutschein-Code suchen (Cenplex: FindVoucher)"""
    from models import Invoice
    voucher = Invoice.query.filter_by(
        organization_id=current_user.organization_id,
        is_voucher=True,
        voucher_code=code,
        is_deleted=False
    ).first()

    if not voucher:
        return jsonify({'found': False})

    return jsonify({
        'found': True,
        'id': voucher.id,
        'amount': float(voucher.amount_total or 0),
        'patient_name': f'{voucher.patient.first_name} {voucher.patient.last_name}' if voucher.patient else '',
        'status': voucher.status
    })


@billing_bp.route('/api/invoice-validations')
@login_required
def api_invoice_validations():
    """Rechnungsvalidierungen laden (Cenplex: GetInvoiceValidations)
    Prüft offene Serien auf Abrechnungsbereitschaft"""
    org_id = current_user.organization_id
    from models import TreatmentSeries, Appointment, TreatmentSeriesTemplate

    active_series = TreatmentSeries.query.filter_by(status='active').filter(
        TreatmentSeries.patient.has(organization_id=org_id)
    ).all()

    validations = []
    for s in active_series:
        appt_count = Appointment.query.filter_by(series_id=s.id).filter(
            Appointment.status.notin_(['cancelled', 'no_show'])
        ).count()
        max_appts = s.template.num_appointments if s.template else 0

        issues = []
        if max_appts > 0 and appt_count >= max_appts:
            issues.append('Serie vollständig - bereit zur Abrechnung')
        if s.template and s.template.auto_billing_after and appt_count >= s.template.auto_billing_after:
            issues.append(f'Auto-Abrechnung nach {s.template.auto_billing_after} Terminen fällig')

        if issues:
            validations.append({
                'series_id': s.id,
                'patient_name': f'{s.patient.last_name}, {s.patient.first_name}' if s.patient else '',
                'series_title': s.title or (s.template.name if s.template else ''),
                'progress': f'{appt_count}/{max_appts}',
                'issues': issues
            })

    return jsonify(validations)
