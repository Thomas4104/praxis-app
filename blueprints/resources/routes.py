from datetime import datetime, timedelta, date, time
from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from blueprints.resources import resources_bp
from models import db, Resource, ResourceBooking, MaintenanceRecord, Location, Appointment, Employee, User
from utils.auth import check_org


@resources_bp.route('/')
@login_required
def index():
    """Ressourcenuebersicht mit Tabs fuer Raeume und Geraete"""
    tab = request.args.get('tab', 'rooms')
    location_filter = request.args.get('location', '')
    status = request.args.get('status', 'active')

    query = Resource.query.filter_by(organization_id=current_user.organization_id)

    # Tab-Filter
    if tab == 'rooms':
        query = query.filter(Resource.resource_type.in_(['room', 'Behandlungsraum', 'Trainingsraum', 'Gruppenraum']))
    elif tab == 'devices':
        query = query.filter(Resource.resource_type.in_(['device', 'Geraet', 'Fahrzeug', 'Sonstiges']))

    # Status-Filter
    if status == 'active':
        query = query.filter_by(is_active=True)
    elif status == 'inactive':
        query = query.filter_by(is_active=False)

    # Standort-Filter
    if location_filter:
        try:
            query = query.filter_by(location_id=int(location_filter))
        except ValueError:
            pass

    resources = query.order_by(Resource.name).all()
    locations = Location.query.filter_by(
        organization_id=current_user.organization_id,
        is_active=True
    ).all()

    # Wartungsinformationen fuer Geraete
    overdue_maintenance = []
    if tab == 'devices':
        for r in resources:
            latest = MaintenanceRecord.query.filter_by(
                resource_id=r.id
            ).order_by(MaintenanceRecord.performed_at.desc()).first()
            if latest and latest.next_due and latest.next_due < date.today():
                overdue_maintenance.append(r.id)

    return render_template('resources/index.html',
                           resources=resources,
                           locations=locations,
                           tab=tab,
                           location_filter=location_filter,
                           status=status,
                           overdue_maintenance=overdue_maintenance)


@resources_bp.route('/new', methods=['GET', 'POST'])
@login_required
def create():
    """Neue Ressource erstellen"""
    if request.method == 'POST':
        return _save_resource(None)

    locations = Location.query.filter_by(
        organization_id=current_user.organization_id,
        is_active=True
    ).all()
    return render_template('resources/form.html', resource=None, locations=locations)


@resources_bp.route('/<int:resource_id>')
@login_required
def detail(resource_id):
    """Ressource-Detailansicht"""
    resource = Resource.query.get_or_404(resource_id)
    check_org(resource)

    # Wartungshistorie (nur fuer Geraete)
    maintenance_records = []
    latest_maintenance = None
    if resource.resource_type in ('device', 'Geraet', 'Fahrzeug'):
        maintenance_records = MaintenanceRecord.query.filter_by(
            resource_id=resource_id
        ).order_by(MaintenanceRecord.performed_at.desc()).all()
        latest_maintenance = maintenance_records[0] if maintenance_records else None

    return render_template('resources/detail.html',
                           resource=resource,
                           maintenance_records=maintenance_records,
                           latest_maintenance=latest_maintenance)


@resources_bp.route('/<int:resource_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(resource_id):
    """Ressource bearbeiten"""
    resource = Resource.query.get_or_404(resource_id)
    check_org(resource)

    if request.method == 'POST':
        return _save_resource(resource)

    locations = Location.query.filter_by(
        organization_id=current_user.organization_id,
        is_active=True
    ).all()
    return render_template('resources/form.html', resource=resource, locations=locations)


@resources_bp.route('/<int:resource_id>/toggle', methods=['POST'])
@login_required
def toggle_active(resource_id):
    """Ressource aktivieren/deaktivieren"""
    resource = Resource.query.get_or_404(resource_id)
    check_org(resource)
    resource.is_active = not resource.is_active
    db.session.commit()

    status_text = 'aktiviert' if resource.is_active else 'deaktiviert'
    flash(f'Ressource "{resource.name}" wurde {status_text}.', 'success')
    return redirect(url_for('resources.index'))


@resources_bp.route('/<int:resource_id>/maintenance', methods=['POST'])
@login_required
def add_maintenance(resource_id):
    """Wartungseintrag hinzufuegen"""
    resource = Resource.query.get_or_404(resource_id)
    check_org(resource)

    performed_at_str = request.form.get('performed_at', '')
    try:
        performed_at = datetime.strptime(performed_at_str, '%Y-%m-%d').date()
    except ValueError:
        performed_at = date.today()

    interval_months = 0
    try:
        interval_months = int(request.form.get('interval_months', '0'))
    except ValueError:
        pass

    next_due = None
    if interval_months > 0:
        # Naechste Wartung berechnen
        next_due_month = performed_at.month + interval_months
        next_due_year = performed_at.year + (next_due_month - 1) // 12
        next_due_month = ((next_due_month - 1) % 12) + 1
        try:
            next_due = performed_at.replace(year=next_due_year, month=next_due_month)
        except ValueError:
            # Fuer Monatstage die nicht existieren (z.B. 31. Februar)
            import calendar
            last_day = calendar.monthrange(next_due_year, next_due_month)[1]
            next_due = performed_at.replace(year=next_due_year, month=next_due_month, day=min(performed_at.day, last_day))

    record = MaintenanceRecord(
        resource_id=resource.id,
        maintenance_type=request.form.get('maintenance_type', 'regular'),
        description=request.form.get('description', '').strip(),
        performed_at=performed_at,
        performed_by=request.form.get('performed_by', '').strip(),
        next_due=next_due,
        interval_months=interval_months if interval_months > 0 else None,
        notes=request.form.get('notes', '').strip()
    )
    db.session.add(record)
    db.session.commit()

    flash('Wartungseintrag wurde gespeichert.', 'success')
    return redirect(url_for('resources.detail', resource_id=resource.id))


@resources_bp.route('/calendar')
@login_required
def calendar():
    """Ressourcen-Kalender (Wochenansicht)"""
    resource_id = request.args.get('resource_id', type=int)
    week_offset = request.args.get('week', 0, type=int)

    # Wochenanfang berechnen (Montag)
    today = date.today()
    week_start = today - timedelta(days=today.weekday()) + timedelta(weeks=week_offset)
    week_end = week_start + timedelta(days=6)

    # Alle Ressourcen laden
    resources = Resource.query.filter_by(
        organization_id=current_user.organization_id,
        is_active=True
    ).filter(
        Resource.resource_type.in_(['room', 'Behandlungsraum', 'Trainingsraum', 'Gruppenraum'])
    ).order_by(Resource.name).all()

    selected_resource = None
    bookings = []
    hours = list(range(7, 20))  # 07:00 - 19:00

    if resource_id:
        selected_resource = Resource.query.get(resource_id)
        if selected_resource:
            check_org(selected_resource)
    elif resources:
        selected_resource = resources[0]
        resource_id = selected_resource.id

    if selected_resource:
        # Termine laden die diese Ressource nutzen
        week_start_dt = datetime.combine(week_start, time(0, 0))
        week_end_dt = datetime.combine(week_end, time(23, 59))

        # Direkte Ressourcen-Buchungen
        resource_bookings = ResourceBooking.query.filter(
            ResourceBooking.resource_id == resource_id,
            ResourceBooking.start_time >= week_start_dt,
            ResourceBooking.end_time <= week_end_dt
        ).all()

        # Termine mit dieser Ressource
        appointments = Appointment.query.filter(
            Appointment.resource_id == resource_id,
            Appointment.start_time >= week_start_dt,
            Appointment.end_time <= week_end_dt,
            Appointment.status.in_(['scheduled', 'confirmed'])
        ).all()

        for appt in appointments:
            therapist_name = ''
            color = '#4a90d9'
            if appt.employee and appt.employee.user:
                therapist_name = f'{appt.employee.user.first_name} {appt.employee.user.last_name}'
                color = appt.employee.color_code or '#4a90d9'

            bookings.append({
                'day': appt.start_time.weekday(),
                'start_hour': appt.start_time.hour,
                'start_minute': appt.start_time.minute,
                'end_hour': appt.end_time.hour,
                'end_minute': appt.end_time.minute,
                'title': appt.title or 'Termin',
                'patient': f'{appt.patient.first_name} {appt.patient.last_name}' if appt.patient else '',
                'therapist': therapist_name,
                'color': color
            })

    # Wochentage berechnen
    weekdays = []
    day_names = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']
    for i in range(7):
        d = week_start + timedelta(days=i)
        weekdays.append({
            'name': day_names[i],
            'date': d,
            'formatted': d.strftime('%d.%m.'),
            'is_today': d == today
        })

    return render_template('resources/calendar.html',
                           resources=resources,
                           selected_resource=selected_resource,
                           resource_id=resource_id,
                           bookings=bookings,
                           hours=hours,
                           weekdays=weekdays,
                           week_offset=week_offset,
                           week_start=week_start,
                           week_end=week_end)


def _save_resource(resource):
    """Speichert eine Ressource (neu oder bestehend)"""
    name = request.form.get('name', '').strip()
    location_id = request.form.get('location_id', '')

    # Validierung
    errors = []
    if not name:
        errors.append('Name ist ein Pflichtfeld.')
    if not location_id:
        errors.append('Standort ist ein Pflichtfeld.')

    if errors:
        for error in errors:
            flash(error, 'error')
        locations = Location.query.filter_by(
            organization_id=current_user.organization_id,
            is_active=True
        ).all()
        return render_template('resources/form.html', resource=resource, locations=locations)

    is_new = resource is None
    if is_new:
        resource = Resource(organization_id=current_user.organization_id)

    resource.name = name
    resource.resource_type = request.form.get('resource_type', 'room')
    resource.location_id = int(location_id)
    resource.description = request.form.get('description', '').strip()

    try:
        resource.capacity = int(request.form.get('capacity', '1'))
    except ValueError:
        resource.capacity = 1

    # Ausstattung als JSON
    equipment = request.form.getlist('equipment')
    if equipment:
        import json
        resource.equipment_json = json.dumps(equipment)

    resource.is_active = request.form.get('is_active') == 'on'

    if is_new:
        db.session.add(resource)

    db.session.commit()

    flash(f'Ressource "{resource.name}" wurde erfolgreich gespeichert.', 'success')
    return redirect(url_for('resources.detail', resource_id=resource.id))
