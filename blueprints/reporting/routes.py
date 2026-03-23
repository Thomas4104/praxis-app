"""Reporting Blueprint: Auswertungen, KPI-Dashboard, Therapeuten-Scorecard"""
import json
from datetime import date, timedelta, datetime
from flask import render_template, request, jsonify, Response
from flask_login import login_required, current_user
from models import db, SavedReport, Employee, Location
from services.reporting_service import (
    REPORT_CATEGORIES, get_report_categories, get_category_filters,
    get_category_columns, run_report, calculate_kpis, calculate_kpi_comparison,
    calculate_therapist_scorecard, export_to_csv,
    get_revenue_chart_data, get_revenue_by_therapist,
    get_revenue_by_insurance_type, get_utilization_by_therapist,
    get_new_patients_chart_data
)
from blueprints.reporting import reporting_bp
from utils.auth import check_org


# ============================================================
# Auswertungen (Report-Builder)
# ============================================================

@reporting_bp.route('/')
@login_required
def index():
    """Hauptseite Auswertungen"""
    return render_template('reporting/reports.html')


@reporting_bp.route('/kpis')
@login_required
def kpis():
    """KPI-Dashboard"""
    return render_template('reporting/kpis.html')


@reporting_bp.route('/scorecard')
@login_required
def scorecard():
    """Therapeuten-Scorecard"""
    employees = Employee.query.filter_by(
        organization_id=current_user.organization_id,
        is_active=True
    ).all()
    return render_template('reporting/scorecard.html', employees=employees)


# ============================================================
# API-Endpunkte
# ============================================================

@reporting_bp.route('/api/categories')
@login_required
def api_categories():
    """Gibt alle Report-Kategorien zurueck"""
    return jsonify(get_report_categories())


@reporting_bp.route('/api/category/<category>/filters')
@login_required
def api_category_filters(category):
    """Gibt Filter fuer eine Kategorie zurueck, inkl. dynamischer Optionen"""
    filters = get_category_filters(category)
    org_id = current_user.organization_id

    # Dynamische Optionen laden
    for f in filters:
        if f.get('model') == 'Location':
            locations = Location.query.filter_by(organization_id=org_id, is_active=True).all()
            f['options'] = [{'value': str(l.id), 'label': l.name} for l in locations]
        elif f.get('model') == 'Employee':
            employees = Employee.query.filter_by(organization_id=org_id, is_active=True).all()
            f['options'] = [{'value': str(e.id), 'label': f"{e.user.first_name} {e.user.last_name}"}
                           for e in employees if e.user]

    return jsonify(filters)


@reporting_bp.route('/api/category/<category>/columns')
@login_required
def api_category_columns(category):
    """Gibt verfuegbare Spalten fuer eine Kategorie zurueck"""
    return jsonify(get_category_columns(category))


@reporting_bp.route('/api/run', methods=['POST'])
@login_required
def api_run_report():
    """Fuehrt eine Auswertung aus"""
    data = request.get_json()
    category = data.get('category')
    filters = data.get('filters', {})
    columns = data.get('columns', [])
    page = data.get('page', 1)
    per_page = data.get('per_page', 50)
    sort_by = data.get('sort_by')
    sort_dir = data.get('sort_dir', 'asc')

    result = run_report(category, filters, columns, current_user.organization_id,
                        page, per_page, sort_by, sort_dir)
    return jsonify(result)


@reporting_bp.route('/api/export', methods=['POST'])
@login_required
def api_export_csv():
    """Exportiert Auswertung als CSV"""
    data = request.get_json()
    category = data.get('category')
    filters = data.get('filters', {})
    columns = data.get('columns', [])

    # Alle Daten exportieren (ohne Paginierung)
    result = run_report(category, filters, columns, current_user.organization_id,
                        page=1, per_page=100000)

    csv_content = export_to_csv(result['headers'], result['rows'])

    cat_label = get_report_categories().get(category, category)
    filename = f"Auswertung_{cat_label}_{date.today().strftime('%Y%m%d')}.csv"

    return Response(
        '\ufeff' + csv_content,  # BOM fuer Excel
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )


@reporting_bp.route('/api/saved', methods=['GET'])
@login_required
def api_saved_reports():
    """Gibt alle gespeicherten Auswertungen zurueck"""
    reports = SavedReport.query.filter_by(
        organization_id=current_user.organization_id
    ).order_by(SavedReport.name.asc()).all()

    cat_labels = get_report_categories()
    return jsonify([{
        'id': r.id,
        'name': r.name,
        'category': r.category,
        'category_label': cat_labels.get(r.category, r.category),
        'filters': json.loads(r.filters_json) if r.filters_json else {},
        'columns': json.loads(r.columns_json) if r.columns_json else [],
        'created_at': r.created_at.strftime('%d.%m.%Y %H:%M') if r.created_at else ''
    } for r in reports])


@reporting_bp.route('/api/saved', methods=['POST'])
@login_required
def api_save_report():
    """Speichert eine Auswertung"""
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Bitte geben Sie einen Namen ein.'}), 400

    report_id = data.get('id')
    if report_id:
        report = SavedReport.query.get(report_id)
        if not report or report.organization_id != current_user.organization_id:
            return jsonify({'error': 'Auswertung nicht gefunden.'}), 404
    else:
        report = SavedReport(
            organization_id=current_user.organization_id,
            user_id=current_user.id
        )
        db.session.add(report)

    report.name = name
    report.category = data.get('category', '')
    report.filters_json = json.dumps(data.get('filters', {}))
    report.columns_json = json.dumps(data.get('columns', []))

    db.session.commit()
    return jsonify({'success': True, 'id': report.id})


@reporting_bp.route('/api/saved/<int:report_id>', methods=['DELETE'])
@login_required
def api_delete_report(report_id):
    """Loescht eine gespeicherte Auswertung"""
    report = SavedReport.query.get(report_id)
    if not report or report.organization_id != current_user.organization_id:
        return jsonify({'error': 'Auswertung nicht gefunden.'}), 404

    db.session.delete(report)
    db.session.commit()
    return jsonify({'success': True})


@reporting_bp.route('/api/saved/<int:report_id>/rename', methods=['PUT'])
@login_required
def api_rename_report(report_id):
    """Benennt eine gespeicherte Auswertung um"""
    report = SavedReport.query.get(report_id)
    if not report or report.organization_id != current_user.organization_id:
        return jsonify({'error': 'Auswertung nicht gefunden.'}), 404

    data = request.get_json()
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Bitte geben Sie einen Namen ein.'}), 400

    report.name = name
    db.session.commit()
    return jsonify({'success': True})


# ============================================================
# KPI-Dashboard API
# ============================================================

@reporting_bp.route('/api/kpis', methods=['POST'])
@login_required
def api_kpis():
    """Berechnet KPIs fuer einen Zeitraum"""
    data = request.get_json() or {}
    date_from = data.get('date_from')
    date_to = data.get('date_to')
    period = data.get('period', 'month')

    today = date.today()
    if not date_from or not date_to:
        if period == 'day':
            date_from = today
            date_to = today
        elif period == 'week':
            date_from = today - timedelta(days=today.weekday())
            date_to = date_from + timedelta(days=6)
        elif period == 'month':
            date_from = today.replace(day=1)
            if today.month == 12:
                date_to = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                date_to = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        elif period == 'quarter':
            q_month = ((today.month - 1) // 3) * 3 + 1
            date_from = today.replace(month=q_month, day=1)
            end_month = q_month + 2
            if end_month > 12:
                date_to = today.replace(year=today.year + 1, month=end_month - 12 + 1, day=1) - timedelta(days=1)
            else:
                date_to = today.replace(month=end_month + 1, day=1) - timedelta(days=1)
        elif period == 'year':
            date_from = today.replace(month=1, day=1)
            date_to = today.replace(month=12, day=31)
        else:
            date_from = today.replace(day=1)
            date_to = today

    comparison = calculate_kpi_comparison(date_from, date_to, current_user.organization_id)
    return jsonify(comparison)


@reporting_bp.route('/api/charts', methods=['POST'])
@login_required
def api_charts():
    """Gibt Chart-Daten zurueck"""
    data = request.get_json() or {}
    date_from = data.get('date_from')
    date_to = data.get('date_to')
    org_id = current_user.organization_id

    today = date.today()
    if not date_from:
        date_from = today.replace(month=1, day=1)
    if not date_to:
        date_to = today

    charts = {
        'revenue_trend': get_revenue_chart_data(org_id, 12),
        'revenue_by_therapist': get_revenue_by_therapist(org_id, date_from, date_to),
        'revenue_by_insurance': get_revenue_by_insurance_type(org_id, date_from, date_to),
        'utilization_by_therapist': get_utilization_by_therapist(org_id, date_from, date_to),
        'new_patients': get_new_patients_chart_data(org_id, 12)
    }
    return jsonify(charts)


# ============================================================
# Therapeuten-Scorecard API
# ============================================================

@reporting_bp.route('/api/scorecard', methods=['POST'])
@login_required
def api_scorecard():
    """Berechnet Scorecard fuer einen Therapeuten"""
    data = request.get_json() or {}
    employee_id = data.get('employee_id')
    period = data.get('period', 'month')

    if not employee_id:
        return jsonify({'error': 'Bitte wählen Sie einen Therapeuten.'}), 400

    # IDOR-Schutz: Pruefen ob Therapeut zur eigenen Organisation gehoert
    emp = Employee.query.get(int(employee_id))
    if emp:
        check_org(emp)

    today = date.today()
    if period == 'month':
        date_from = today.replace(day=1)
        if today.month == 12:
            date_to = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            date_to = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
    elif period == 'quarter':
        q_month = ((today.month - 1) // 3) * 3 + 1
        date_from = today.replace(month=q_month, day=1)
        end_month = q_month + 2
        if end_month > 12:
            date_to = today.replace(year=today.year + 1, month=end_month - 12 + 1, day=1) - timedelta(days=1)
        else:
            date_to = today.replace(month=end_month + 1, day=1) - timedelta(days=1)
    elif period == 'year':
        date_from = today.replace(month=1, day=1)
        date_to = today.replace(month=12, day=31)
    else:
        date_from = today.replace(day=1)
        date_to = today

    result = calculate_therapist_scorecard(int(employee_id), date_from, date_to, current_user.organization_id)
    if not result:
        return jsonify({'error': 'Therapeut nicht gefunden.'}), 404

    return jsonify(result)
