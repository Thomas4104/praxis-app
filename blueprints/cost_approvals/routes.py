# Gutsprachen-Routen: Kostengutsprachen erstellen und verwalten

from datetime import datetime, date, timedelta
from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from blueprints.cost_approvals import cost_approvals_bp
from models import (db, CostApproval, Patient, TreatmentSeries,
                    InsuranceProvider, Doctor, Employee)


@cost_approvals_bp.route('/')
@login_required
def index():
    """Gutsprachen-Übersicht mit Status-Filter"""
    status_filter = request.args.get('status', '')
    query = CostApproval.query.order_by(CostApproval.created_at.desc())

    if status_filter:
        query = query.filter(CostApproval.status == status_filter)

    gutsprachen = query.all()

    stats = {
        'total': CostApproval.query.count(),
        'pending': CostApproval.query.filter_by(status='pending').count(),
        'sent': CostApproval.query.filter_by(status='sent').count(),
        'approved': CostApproval.query.filter_by(status='approved').count(),
        'rejected': CostApproval.query.filter_by(status='rejected').count(),
    }

    return render_template('cost_approvals/index.html',
                           gutsprachen=gutsprachen,
                           stats=stats,
                           status_filter=status_filter)


@cost_approvals_bp.route('/neu', methods=['GET', 'POST'])
@login_required
def create():
    """Neue Gutsprache erstellen"""
    if request.method == 'POST':
        patient_id = request.form.get('patient_id', type=int)
        insurance_provider_id = request.form.get('insurance_provider_id', type=int)
        doctor_id = request.form.get('doctor_id', type=int)
        series_id = request.form.get('series_id', type=int)
        diagnosis = request.form.get('diagnosis', '')
        treatment_type = request.form.get('treatment_type', '')
        approved_sessions = request.form.get('approved_sessions', type=int)
        notes = request.form.get('notes', '')

        if not patient_id:
            flash('Bitte einen Patienten auswählen.', 'error')
            return redirect(url_for('cost_approvals.create'))

        gutsprache = CostApproval(
            patient_id=patient_id,
            insurance_provider_id=insurance_provider_id,
            doctor_id=doctor_id,
            series_id=series_id,
            diagnosis=diagnosis,
            treatment_type=treatment_type,
            approved_sessions=approved_sessions,
            notes=notes,
            valid_until=date.today() + timedelta(days=90),
        )
        db.session.add(gutsprache)
        db.session.commit()

        flash('Gutsprache erstellt.', 'success')
        return redirect(url_for('cost_approvals.detail', id=gutsprache.id))

    patienten = Patient.query.filter_by(is_active=True).order_by(Patient.last_name).all()
    versicherungen = InsuranceProvider.query.all()
    aerzte = Doctor.query.all()
    serien = TreatmentSeries.query.filter_by(status='active').all()

    return render_template('cost_approvals/form.html',
                           patienten=patienten,
                           versicherungen=versicherungen,
                           aerzte=aerzte,
                           serien=serien)


@cost_approvals_bp.route('/<int:id>')
@login_required
def detail(id):
    """Gutsprache-Details"""
    gutsprache = CostApproval.query.get_or_404(id)
    return render_template('cost_approvals/detail.html', gutsprache=gutsprache)


@cost_approvals_bp.route('/<int:id>/status', methods=['POST'])
@login_required
def update_status(id):
    """Status einer Gutsprache aktualisieren"""
    gutsprache = CostApproval.query.get_or_404(id)
    new_status = request.form.get('status', '')

    if new_status not in ('pending', 'sent', 'approved', 'rejected'):
        flash('Ungültiger Status.', 'error')
        return redirect(url_for('cost_approvals.detail', id=id))

    gutsprache.status = new_status

    if new_status == 'sent':
        gutsprache.sent_at = datetime.utcnow()
    elif new_status in ('approved', 'rejected'):
        gutsprache.answered_at = datetime.utcnow()
        approved_sessions = request.form.get('approved_sessions', type=int)
        approved_amount = request.form.get('approved_amount', type=float)
        if approved_sessions:
            gutsprache.approved_sessions = approved_sessions
        if approved_amount:
            gutsprache.approved_amount = approved_amount

    db.session.commit()
    flash(f'Gutsprache-Status auf "{gutsprache.status_label}" geändert.', 'success')
    return redirect(url_for('cost_approvals.detail', id=id))
