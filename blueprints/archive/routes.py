"""Archiv-Modul: Abgeschlossene Serien, inaktive Patienten, alte Rechnungen, erledigte Tasks"""
from datetime import datetime, date, timedelta
from flask import render_template, jsonify, request
from flask_login import login_required, current_user
from blueprints.archive import archive_bp
from models import db, TreatmentSeries, Patient, Invoice, Task
from utils.permissions import require_permission
from services.settings_service import get_setting


@archive_bp.route('/')
@login_required
@require_permission('reporting.view')
def index():
    """Archiv-Uebersicht"""
    org_id = current_user.organization_id

    # Zaehler fuer Tabs
    counts = {
        'series': _get_archived_series_count(org_id),
        'patients': Patient.query.filter_by(organization_id=org_id, is_active=False).count(),
        'invoices': _get_archived_invoices_count(org_id),
        'tasks': Task.query.filter_by(organization_id=org_id, status='completed').count(),
    }

    tab = request.args.get('tab', 'series')
    return render_template('archive/index.html', counts=counts, active_tab=tab)


@archive_bp.route('/api/series')
@login_required
@require_permission('reporting.view')
def api_archived_series():
    """Archivierte (abgeschlossene) Behandlungsserien"""
    org_id = current_user.organization_id
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 25, type=int)

    months = int(get_setting(org_id, 'archive_series_after_months', '6') or 6)
    cutoff = date.today() - timedelta(days=months * 30)

    query = TreatmentSeries.query.filter(
        TreatmentSeries.status == 'completed',
        TreatmentSeries.completed_at <= cutoff,
    ).join(TreatmentSeries.patient).filter(
        Patient.organization_id == org_id
    ).order_by(TreatmentSeries.completed_at.desc())

    total = query.count()
    series = query.offset((page - 1) * per_page).limit(per_page).all()

    return jsonify({
        'total': total,
        'page': page,
        'per_page': per_page,
        'items': [{
            'id': s.id,
            'patient_name': f'{s.patient.last_name}, {s.patient.first_name}',
            'patient_id': s.patient_id,
            'diagnosis': s.diagnosis_text or '',
            'insurance_type': s.insurance_type or '',
            'status': s.status,
            'completed_at': s.completed_at.strftime('%d.%m.%Y') if s.completed_at else '',
            'created_at': s.created_at.strftime('%d.%m.%Y') if s.created_at else '',
        } for s in series]
    })


@archive_bp.route('/api/patients')
@login_required
@require_permission('reporting.view')
def api_archived_patients():
    """Inaktive Patienten"""
    org_id = current_user.organization_id
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 25, type=int)
    search = request.args.get('q', '').strip()

    query = Patient.query.filter_by(organization_id=org_id, is_active=False)

    if search:
        query = query.filter(
            db.or_(
                Patient.last_name.ilike(f'%{search}%'),
                Patient.first_name.ilike(f'%{search}%'),
                Patient.patient_number.ilike(f'%{search}%'),
            )
        )

    total = query.count()
    patients = query.order_by(Patient.last_name).offset((page - 1) * per_page).limit(per_page).all()

    return jsonify({
        'total': total,
        'page': page,
        'items': [{
            'id': p.id,
            'name': f'{p.last_name}, {p.first_name}',
            'patient_number': p.patient_number or '',
            'date_of_birth': p.date_of_birth.strftime('%d.%m.%Y') if p.date_of_birth else '',
        } for p in patients]
    })


@archive_bp.route('/api/invoices')
@login_required
@require_permission('reporting.view')
def api_archived_invoices():
    """Archivierte Rechnungen (bezahlt/storniert, aelter als X Monate)"""
    org_id = current_user.organization_id
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 25, type=int)

    months = int(get_setting(org_id, 'archive_invoices_after_months', '12') or 12)
    cutoff = date.today() - timedelta(days=months * 30)

    query = Invoice.query.filter(
        Invoice.organization_id == org_id,
        Invoice.status.in_(['paid', 'cancelled']),
        Invoice.created_at <= cutoff,
    ).order_by(Invoice.created_at.desc())

    total = query.count()
    invoices = query.offset((page - 1) * per_page).limit(per_page).all()

    return jsonify({
        'total': total,
        'page': page,
        'items': [{
            'id': i.id,
            'invoice_number': i.invoice_number,
            'patient_name': f'{i.patient.last_name}, {i.patient.first_name}' if i.patient else '',
            'amount_total': float(i.amount_total or 0),
            'status': i.status,
            'created_at': i.created_at.strftime('%d.%m.%Y') if i.created_at else '',
        } for i in invoices]
    })


@archive_bp.route('/api/tasks')
@login_required
@require_permission('reporting.view')
def api_archived_tasks():
    """Erledigte Aufgaben"""
    org_id = current_user.organization_id
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 25, type=int)

    query = Task.query.filter_by(
        organization_id=org_id,
        status='completed'
    ).order_by(Task.updated_at.desc())

    total = query.count()
    tasks = query.offset((page - 1) * per_page).limit(per_page).all()

    return jsonify({
        'total': total,
        'page': page,
        'items': [{
            'id': t.id,
            'title': t.title,
            'priority': t.priority or 'normal',
            'completed_at': t.updated_at.strftime('%d.%m.%Y') if t.updated_at else '',
        } for t in tasks]
    })


@archive_bp.route('/api/restore/<string:entity_type>/<int:entity_id>', methods=['POST'])
@login_required
@require_permission('settings.edit')
def api_restore(entity_type, entity_id):
    """Eintrag aus dem Archiv wiederherstellen"""
    from services.audit_service import log_action
    org_id = current_user.organization_id

    if entity_type == 'patient':
        patient = Patient.query.get_or_404(entity_id)
        if patient.organization_id != org_id:
            return jsonify({'error': 'Nicht erlaubt'}), 403
        patient.is_active = True
        log_action('restore', 'patient', entity_id)

    elif entity_type == 'series':
        series = TreatmentSeries.query.get_or_404(entity_id)
        if series.patient.organization_id != org_id:
            return jsonify({'error': 'Nicht erlaubt'}), 403
        series.status = 'active'
        series.completed_at = None
        log_action('restore', 'treatment_series', entity_id)

    elif entity_type == 'task':
        task = Task.query.get_or_404(entity_id)
        if task.organization_id != org_id:
            return jsonify({'error': 'Nicht erlaubt'}), 403
        task.status = 'open'
        log_action('restore', 'task', entity_id)
    else:
        return jsonify({'error': 'Unbekannter Typ'}), 400

    db.session.commit()
    return jsonify({'message': 'Wiederhergestellt'})


def _get_archived_series_count(org_id):
    """Zaehlt archivierte Behandlungsserien"""
    months = int(get_setting(org_id, 'archive_series_after_months', '6') or 6)
    cutoff = date.today() - timedelta(days=months * 30)
    return TreatmentSeries.query.filter(
        TreatmentSeries.status == 'completed',
        TreatmentSeries.completed_at <= cutoff,
    ).join(TreatmentSeries.patient).filter(
        Patient.organization_id == org_id
    ).count()


def _get_archived_invoices_count(org_id):
    """Zaehlt archivierte Rechnungen"""
    months = int(get_setting(org_id, 'archive_invoices_after_months', '12') or 12)
    cutoff = date.today() - timedelta(days=months * 30)
    return Invoice.query.filter(
        Invoice.organization_id == org_id,
        Invoice.status.in_(['paid', 'cancelled']),
        Invoice.created_at <= cutoff,
    ).count()
