import json
import os
from datetime import datetime, timedelta, date, time
from flask import render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from blueprints.resources import resources_bp
from models import db, Resource, ResourceBooking, MaintenanceRecord, Location, Appointment, Employee, User
from utils.auth import check_org


# Erlaubte Bild-Dateitypen
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}


def _allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@resources_bp.route('/')
@login_required
def index():
    """Ressourcenuebersicht mit Tabs, Suche, Gruppierung"""
    tab = request.args.get('tab', 'rooms')
    location_filter = request.args.get('location', '')
    status = request.args.get('status', 'active')
    search = request.args.get('search', '').strip()

    query = Resource.query.filter_by(organization_id=current_user.organization_id)

    # Tab-Filter
    room_types = ['room', 'Behandlungsraum', 'Trainingsraum', 'Gruppenraum']
    device_types = ['device', 'Geraet', 'Fahrzeug', 'Sonstiges']
    if tab == 'rooms':
        query = query.filter(Resource.resource_type.in_(room_types))
    elif tab == 'devices':
        query = query.filter(Resource.resource_type.in_(device_types))

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

    # Textsuche (Cenplex: Mehrwort, alle Begriffe muessen matchen)
    if search:
        terms = search.lower().split()
        for term in terms:
            query = query.filter(
                db.or_(
                    db.func.lower(Resource.name).contains(term),
                    db.func.lower(Resource.description).contains(term)
                )
            )

    resources = query.order_by(Resource.resource_type, Resource.name).all()
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

    # Gruppierung nach Typ fuer Anzeige
    grouped_resources = {}
    type_labels = {
        'room': 'Behandlungsraum', 'Behandlungsraum': 'Behandlungsraum',
        'Trainingsraum': 'Trainingsraum', 'Gruppenraum': 'Gruppenraum',
        'device': 'Geraet', 'Geraet': 'Geraet',
        'Fahrzeug': 'Fahrzeug', 'Sonstiges': 'Sonstiges'
    }
    for r in resources:
        label = type_labels.get(r.resource_type, r.resource_type)
        if label not in grouped_resources:
            grouped_resources[label] = []
        grouped_resources[label].append(r)

    return render_template('resources/index.html',
                           resources=resources,
                           grouped_resources=grouped_resources,
                           locations=locations,
                           tab=tab,
                           location_filter=location_filter,
                           status=status,
                           search=search,
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
    """Ressource-Detailansicht mit eingebettetem Wochenkalender"""
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

    # Ausstattung als Liste parsen
    equipment_list = []
    if resource.equipment_json:
        try:
            equipment_list = json.loads(resource.equipment_json)
        except (json.JSONDecodeError, TypeError):
            equipment_list = []

    # Blockierte Zeiten parsen
    blocked_times = []
    if resource.blocked_timeschedule_json:
        try:
            blocked_times = json.loads(resource.blocked_timeschedule_json)
        except (json.JSONDecodeError, TypeError):
            blocked_times = []

    # Eingebetteter Wochenkalender (wie Cenplex AppointmentWeekControl)
    week_offset = request.args.get('week', 0, type=int)
    today = date.today()
    week_start = today - timedelta(days=today.weekday()) + timedelta(weeks=week_offset)
    week_end = week_start + timedelta(days=6)

    week_start_dt = datetime.combine(week_start, time(0, 0))
    week_end_dt = datetime.combine(week_end, time(23, 59))

    # Termine fuer diese Ressource laden
    bookings = []
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

        duration_min = int((appt.end_time - appt.start_time).total_seconds() / 60)
        # Serieninfo (wie Cenplex: Position/SeriesCount)
        series_info = therapist_name
        if hasattr(appt, 'series_position') and appt.series_position and hasattr(appt, 'series_count') and appt.series_count:
            series_info = f'{appt.series_position}/{appt.series_count}'

        bookings.append({
            'day': appt.start_time.weekday(),
            'start_hour': appt.start_time.hour,
            'start_minute': appt.start_time.minute,
            'end_hour': appt.end_time.hour,
            'end_minute': appt.end_time.minute,
            'duration': duration_min,
            'title': appt.title or 'Termin',
            'patient': f'{appt.patient.first_name} {appt.patient.last_name}' if appt.patient else '',
            'therapist': therapist_name,
            'series_info': series_info,
            'color': color,
            'is_small': duration_min < 40
        })

    # Direkte Buchungen
    resource_bookings = ResourceBooking.query.filter(
        ResourceBooking.resource_id == resource_id,
        ResourceBooking.start_time >= week_start_dt,
        ResourceBooking.end_time <= week_end_dt
    ).all()

    for rb in resource_bookings:
        duration_min = int((rb.end_time - rb.start_time).total_seconds() / 60)
        bookings.append({
            'day': rb.start_time.weekday(),
            'start_hour': rb.start_time.hour,
            'start_minute': rb.start_time.minute,
            'end_hour': rb.end_time.hour,
            'end_minute': rb.end_time.minute,
            'duration': duration_min,
            'title': 'Buchung',
            'patient': '',
            'therapist': '',
            'series_info': '',
            'color': '#6c757d',
            'is_small': duration_min < 40
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

    hours = list(range(7, 20))

    return render_template('resources/detail.html',
                           resource=resource,
                           maintenance_records=maintenance_records,
                           latest_maintenance=latest_maintenance,
                           equipment_list=equipment_list,
                           blocked_times=blocked_times,
                           bookings=bookings,
                           weekdays=weekdays,
                           hours=hours,
                           week_offset=week_offset,
                           week_start=week_start,
                           week_end=week_end,
                           today=today)


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

    # Blockierte Zeiten parsen fuer Formular
    blocked_times = []
    if resource.blocked_timeschedule_json:
        try:
            blocked_times = json.loads(resource.blocked_timeschedule_json)
        except (json.JSONDecodeError, TypeError):
            blocked_times = []

    return render_template('resources/form.html',
                           resource=resource,
                           locations=locations,
                           blocked_times=blocked_times)


@resources_bp.route('/<int:resource_id>/toggle', methods=['POST'])
@login_required
def toggle_active(resource_id):
    """Ressource aktivieren/deaktivieren (wie Cenplex ToggleResourceState)"""
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
        next_due_month = performed_at.month + interval_months
        next_due_year = performed_at.year + (next_due_month - 1) // 12
        next_due_month = ((next_due_month - 1) % 12) + 1
        try:
            next_due = performed_at.replace(year=next_due_year, month=next_due_month)
        except ValueError:
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


@resources_bp.route('/<int:resource_id>/blocked-times', methods=['POST'])
@login_required
def update_blocked_times(resource_id):
    """Blockierte Zeiten aktualisieren (Cenplex BlockedTimeschedule)"""
    resource = Resource.query.get_or_404(resource_id)
    check_org(resource)

    action = request.form.get('action', 'add')

    blocked_times = []
    if resource.blocked_timeschedule_json:
        try:
            blocked_times = json.loads(resource.blocked_timeschedule_json)
        except (json.JSONDecodeError, TypeError):
            blocked_times = []

    if action == 'add':
        day = request.form.get('block_day', '')
        start = request.form.get('block_start', '')
        end = request.form.get('block_end', '')
        reason = request.form.get('block_reason', '').strip()

        if day and start and end:
            blocked_times.append({
                'day': day,
                'start': start,
                'end': end,
                'reason': reason
            })
    elif action == 'remove':
        idx = request.form.get('block_index', '')
        try:
            idx = int(idx)
            if 0 <= idx < len(blocked_times):
                blocked_times.pop(idx)
        except (ValueError, IndexError):
            pass

    resource.blocked_timeschedule_json = json.dumps(blocked_times) if blocked_times else None

    # Gueltigkeitsdatum
    valid_until = request.form.get('valid_until', '')
    if valid_until:
        try:
            resource.blocked_timeschedule_valid_until = datetime.strptime(valid_until, '%Y-%m-%d').date()
        except ValueError:
            pass
    elif action == 'add' and not valid_until:
        resource.blocked_timeschedule_valid_until = None

    db.session.commit()
    flash('Blockierte Zeiten wurden aktualisiert.', 'success')
    return redirect(url_for('resources.detail', resource_id=resource.id))


@resources_bp.route('/<int:resource_id>/upload-image', methods=['POST'])
@login_required
def upload_image(resource_id):
    """Bild fuer Ressource hochladen (Cenplex EditImage/PictureDto)"""
    resource = Resource.query.get_or_404(resource_id)
    check_org(resource)

    if 'image' not in request.files:
        flash('Keine Datei ausgewaehlt.', 'error')
        return redirect(url_for('resources.edit', resource_id=resource.id))

    file = request.files['image']
    if file.filename == '':
        flash('Keine Datei ausgewaehlt.', 'error')
        return redirect(url_for('resources.edit', resource_id=resource.id))

    if file and _allowed_file(file.filename):
        filename = secure_filename(f'resource_{resource.id}_{file.filename}')
        upload_dir = os.path.join(current_app.static_folder, 'uploads', 'resources')
        os.makedirs(upload_dir, exist_ok=True)

        # Altes Bild loeschen
        if resource.picture_path:
            old_path = os.path.join(current_app.static_folder, resource.picture_path)
            if os.path.exists(old_path):
                os.remove(old_path)

        filepath = os.path.join(upload_dir, filename)
        file.save(filepath)
        resource.picture_path = f'uploads/resources/{filename}'
        db.session.commit()
        flash('Bild wurde hochgeladen.', 'success')
    else:
        flash('Ungültiges Dateiformat. Erlaubt: PNG, JPG, GIF, WebP', 'error')

    return redirect(url_for('resources.edit', resource_id=resource.id))


@resources_bp.route('/<int:resource_id>/remove-image', methods=['POST'])
@login_required
def remove_image(resource_id):
    """Bild entfernen"""
    resource = Resource.query.get_or_404(resource_id)
    check_org(resource)

    if resource.picture_path:
        old_path = os.path.join(current_app.static_folder, resource.picture_path)
        if os.path.exists(old_path):
            os.remove(old_path)
        resource.picture_path = None
        db.session.commit()
        flash('Bild wurde entfernt.', 'success')

    return redirect(url_for('resources.edit', resource_id=resource.id))


@resources_bp.route('/calendar')
@login_required
def calendar():
    """Ressourcen-Kalender (Wochenansicht) - alle Ressourcentypen"""
    resource_id = request.args.get('resource_id', type=int)
    week_offset = request.args.get('week', 0, type=int)

    today = date.today()
    week_start = today - timedelta(days=today.weekday()) + timedelta(weeks=week_offset)
    week_end = week_start + timedelta(days=6)

    # Alle aktiven Ressourcen (nicht nur Raeume - Cenplex zeigt alle)
    resources = Resource.query.filter_by(
        organization_id=current_user.organization_id,
        is_active=True
    ).order_by(Resource.resource_type, Resource.name).all()

    selected_resource = None
    bookings = []
    hours = list(range(7, 20))

    if resource_id:
        selected_resource = Resource.query.get(resource_id)
        if selected_resource:
            check_org(selected_resource)
    elif resources:
        selected_resource = resources[0]
        resource_id = selected_resource.id

    if selected_resource:
        week_start_dt = datetime.combine(week_start, time(0, 0))
        week_end_dt = datetime.combine(week_end, time(23, 59))

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

            duration_min = int((appt.end_time - appt.start_time).total_seconds() / 60)
            bookings.append({
                'day': appt.start_time.weekday(),
                'start_hour': appt.start_time.hour,
                'start_minute': appt.start_time.minute,
                'end_hour': appt.end_time.hour,
                'end_minute': appt.end_time.minute,
                'duration': duration_min,
                'title': appt.title or 'Termin',
                'patient': f'{appt.patient.first_name} {appt.patient.last_name}' if appt.patient else '',
                'therapist': therapist_name,
                'color': color,
                'is_small': duration_min < 40
            })

        # Direkte Buchungen
        resource_bookings = ResourceBooking.query.filter(
            ResourceBooking.resource_id == resource_id,
            ResourceBooking.start_time >= week_start_dt,
            ResourceBooking.end_time <= week_end_dt
        ).all()

        for rb in resource_bookings:
            duration_min = int((rb.end_time - rb.start_time).total_seconds() / 60)
            bookings.append({
                'day': rb.start_time.weekday(),
                'start_hour': rb.start_time.hour,
                'start_minute': rb.start_time.minute,
                'end_hour': rb.end_time.hour,
                'end_minute': rb.end_time.minute,
                'duration': duration_min,
                'title': 'Buchung',
                'patient': '',
                'therapist': '',
                'color': '#6c757d',
                'is_small': duration_min < 40
            })

    # Wochentage
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


@resources_bp.route('/api/availability')
@login_required
def api_availability():
    """API: Raumverfuegbarkeit pruefen (Cenplex RoomAvailability)"""
    resource_id = request.args.get('resource_id', type=int)
    check_date = request.args.get('date', '')

    if not resource_id:
        return jsonify({'error': 'resource_id erforderlich'}), 400

    resource = Resource.query.get_or_404(resource_id)
    check_org(resource)

    try:
        target_date = datetime.strptime(check_date, '%Y-%m-%d').date() if check_date else date.today()
    except ValueError:
        target_date = date.today()

    start_dt = datetime.combine(target_date, time(0, 0))
    end_dt = datetime.combine(target_date, time(23, 59))

    # Termine zaehlen
    appointment_count = Appointment.query.filter(
        Appointment.resource_id == resource_id,
        Appointment.start_time >= start_dt,
        Appointment.end_time <= end_dt,
        Appointment.status.in_(['scheduled', 'confirmed'])
    ).count()

    booking_count = ResourceBooking.query.filter(
        ResourceBooking.resource_id == resource_id,
        ResourceBooking.start_time >= start_dt,
        ResourceBooking.end_time <= end_dt
    ).count()

    total = appointment_count + booking_count

    # Verfuegbarkeit bestimmen (wie Cenplex Available/Partly/Booked)
    if total == 0:
        availability = 'available'
    elif total >= 8:
        availability = 'booked'
    else:
        availability = 'partly'

    return jsonify({
        'resource_id': resource_id,
        'date': target_date.isoformat(),
        'availability': availability,
        'appointment_count': appointment_count,
        'booking_count': booking_count,
        'total': total
    })


def _save_resource(resource):
    """Speichert eine Ressource (neu oder bestehend)"""
    name = request.form.get('name', '').strip()
    location_id = request.form.get('location_id', '')

    # Validierung (Cenplex: Name ist Pflichtfeld)
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
        return render_template('resources/form.html', resource=resource, locations=locations, blocked_times=[])

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
    resource.equipment_json = json.dumps(equipment) if equipment else None

    resource.is_active = request.form.get('is_active') == 'on'

    # Cenplex: is_shared (standortuebergreifend)
    resource.is_shared = request.form.get('is_shared') == 'on'

    # Cenplex: Raumverfuegbarkeit
    room_availability = request.form.get('room_availability', 'available')
    if room_availability in ('available', 'partly', 'booked'):
        resource.room_availability = room_availability

    if is_new:
        db.session.add(resource)

    db.session.commit()

    flash(f'Ressource "{resource.name}" wurde erfolgreich gespeichert.', 'success')
    return redirect(url_for('resources.detail', resource_id=resource.id))
