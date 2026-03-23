"""Routen fuer Gutsprachen-Verwaltung"""
from datetime import datetime, date
from flask import render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from blueprints.cost_approvals import cost_approvals_bp
from models import (db, CostApproval, CostApprovalItem, Patient, InsuranceProvider,
                    Doctor, Employee, TreatmentSeries, TreatmentSeriesTemplate)


@cost_approvals_bp.route('/')
@login_required
def index():
    """Gutsprachen-Uebersicht"""
    search = request.args.get('search', '').strip()
    status = request.args.get('status', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    query = CostApproval.query.filter_by(organization_id=current_user.organization_id)

    if search:
        query = query.join(Patient, CostApproval.patient_id == Patient.id, isouter=True)\
            .join(InsuranceProvider, CostApproval.insurance_provider_id == InsuranceProvider.id, isouter=True)\
            .filter(db.or_(
                Patient.first_name.ilike(f'%{search}%'),
                Patient.last_name.ilike(f'%{search}%'),
                InsuranceProvider.name.ilike(f'%{search}%'),
                CostApproval.approval_number.ilike(f'%{search}%')
            ))

    if status:
        query = query.filter(CostApproval.status == status)

    if date_from:
        try:
            df = datetime.strptime(date_from, '%Y-%m-%d').date()
            query = query.filter(CostApproval.created_at >= datetime.combine(df, datetime.min.time()))
        except ValueError:
            pass

    if date_to:
        try:
            dt = datetime.strptime(date_to, '%Y-%m-%d').date()
            query = query.filter(CostApproval.created_at <= datetime.combine(dt, datetime.max.time()))
        except ValueError:
            pass

    gutsprachen = query.order_by(CostApproval.created_at.desc()).all()

    return render_template('cost_approvals/index.html',
                           gutsprachen=gutsprachen,
                           search=search,
                           status_filter=status,
                           date_from=date_from,
                           date_to=date_to)


@cost_approvals_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    """Neue Gutsprache erstellen"""
    if request.method == 'POST':
        patient_id = request.form.get('patient_id', type=int)
        series_id = request.form.get('series_id', type=int)
        insurance_provider_id = request.form.get('insurance_provider_id', type=int)
        doctor_id = request.form.get('doctor_id', type=int)
        therapist_id = request.form.get('therapist_id', type=int)
        diagnosis_code = request.form.get('diagnosis_code', '').strip()
        diagnosis_text = request.form.get('diagnosis_text', '').strip()
        prescription_date_str = request.form.get('prescription_date', '')
        prescription_type = request.form.get('prescription_type', '')
        justification = request.form.get('justification', '').strip()

        # Naechste Gutsprache-Nummer generieren
        last = CostApproval.query.filter_by(
            organization_id=current_user.organization_id
        ).order_by(CostApproval.id.desc()).first()
        next_nr = (last.id + 1) if last else 1
        approval_number = f'GS-{date.today().year}-{next_nr:04d}'

        prescription_date = None
        if prescription_date_str:
            try:
                prescription_date = datetime.strptime(prescription_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass

        gutsprache = CostApproval(
            organization_id=current_user.organization_id,
            approval_number=approval_number,
            patient_id=patient_id,
            series_id=series_id,
            insurance_provider_id=insurance_provider_id,
            doctor_id=doctor_id,
            therapist_id=therapist_id,
            diagnosis_code=diagnosis_code,
            diagnosis_text=diagnosis_text,
            prescription_date=prescription_date,
            prescription_type=prescription_type,
            justification=justification,
            status='draft',
            requested_date=date.today()
        )
        db.session.add(gutsprache)
        db.session.flush()

        # Positionen hinzufuegen
        tariff_codes = request.form.getlist('tariff_code[]')
        descriptions = request.form.getlist('item_description[]')
        quantities = request.form.getlist('quantity[]')
        amounts = request.form.getlist('amount[]')
        comments = request.form.getlist('item_comment[]')

        total = 0.0
        total_sessions = 0
        for i in range(len(tariff_codes)):
            if not tariff_codes[i] and not descriptions[i]:
                continue
            qty = float(quantities[i]) if i < len(quantities) and quantities[i] else 1.0
            amt = float(amounts[i]) if i < len(amounts) and amounts[i] else 0.0
            comment = comments[i] if i < len(comments) else ''

            item = CostApprovalItem(
                cost_approval_id=gutsprache.id,
                tariff_code=tariff_codes[i],
                description=descriptions[i] if i < len(descriptions) else '',
                quantity=qty,
                amount=amt,
                comment=comment
            )
            db.session.add(item)
            total += amt * qty
            total_sessions += int(qty)

        gutsprache.total_amount = total
        gutsprache.requested_sessions = total_sessions
        db.session.commit()
        flash('Gutsprache erfolgreich erstellt.', 'success')
        return redirect(url_for('cost_approvals.detail', id=gutsprache.id))

    # GET: Formulardaten laden
    patients = Patient.query.filter_by(
        organization_id=current_user.organization_id, is_active=True
    ).order_by(Patient.last_name).all()

    insurances = InsuranceProvider.query.filter_by(is_active=True).all()
    doctors = Doctor.query.filter_by(is_active=True).order_by(Doctor.last_name).all()
    employees = Employee.query.filter_by(
        organization_id=current_user.organization_id, is_active=True
    ).all()

    # Vorausgewaehlter Patient (aus URL-Parameter)
    preselect_patient_id = request.args.get('patient_id', type=int)
    preselect_series_id = request.args.get('series_id', type=int)

    return render_template('cost_approvals/form.html',
                           patients=patients,
                           insurances=insurances,
                           doctors=doctors,
                           employees=employees,
                           preselect_patient_id=preselect_patient_id,
                           preselect_series_id=preselect_series_id)


@cost_approvals_bp.route('/detail/<int:id>')
@login_required
def detail(id):
    """Gutsprache-Detail"""
    gutsprache = CostApproval.query.get_or_404(id)
    items = gutsprache.items.all()
    return render_template('cost_approvals/detail.html',
                           gutsprache=gutsprache,
                           items=items)


@cost_approvals_bp.route('/api/<int:id>/send', methods=['POST'])
@login_required
def send_approval(id):
    """Gutsprache senden (draft -> sent)"""
    gutsprache = CostApproval.query.get_or_404(id)
    if gutsprache.status not in ('draft', 'cancelled'):
        return jsonify({'error': 'Gutsprache kann in diesem Status nicht gesendet werden.'}), 400

    gutsprache.status = 'sent'
    gutsprache.sent_date = date.today()
    db.session.commit()
    return jsonify({'success': True, 'message': 'Gutsprache wurde gesendet.'})


@cost_approvals_bp.route('/api/<int:id>/respond', methods=['POST'])
@login_required
def record_response(id):
    """Antwort erfassen"""
    gutsprache = CostApproval.query.get_or_404(id)
    data = request.get_json()

    result = data.get('result')  # approved, partially_approved, rejected
    approved_sessions = data.get('approved_sessions', type=int)
    approved_amount = data.get('approved_amount', type=float)
    valid_until = data.get('valid_until', '')
    rejection_reason = data.get('rejection_reason', '')
    response_notes = data.get('response_notes', '')

    if result == 'approved':
        gutsprache.status = 'approved'
        gutsprache.approved_sessions = approved_sessions or gutsprache.requested_sessions
        gutsprache.approved_amount = approved_amount or gutsprache.total_amount
    elif result == 'partially_approved':
        gutsprache.status = 'partially_approved'
        gutsprache.approved_sessions = approved_sessions
        gutsprache.approved_amount = approved_amount
    elif result == 'rejected':
        gutsprache.status = 'rejected'
        gutsprache.rejection_reason = rejection_reason

    gutsprache.response_date = date.today()
    gutsprache.response_notes = response_notes

    if valid_until:
        try:
            gutsprache.valid_until = datetime.strptime(valid_until, '%Y-%m-%d').date()
        except ValueError:
            pass

    db.session.commit()
    return jsonify({'success': True, 'message': 'Antwort wurde erfasst.'})


@cost_approvals_bp.route('/api/<int:id>/cancel', methods=['POST'])
@login_required
def cancel_approval(id):
    """Gutsprache stornieren"""
    gutsprache = CostApproval.query.get_or_404(id)
    gutsprache.status = 'cancelled'
    db.session.commit()
    return jsonify({'success': True, 'message': 'Gutsprache wurde storniert.'})


@cost_approvals_bp.route('/api/<int:id>/resend', methods=['POST'])
@login_required
def resend_approval(id):
    """Gutsprache erneut senden"""
    gutsprache = CostApproval.query.get_or_404(id)
    if gutsprache.status not in ('rejected', 'cancelled'):
        return jsonify({'error': 'Gutsprache kann nicht erneut gesendet werden.'}), 400

    gutsprache.status = 'sent'
    gutsprache.sent_date = date.today()
    gutsprache.response_date = None
    gutsprache.rejection_reason = None
    gutsprache.response_notes = None
    db.session.commit()
    return jsonify({'success': True, 'message': 'Gutsprache wurde erneut gesendet.'})


# === API-Endpunkte ===

@cost_approvals_bp.route('/api/patient/<int:patient_id>/series')
@login_required
def patient_series(patient_id):
    """Aktive Serien eines Patienten laden"""
    serien = TreatmentSeries.query.filter_by(
        patient_id=patient_id, status='active'
    ).all()
    result = []
    for s in serien:
        template_name = s.template.name if s.template else 'Ohne Vorlage'
        result.append({
            'id': s.id,
            'name': f'{template_name} ({s.diagnosis_text or s.diagnosis_code or ""})',
            'diagnosis_code': s.diagnosis_code,
            'diagnosis_text': s.diagnosis_text,
            'therapist_id': s.therapist_id,
            'doctor_id': s.prescribing_doctor_id,
            'insurance_type': s.insurance_type,
            'prescription_date': s.prescription_date.strftime('%Y-%m-%d') if s.prescription_date else '',
            'prescription_type': s.prescription_type or ''
        })
    return jsonify({'series': result})


@cost_approvals_bp.route('/api/patient/<int:patient_id>/insurance')
@login_required
def patient_insurance(patient_id):
    """Versicherung eines Patienten laden"""
    patient = Patient.query.get_or_404(patient_id)
    result = {
        'insurance_provider_id': patient.insurance_provider_id,
        'insurance_type': patient.insurance_type,
        'insurance_number': patient.insurance_number
    }
    return jsonify(result)
