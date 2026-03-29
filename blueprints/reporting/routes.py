"""Reporting Blueprint: Auswertungen, KPI-Dashboard, Therapeuten-Scorecard, Ausdrucke"""
import json
import io
import os
from datetime import date, timedelta, datetime, time
from calendar import monthrange
from flask import render_template, request, jsonify, Response, send_file, abort
from sqlalchemy import func
from flask_login import login_required, current_user
from models import (db, SavedReport, Employee, Location, KpiDashboardConfig, KpiBoxDefinition, KpiBudget,
                    Appointment, Patient, Organization, TreatmentSeries, TreatmentPlan, Doctor,
                    Holiday, ClinicalFinding, Invoice, InvoiceItem)
from services.reporting_service import (
    REPORT_CATEGORIES, get_report_categories, get_category_filters,
    get_category_columns, run_report, calculate_kpis, calculate_kpi_comparison,
    calculate_therapist_scorecard, export_to_csv,
    get_revenue_chart_data, get_revenue_by_therapist,
    get_revenue_by_insurance_type, get_utilization_by_therapist,
    get_new_patients_chart_data,
    get_financial_kpis, get_appointment_kpis, get_chart_data_monthly,
    get_controlling_kpis, get_controlling_trend, get_budget_comparison, save_budget
)
from blueprints.reporting import reporting_bp
from utils.auth import check_org, get_org_id
from utils.permissions import require_permission
from services.audit_service import log_data_export


# ============================================================
# Auswertungen (Report-Builder)
# ============================================================

@reporting_bp.route('/')
@login_required
@require_permission('reporting.view')
def index():
    """Hauptseite Auswertungen"""
    return render_template('reporting/reports.html')


@reporting_bp.route('/kpis')
@login_required
@require_permission('reporting.view')
def kpis():
    """KPI-Dashboard"""
    return render_template('reporting/kpis.html')


@reporting_bp.route('/controlling')
@login_required
@require_permission('reporting.view')
def controlling():
    """Controlling-Dashboard (Cenplex: KPI Controlling)"""
    locations = Location.query.filter_by(
        organization_id=current_user.organization_id, is_active=True
    ).all()
    return render_template('reporting/controlling.html', locations=locations)


@reporting_bp.route('/scorecard')
@login_required
@require_permission('reporting.view')
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
@require_permission('reporting.export')
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

    # Audit-Logging fuer Datenexport
    log_data_export('csv_export', len(result.get('rows', [])), columns=columns, filters=filters)

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
# Erweiterte KPI-Endpunkte (Finanz-KPIs, Termin-KPIs, Chart-Daten)
# ============================================================

@reporting_bp.route('/api/financial-kpis')
@login_required
@require_permission('reporting.view')
def api_financial_kpis():
    """Finanz- und Termin-KPI-Daten laden"""
    from datetime import date, timedelta

    org_id = current_user.organization_id
    period = request.args.get('period', 'month')  # week, month, quarter, year

    today = date.today()
    if period == 'week':
        start = today - timedelta(days=7)
    elif period == 'quarter':
        quarter_start_month = ((today.month - 1) // 3) * 3 + 1
        start = date(today.year, quarter_start_month, 1)
    elif period == 'year':
        start = date(today.year, 1, 1)
    else:  # month
        start = date(today.year, today.month, 1)

    financial = get_financial_kpis(org_id, start, today)
    appointments = get_appointment_kpis(org_id, start, today)

    return jsonify({
        'financial': financial,
        'appointments': appointments,
        'period': period,
        'period_start': start.isoformat(),
        'period_end': today.isoformat(),
    })


@reporting_bp.route('/api/monthly-chart-data')
@login_required
@require_permission('reporting.view')
def api_monthly_chart_data():
    """Monatliche Chart-Daten (aktuelles Jahr + Vorjahr)"""
    from datetime import date

    org_id = current_user.organization_id
    year = request.args.get('year', date.today().year, type=int)
    category = request.args.get('category', 'revenue')

    data = get_chart_data_monthly(org_id, year, category)
    return jsonify(data)


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


# ============================================================
# Controlling-KPIs API (Cenplex: KpicontrollingDto)
# ============================================================

@reporting_bp.route('/api/controlling')
@login_required
@require_permission('reporting.view')
def api_controlling():
    """Controlling-KPIs laden"""
    org_id = current_user.organization_id
    period = request.args.get('period', 'month')
    location_id = request.args.get('location_id', type=int)

    today = date.today()
    if period == 'week':
        start = today - timedelta(days=today.weekday())
    elif period == 'quarter':
        q_month = ((today.month - 1) // 3) * 3 + 1
        start = date(today.year, q_month, 1)
    elif period == 'year':
        start = date(today.year, 1, 1)
    else:
        start = today.replace(day=1)

    controlling = get_controlling_kpis(org_id, start, today, location_id)
    trend = get_controlling_trend(org_id, months=6, location_id=location_id)

    return jsonify({
        'controlling': controlling,
        'trend': trend,
        'period': period,
        'period_start': start.isoformat(),
        'period_end': today.isoformat(),
    })


# ============================================================
# Budget-API (Cenplex: BudgetlinesDto)
# ============================================================

@reporting_bp.route('/api/budget')
@login_required
@require_permission('reporting.view')
def api_budget():
    """Budget-Vergleich laden"""
    org_id = current_user.organization_id
    year = request.args.get('year', date.today().year, type=int)
    metric = request.args.get('metric', 'revenue')
    location_id = request.args.get('location_id', type=int)
    employee_id = request.args.get('employee_id', type=int)

    result = get_budget_comparison(org_id, year, metric, location_id, employee_id)
    return jsonify(result)


@reporting_bp.route('/api/budget', methods=['POST'])
@login_required
@require_permission('reporting.view')
def api_save_budget():
    """Budget-Ziel speichern"""
    data = request.get_json()
    org_id = current_user.organization_id

    save_budget(
        org_id=org_id,
        kpi_metric=data.get('metric', 'revenue'),
        year=data.get('year', date.today().year),
        month=data.get('month'),
        target_value=data.get('target_value', 0),
        location_id=data.get('location_id'),
        employee_id=data.get('employee_id')
    )
    return jsonify({'success': True})


# ============================================================
# KPI-Dashboard-Konfiguration CRUD (Cenplex: KpidashboardconfigDto)
# ============================================================

@reporting_bp.route('/api/dashboard-configs')
@login_required
@require_permission('reporting.view')
def api_dashboard_configs():
    """Alle Dashboard-Konfigurationen laden"""
    configs = KpiDashboardConfig.query.filter_by(
        organization_id=current_user.organization_id
    ).order_by(KpiDashboardConfig.name.asc()).all()

    return jsonify([{
        'id': c.id,
        'name': c.name,
        'kpi_type': c.kpi_type,
        'columns': c.columns,
        'is_default': c.is_default,
        'boxes': [{
            'id': b.id,
            'name': b.name,
            'position_x': b.position_x,
            'position_y': b.position_y,
            'width': b.width,
            'height': b.height,
            'graph_type': b.graph_type,
            'kpi_metric': b.kpi_metric,
            'data_config': json.loads(b.data_config_json) if b.data_config_json else {},
            'time_filter': json.loads(b.time_filter_json) if b.time_filter_json else {}
        } for b in c.boxes.all()]
    } for c in configs])


@reporting_bp.route('/api/dashboard-configs', methods=['POST'])
@login_required
@require_permission('reporting.view')
def api_save_dashboard_config():
    """Dashboard-Konfiguration speichern"""
    data = request.get_json()
    org_id = current_user.organization_id

    config_id = data.get('id')
    if config_id:
        config = KpiDashboardConfig.query.get(config_id)
        if not config or config.organization_id != org_id:
            return jsonify({'error': 'Nicht gefunden.'}), 404
    else:
        config = KpiDashboardConfig(
            organization_id=org_id,
            user_id=current_user.id
        )
        db.session.add(config)

    config.name = data.get('name', 'Neues Dashboard')
    config.kpi_type = data.get('kpi_type', 'controlling')
    config.columns = data.get('columns', 4)
    config.is_default = data.get('is_default', False)

    # Boxen aktualisieren
    if 'boxes' in data:
        # Bestehende Boxen entfernen
        KpiBoxDefinition.query.filter_by(dashboard_id=config.id).delete() if config.id else None
        db.session.flush()

        for box_data in data['boxes']:
            box = KpiBoxDefinition(
                dashboard_id=config.id,
                name=box_data.get('name', ''),
                position_x=box_data.get('position_x', 0),
                position_y=box_data.get('position_y', 0),
                width=box_data.get('width', 1),
                height=box_data.get('height', 1),
                graph_type=box_data.get('graph_type', 'number'),
                kpi_metric=box_data.get('kpi_metric', ''),
                data_config_json=json.dumps(box_data.get('data_config', {})),
                time_filter_json=json.dumps(box_data.get('time_filter', {}))
            )
            db.session.add(box)

    db.session.commit()
    return jsonify({'success': True, 'id': config.id})


@reporting_bp.route('/api/dashboard-configs/<int:config_id>', methods=['DELETE'])
@login_required
@require_permission('reporting.view')
def api_delete_dashboard_config(config_id):
    """Dashboard-Konfiguration loeschen"""
    config = KpiDashboardConfig.query.get(config_id)
    if not config or config.organization_id != current_user.organization_id:
        return jsonify({'error': 'Nicht gefunden.'}), 404

    db.session.delete(config)
    db.session.commit()
    return jsonify({'success': True})


# ============================================================
# Cenplex KPI-API
# ============================================================

@reporting_bp.route('/api/kpi', methods=['POST'])
@login_required
@require_permission('reporting.view')
def api_kpi():
    """API: KPI-Daten abrufen (Cenplex-kompatibel)"""
    from services.reporting_service import get_kpi_data

    data = request.get_json()
    kpi_type = data.get('kpi_type', 'appointments')
    date_from = datetime.strptime(data['date_from'], '%Y-%m-%d') if data.get('date_from') else datetime.now().replace(day=1)
    date_to = datetime.strptime(data['date_to'], '%Y-%m-%d') if data.get('date_to') else datetime.now()

    result = get_kpi_data(
        org_id=current_user.organization_id,
        kpi_type=kpi_type,
        date_from=date_from,
        date_to=date_to,
        location_id=data.get('location_id'),
        employee_id=data.get('employee_id')
    )

    return jsonify(result)


# ============================================================
# Cenplex Phase 14: KPI Dashboard
# ============================================================

@reporting_bp.route('/api/kpi-dashboard')
@login_required
def api_kpi_dashboard():
    """KPI-Dashboard Daten (Cenplex: KPI PerformanceIndicator)"""
    from models import Appointment, Invoice, Patient, TreatmentSeries, Employee
    org_id = current_user.organization_id

    period_str = request.args.get('period', 'month')  # month, quarter, year
    today = date.today()

    if period_str == 'year':
        start_date = today.replace(month=1, day=1)
    elif period_str == 'quarter':
        quarter_start = ((today.month - 1) // 3) * 3 + 1
        start_date = today.replace(month=quarter_start, day=1)
    else:
        start_date = today.replace(day=1)

    start_dt = datetime.combine(start_date, time.min)
    end_dt = datetime.combine(today, time.max)

    # Termine
    total_appointments = Appointment.query.filter(
        Appointment.employee.has(organization_id=org_id),
        Appointment.start_time.between(start_dt, end_dt),
        Appointment.status.notin_(['cancelled'])
    ).count()

    cancelled = Appointment.query.filter(
        Appointment.employee.has(organization_id=org_id),
        Appointment.start_time.between(start_dt, end_dt),
        Appointment.status == 'cancelled'
    ).count()

    no_shows = Appointment.query.filter(
        Appointment.employee.has(organization_id=org_id),
        Appointment.start_time.between(start_dt, end_dt),
        Appointment.status == 'no_show'
    ).count()

    # Umsatz
    revenue = db.session.query(
        func.sum(Invoice.amount_total)
    ).filter(
        Invoice.organization_id == org_id,
        Invoice.status.in_(['sent', 'paid']),
        Invoice.created_at.between(start_dt, end_dt)
    ).scalar() or 0

    open_amount = db.session.query(
        func.sum(Invoice.amount_open)
    ).filter(
        Invoice.organization_id == org_id,
        Invoice.status.in_(['sent', 'overdue']),
        Invoice.amount_open > 0
    ).scalar() or 0

    # Neue Patienten
    new_patients = Patient.query.filter_by(organization_id=org_id).filter(
        Patient.created_at.between(start_dt, end_dt)
    ).count()

    # Aktive Serien
    active_series = TreatmentSeries.query.filter_by(status='active').filter(
        TreatmentSeries.patient.has(organization_id=org_id)
    ).count()

    # Durchschnittliche Auslastung pro Therapeut
    therapists = Employee.query.filter_by(organization_id=org_id, is_active=True).all()
    utilization = {}
    for t in therapists:
        if t.user and t.user.role == 'therapist':
            appts = Appointment.query.filter_by(employee_id=t.id).filter(
                Appointment.start_time.between(start_dt, end_dt),
                Appointment.status.notin_(['cancelled', 'no_show'])
            ).count()
            utilization[t.id] = {
                'name': f'{t.user.first_name} {t.user.last_name}' if t.user else '',
                'appointments': appts
            }

    return jsonify({
        'period': period_str,
        'start_date': start_date.isoformat(),
        'end_date': today.isoformat(),
        'kpis': {
            'total_appointments': total_appointments,
            'cancelled_appointments': cancelled,
            'no_shows': no_shows,
            'cancellation_rate': round(cancelled / max(total_appointments + cancelled, 1) * 100, 1),
            'revenue': float(revenue),
            'open_amount': float(open_amount),
            'new_patients': new_patients,
            'active_series': active_series,
            'therapist_utilization': utilization
        }
    })


# ============================================================
# Ausdrucke (Cenplex: Reports/PrintCases)
# ============================================================

@reporting_bp.route('/ausdrucke')
@login_required
@require_permission('reporting.view')
def ausdrucke():
    """Uebersichtsseite fuer alle Ausdrucke"""
    org_id = current_user.organization_id
    employees = Employee.query.filter_by(organization_id=org_id, is_active=True).all()
    locations = Location.query.filter_by(organization_id=org_id, is_active=True).all()
    return render_template('reporting/ausdrucke.html', employees=employees, locations=locations)


# ============================================================
# Tagesplan-Druck (Cenplex: DayPlanReport)
# ============================================================

@reporting_bp.route('/tagesplan')
@login_required
@require_permission('reporting.view')
def tagesplan():
    """Tagesplan-Druckansicht fuer einen Therapeuten"""
    org_id = current_user.organization_id
    employee_id = request.args.get('employee_id', type=int)
    day_str = request.args.get('date', date.today().isoformat())

    try:
        day = date.fromisoformat(day_str)
    except ValueError:
        day = date.today()

    employees = Employee.query.filter_by(organization_id=org_id, is_active=True).all()
    employee = None
    appointments = []

    if employee_id:
        employee = Employee.query.get(employee_id)
        if employee and employee.organization_id != org_id:
            abort(403)
        if employee:
            day_start = datetime.combine(day, time.min)
            day_end = datetime.combine(day, time.max)
            appointments = Appointment.query.filter(
                Appointment.employee_id == employee_id,
                Appointment.start_time.between(day_start, day_end),
                Appointment.status != 'cancelled'
            ).order_by(Appointment.start_time.asc()).all()

    org = Organization.query.get(org_id)
    # Wochentag auf Deutsch
    weekdays_de = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']
    formatted_day = f"{weekdays_de[day.weekday()]} {day.strftime('%d.%m.%Y')}"

    return render_template('reporting/tagesplan.html',
                           employees=employees, employee=employee,
                           appointments=appointments, day=day,
                           formatted_day=formatted_day, org=org)


# ============================================================
# Wochenplan-Druck (Cenplex: WeekWorkSheduleReport)
# ============================================================

@reporting_bp.route('/wochenplan')
@login_required
@require_permission('reporting.view')
def wochenplan():
    """Wochenplan-Druckansicht fuer einen Therapeuten"""
    org_id = current_user.organization_id
    employee_id = request.args.get('employee_id', type=int)
    day_str = request.args.get('date', date.today().isoformat())

    try:
        ref_day = date.fromisoformat(day_str)
    except ValueError:
        ref_day = date.today()

    # Montag der Woche berechnen
    week_start = ref_day - timedelta(days=ref_day.weekday())
    week_end = week_start + timedelta(days=6)

    employees = Employee.query.filter_by(organization_id=org_id, is_active=True).all()
    employee = None
    week_data = {}

    if employee_id:
        employee = Employee.query.get(employee_id)
        if employee and employee.organization_id != org_id:
            abort(403)
        if employee:
            start_dt = datetime.combine(week_start, time.min)
            end_dt = datetime.combine(week_end, time.max)
            appts = Appointment.query.filter(
                Appointment.employee_id == employee_id,
                Appointment.start_time.between(start_dt, end_dt),
                Appointment.status != 'cancelled'
            ).order_by(Appointment.start_time.asc()).all()

            weekdays_de = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag']
            for i in range(7):
                d = week_start + timedelta(days=i)
                day_appts = [a for a in appts if a.start_time.date() == d]
                week_data[i] = {
                    'date': d,
                    'weekday': weekdays_de[i],
                    'formatted': f"{weekdays_de[i]}, {d.strftime('%d.%m.%Y')}",
                    'appointments': day_appts
                }

    org = Organization.query.get(org_id)
    kw = week_start.isocalendar()[1]

    return render_template('reporting/wochenplan.html',
                           employees=employees, employee=employee,
                           week_data=week_data, week_start=week_start,
                           week_end=week_end, kw=kw, org=org)


# ============================================================
# Arztbericht (Cenplex: DoctorReport)
# ============================================================

@reporting_bp.route('/arztbericht')
@login_required
@require_permission('reporting.view')
def arztbericht():
    """Arztbericht erstellen und drucken"""
    org_id = current_user.organization_id
    series_id = request.args.get('series_id', type=int)

    series = None
    patient = None
    doctor = None
    appointments = []
    findings = []
    plan = None

    if series_id:
        series = TreatmentSeries.query.get(series_id)
        if series:
            patient = Patient.query.get(series.patient_id)
            if patient and patient.organization_id != org_id:
                abort(403)
            if series.prescribing_doctor_id:
                doctor = Doctor.query.get(series.prescribing_doctor_id)
            appointments = Appointment.query.filter_by(
                series_id=series_id
            ).filter(
                Appointment.status.in_(['completed', 'scheduled'])
            ).order_by(Appointment.start_time.asc()).all()
            findings = ClinicalFinding.query.filter_by(
                series_id=series_id
            ).order_by(ClinicalFinding.created_at.desc()).all()
            # Behandlungsplan
            plan = TreatmentPlan.query.filter_by(
                series_id=series_id, is_deleted=False
            ).first()

    org = Organization.query.get(org_id)

    # Alle aktiven Serien laden fuer Auswahl
    active_series = TreatmentSeries.query.filter(
        TreatmentSeries.status.in_(['active', 'completed']),
        TreatmentSeries.patient.has(organization_id=org_id)
    ).order_by(TreatmentSeries.created_at.desc()).limit(100).all()

    return render_template('reporting/arztbericht.html',
                           series=series, patient=patient, doctor=doctor,
                           appointments=appointments, findings=findings,
                           plan=plan, org=org, active_series=active_series)


# ============================================================
# Ferienkalender (Cenplex: VacationCalendarReport)
# ============================================================

@reporting_bp.route('/ferienkalender')
@login_required
@require_permission('reporting.view')
def ferienkalender():
    """Ferienkalender drucken"""
    org_id = current_user.organization_id
    year = request.args.get('year', date.today().year, type=int)
    location_id = request.args.get('location_id', type=int)

    # Feiertage und Ferien laden
    query = Holiday.query.filter_by(organization_id=org_id)
    if location_id:
        query = query.filter(db.or_(Holiday.location_id == location_id, Holiday.is_global == True))
    else:
        query = query.filter(Holiday.is_global == True)

    holidays = query.filter(
        db.or_(
            db.and_(Holiday.date >= date(year, 1, 1), Holiday.date <= date(year, 12, 31)),
            db.and_(Holiday.is_yearly == True)
        )
    ).order_by(Holiday.date.asc()).all()

    # Monate aufbereiten
    months = []
    weekdays_de = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']
    month_names = ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
                   'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember']

    # Holiday-Daten als Set fuer schnellen Lookup
    holiday_dates = set()
    holiday_map = {}
    for h in holidays:
        if h.end_date:
            d = h.date
            while d <= h.end_date:
                if d.year == year:
                    holiday_dates.add(d)
                    holiday_map[d] = h.name
                d += timedelta(days=1)
        else:
            actual_date = h.date
            if h.is_yearly and actual_date.year != year:
                actual_date = actual_date.replace(year=year)
            holiday_dates.add(actual_date)
            holiday_map[actual_date] = h.name

    for m in range(1, 13):
        days_in_month = monthrange(year, m)[1]
        days = []
        for d in range(1, days_in_month + 1):
            dt = date(year, m, d)
            days.append({
                'day': d,
                'date': dt,
                'weekday': weekdays_de[dt.weekday()],
                'is_weekend': dt.weekday() >= 5,
                'is_holiday': dt in holiday_dates,
                'holiday_name': holiday_map.get(dt, ''),
            })
        months.append({
            'number': m,
            'name': month_names[m - 1],
            'days': days
        })

    org = Organization.query.get(org_id)
    locations = Location.query.filter_by(organization_id=org_id, is_active=True).all()

    return render_template('reporting/ferienkalender.html',
                           months=months, holidays=holidays, year=year,
                           org=org, locations=locations, location_id=location_id)


# ============================================================
# Behandlungsbericht (Cenplex: TreatmentReport)
# ============================================================

@reporting_bp.route('/behandlungsbericht')
@login_required
@require_permission('reporting.view')
def behandlungsbericht():
    """Behandlungsbericht erstellen und drucken"""
    org_id = current_user.organization_id
    series_id = request.args.get('series_id', type=int)

    series = None
    patient = None
    therapist = None
    appointments = []
    findings = []
    plan = None

    if series_id:
        series = TreatmentSeries.query.get(series_id)
        if series:
            patient = Patient.query.get(series.patient_id)
            if patient and patient.organization_id != org_id:
                abort(403)
            if series.therapist_id:
                therapist = Employee.query.get(series.therapist_id)
            appointments = Appointment.query.filter_by(
                series_id=series_id
            ).filter(
                Appointment.status.in_(['completed', 'scheduled'])
            ).order_by(Appointment.start_time.asc()).all()
            findings = ClinicalFinding.query.filter_by(
                series_id=series_id
            ).order_by(ClinicalFinding.created_at.asc()).all()
            plan = TreatmentPlan.query.filter_by(
                series_id=series_id, is_deleted=False
            ).first()

    org = Organization.query.get(org_id)

    # Aktive Serien fuer Auswahl
    active_series = TreatmentSeries.query.filter(
        TreatmentSeries.status.in_(['active', 'completed']),
        TreatmentSeries.patient.has(organization_id=org_id)
    ).order_by(TreatmentSeries.created_at.desc()).limit(100).all()

    return render_template('reporting/behandlungsbericht.html',
                           series=series, patient=patient, therapist=therapist,
                           appointments=appointments, findings=findings,
                           plan=plan, org=org, active_series=active_series)


# ============================================================
# Rechnungsdruck mit Sprachauswahl DE/FR/IT (Cenplex: InvoiceReportHelper)
# ============================================================

INVOICE_LABELS = {
    'de': {
        'title': 'Rechnung',
        'invoice_number': 'Rechnungsnummer',
        'date': 'Rechnungsdatum',
        'due_date': 'Fällig am',
        'insurance': 'Versicherung',
        'billing_type': 'Typ',
        'billing_model': 'Abrechnungsmodell',
        'tiers_garant': 'Tiers Garant',
        'tiers_payant': 'Tiers Payant',
        'position': 'Pos.',
        'tariff_code': 'Tarifziffer',
        'description': 'Beschreibung',
        'quantity': 'Anzahl',
        'tax_points': 'TP',
        'tp_value': 'TP-Wert',
        'amount': 'Betrag CHF',
        'vat': 'MwSt %',
        'subtotal': 'Subtotal',
        'vat_label': 'MwSt',
        'total': 'Total',
        'paid': 'Bezahlt',
        'open': 'Offen',
        'payment_note': 'Zahlbar innert {days} Tagen. Vielen Dank für Ihr Vertrauen.',
        'qr_title': 'QR-Einzahlungsschein',
        'reminder': 'Zahlungserinnerung',
        'copy': 'Kopie',
        'treatment_period': 'Behandlungszeitraum',
        'patient': 'Patient/in',
        'therapist': 'Therapeut/in',
    },
    'fr': {
        'title': 'Facture',
        'invoice_number': 'Numéro de facture',
        'date': 'Date de facture',
        'due_date': 'Échéance',
        'insurance': 'Assurance',
        'billing_type': 'Type',
        'billing_model': 'Modèle de facturation',
        'tiers_garant': 'Tiers Garant',
        'tiers_payant': 'Tiers Payant',
        'position': 'Pos.',
        'tariff_code': 'Code tarif',
        'description': 'Description',
        'quantity': 'Quantité',
        'tax_points': 'PT',
        'tp_value': 'Val. PT',
        'amount': 'Montant CHF',
        'vat': 'TVA %',
        'subtotal': 'Sous-total',
        'vat_label': 'TVA',
        'total': 'Total',
        'paid': 'Payé',
        'open': 'Solde',
        'payment_note': 'Payable dans les {days} jours. Merci de votre confiance.',
        'qr_title': 'Bulletin de versement QR',
        'reminder': 'Rappel de paiement',
        'copy': 'Copie',
        'treatment_period': 'Période de traitement',
        'patient': 'Patient/e',
        'therapist': 'Thérapeute',
    },
    'it': {
        'title': 'Fattura',
        'invoice_number': 'Numero fattura',
        'date': 'Data fattura',
        'due_date': 'Scadenza',
        'insurance': 'Assicurazione',
        'billing_type': 'Tipo',
        'billing_model': 'Modello di fatturazione',
        'tiers_garant': 'Tiers Garant',
        'tiers_payant': 'Tiers Payant',
        'position': 'Pos.',
        'tariff_code': 'Codice tariffa',
        'description': 'Descrizione',
        'quantity': 'Quantità',
        'tax_points': 'PT',
        'tp_value': 'Val. PT',
        'amount': 'Importo CHF',
        'vat': 'IVA %',
        'subtotal': 'Subtotale',
        'vat_label': 'IVA',
        'total': 'Totale',
        'paid': 'Pagato',
        'open': 'Scoperto',
        'payment_note': 'Pagabile entro {days} giorni. Grazie per la vostra fiducia.',
        'qr_title': 'Polizza di versamento QR',
        'reminder': 'Sollecito di pagamento',
        'copy': 'Copia',
        'treatment_period': 'Periodo di trattamento',
        'patient': 'Paziente',
        'therapist': 'Terapeuta',
    }
}


@reporting_bp.route('/rechnung/<int:invoice_id>/print')
@login_required
@require_permission('billing.view')
def rechnung_print(invoice_id):
    """Rechnungs-Druckansicht mit Sprachauswahl (Cenplex: InvoiceReport DE/FR/IT)"""
    org_id = current_user.organization_id
    invoice = Invoice.query.get_or_404(invoice_id)
    if invoice.organization_id != org_id:
        abort(403)

    lang = request.args.get('lang', 'de')
    is_copy = request.args.get('copy', '0') == '1'
    is_reminder = request.args.get('reminder', '0') == '1'

    if lang not in INVOICE_LABELS:
        lang = 'de'
    labels = INVOICE_LABELS[lang]

    patient = Patient.query.get(invoice.patient_id) if invoice.patient_id else None
    items = InvoiceItem.query.filter_by(invoice_id=invoice_id).order_by(InvoiceItem.position).all()
    org = Organization.query.get(org_id)

    # Behandlungszeitraum berechnen (Cenplex: TreatmentPeriod)
    treatment_period = ''
    if items:
        dates = [i.valuta_date for i in items if i.valuta_date]
        if dates:
            treatment_period = f"{min(dates).strftime('%d.%m.%Y')} - {max(dates).strftime('%d.%m.%Y')}"

    # Therapeut ermitteln
    therapist = None
    if invoice.series_id:
        series = TreatmentSeries.query.get(invoice.series_id)
        if series and series.therapist_id:
            therapist = Employee.query.get(series.therapist_id)

    # Summen
    subtotal = sum(i.amount for i in items)
    total_vat = sum(i.vat_amount or 0 for i in items)

    return render_template('reporting/rechnung_print.html',
                           invoice=invoice, patient=patient, items=items,
                           org=org, labels=labels, lang=lang,
                           is_copy=is_copy, is_reminder=is_reminder,
                           treatment_period=treatment_period,
                           therapist=therapist, subtotal=subtotal,
                           total_vat=total_vat)
