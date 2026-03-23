"""Mitarbeiter-Blueprint: Verwaltung von Mitarbeitern, Arbeitszeiten, Absenzen und Qualifikationen"""
import json
import calendar
from datetime import datetime, date, time, timedelta
from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from blueprints.employees import employees_bp
from models import db, User, Employee, WorkSchedule, Absence, AbsenceQuota, Certificate, \
    Location, Resource, Appointment, Holiday


# ============================================================
# Mitarbeiteruebersicht
# ============================================================

@employees_bp.route('/')
@login_required
def index():
    """Mitarbeiteruebersicht mit Suche und Filter"""
    search = request.args.get('search', '').strip()
    role = request.args.get('role', '')
    location = request.args.get('location', '')
    status = request.args.get('status', 'active')

    query = Employee.query.filter_by(organization_id=current_user.organization_id)

    # Status-Filter
    if status == 'active':
        query = query.filter_by(is_active=True)
    elif status == 'inactive':
        query = query.filter_by(is_active=False)

    # Standort-Filter
    if location:
        try:
            query = query.filter_by(default_location_id=int(location))
        except ValueError:
            pass

    # Ergebnisse laden
    employees = query.all()

    # Rollen-Filter (ueber User-Beziehung)
    if role:
        employees = [e for e in employees if e.user and e.user.role == role]

    # Suchfilter (Name)
    if search:
        search_lower = search.lower()
        employees = [e for e in employees if e.user and
                     (search_lower in e.user.first_name.lower() or
                      search_lower in e.user.last_name.lower() or
                      search_lower in (e.employee_number or '').lower())]

    # Standorte fuer Filter-Dropdown
    locations = Location.query.filter_by(is_active=True).order_by(Location.name).all()

    return render_template('employees/index.html',
                           employees=employees,
                           locations=locations,
                           search=search,
                           role=role,
                           location=location,
                           status=status)


# ============================================================
# Mitarbeiter erstellen / bearbeiten
# ============================================================

@employees_bp.route('/new', methods=['GET', 'POST'])
@login_required
def create():
    """Neuen Mitarbeiter erstellen"""
    if request.method == 'POST':
        return _save_employee(None)

    locations = Location.query.filter_by(is_active=True).order_by(Location.name).all()
    rooms = Resource.query.filter_by(resource_type='room', is_active=True).order_by(Resource.name).all()
    return render_template('employees/form.html', employee=None, locations=locations, rooms=rooms)


@employees_bp.route('/<int:employee_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(employee_id):
    """Mitarbeiter bearbeiten"""
    employee = Employee.query.get_or_404(employee_id)

    if request.method == 'POST':
        return _save_employee(employee)

    locations = Location.query.filter_by(is_active=True).order_by(Location.name).all()
    rooms = Resource.query.filter_by(resource_type='room', is_active=True).order_by(Resource.name).all()
    return render_template('employees/form.html', employee=employee, locations=locations, rooms=rooms)


def _save_employee(employee):
    """Speichert einen Mitarbeiter (neu oder bestehend)"""
    first_name = request.form.get('first_name', '').strip()
    last_name = request.form.get('last_name', '').strip()
    username = request.form.get('username', '').strip()
    role = request.form.get('role', 'therapist')
    pensum = request.form.get('pensum_percent', '100').strip()

    # Validierung
    errors = []
    if not first_name:
        errors.append('Vorname ist ein Pflichtfeld.')
    if not last_name:
        errors.append('Nachname ist ein Pflichtfeld.')
    if not username:
        errors.append('Benutzername ist ein Pflichtfeld.')

    try:
        pensum_int = int(pensum)
        if pensum_int < 1 or pensum_int > 100:
            errors.append('Pensum muss zwischen 1 und 100 liegen.')
    except ValueError:
        errors.append('Pensum muss eine Zahl sein.')
        pensum_int = 100

    # Benutzername eindeutig pruefen
    existing_user = User.query.filter_by(username=username).first()
    if employee and employee.user:
        if existing_user and existing_user.id != employee.user_id:
            errors.append('Dieser Benutzername ist bereits vergeben.')
    else:
        if existing_user:
            errors.append('Dieser Benutzername ist bereits vergeben.')

    if errors:
        for error in errors:
            flash(error, 'error')
        locations = Location.query.filter_by(is_active=True).order_by(Location.name).all()
        rooms = Resource.query.filter_by(resource_type='room', is_active=True).order_by(Resource.name).all()
        return render_template('employees/form.html', employee=employee, locations=locations, rooms=rooms)

    is_new = employee is None

    if is_new:
        # Neuen User erstellen
        user = User(
            organization_id=current_user.organization_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            name=f'{first_name} {last_name}',
            email=request.form.get('email', '').strip(),
            role=role
        )
        password = request.form.get('password', '').strip()
        if not password:
            password = username  # Standard-Passwort = Benutzername
        user.set_password(password)
        db.session.add(user)
        db.session.flush()

        # Mitarbeiternummer generieren
        emp_count = Employee.query.filter_by(organization_id=current_user.organization_id).count()
        employee = Employee(
            user_id=user.id,
            organization_id=current_user.organization_id,
            employee_number=request.form.get('employee_number', '').strip() or f'MA{emp_count + 1:03d}'
        )
        db.session.add(employee)
    else:
        # Bestehenden User aktualisieren
        user = employee.user
        user.first_name = first_name
        user.last_name = last_name
        user.name = f'{first_name} {last_name}'
        user.email = request.form.get('email', '').strip()
        user.role = role
        user.username = username

        # Passwort nur aendern, wenn eines angegeben
        password = request.form.get('password', '').strip()
        if password:
            user.set_password(password)

        employee.employee_number = request.form.get('employee_number', '').strip() or employee.employee_number

    # Mitarbeiter-Felder
    employee.pensum_percent = pensum_int
    employee.employment_model = request.form.get('employment_model', 'Festanstellung')
    employee.color_code = request.form.get('color_code', '#4a90d9')
    employee.zsr_number = request.form.get('zsr_number', '').strip()
    employee.gln_number = request.form.get('gln_number', '').strip()
    employee.is_active = request.form.get('is_active') != 'off'

    # Standort und Raum
    loc_id = request.form.get('default_location_id', '')
    employee.default_location_id = int(loc_id) if loc_id else None

    room_id = request.form.get('default_room_id', '')
    employee.default_room_id = int(room_id) if room_id else None

    # User-Felder
    user.phone = request.form.get('phone', '').strip() if hasattr(user, 'phone') else None

    # Qualifikationen
    qualifications = request.form.getlist('qualifications')
    employee.qualifications_json = json.dumps(qualifications) if qualifications else None

    # Spezialisierungen
    specializations = request.form.get('specializations', '').strip()
    if specializations:
        specs = [s.strip() for s in specializations.split(',') if s.strip()]
        employee.specializations_json = json.dumps(specs)

    db.session.commit()

    flash(f'Mitarbeiter "{first_name} {last_name}" wurde erfolgreich gespeichert.', 'success')
    return redirect(url_for('employees.detail', employee_id=employee.id))


# ============================================================
# Mitarbeiter-Detail
# ============================================================

@employees_bp.route('/<int:employee_id>')
@login_required
def detail(employee_id):
    """Mitarbeiter-Detailansicht"""
    employee = Employee.query.get_or_404(employee_id)

    # Naechste 5 Termine
    now = datetime.now()
    upcoming_appointments = Appointment.query.filter(
        Appointment.employee_id == employee_id,
        Appointment.start_time >= now,
        Appointment.status != 'cancelled'
    ).order_by(Appointment.start_time).limit(5).all()

    # Aktuelle Absenzen
    today = date.today()
    current_absences = Absence.query.filter(
        Absence.employee_id == employee_id,
        Absence.start_date <= today,
        Absence.end_date >= today
    ).all()

    # Arbeitszeiten
    work_schedules = WorkSchedule.query.filter_by(employee_id=employee_id).order_by(
        WorkSchedule.day_of_week, WorkSchedule.start_time
    ).all()

    # Auslastung diese Woche berechnen
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=4)
    week_appointments = Appointment.query.filter(
        Appointment.employee_id == employee_id,
        Appointment.start_time >= datetime.combine(week_start, time(0, 0)),
        Appointment.end_time <= datetime.combine(week_end, time(23, 59)),
        Appointment.status != 'cancelled'
    ).all()

    # Soll-Stunden berechnen
    total_work_minutes = sum(
        (datetime.combine(today, ws.end_time) - datetime.combine(today, ws.start_time)).seconds // 60
        for ws in work_schedules if ws.day_of_week < 5
    )
    booked_minutes = sum(a.duration_minutes or 30 for a in week_appointments)
    utilization = round(booked_minutes / total_work_minutes * 100) if total_work_minutes > 0 else 0

    # Zertifikate
    certificates = Certificate.query.filter_by(employee_id=employee_id).order_by(Certificate.expiry_date).all()

    # Ferien-Kontingent
    quota = AbsenceQuota.query.filter_by(
        employee_id=employee_id,
        year=today.year,
        absence_type='vacation'
    ).first()

    return render_template('employees/detail.html',
                           employee=employee,
                           upcoming_appointments=upcoming_appointments,
                           current_absences=current_absences,
                           work_schedules=work_schedules,
                           utilization=utilization,
                           booked_minutes=booked_minutes,
                           total_work_minutes=total_work_minutes,
                           certificates=certificates,
                           quota=quota)


# ============================================================
# Mitarbeiter aktivieren/deaktivieren
# ============================================================

@employees_bp.route('/<int:employee_id>/toggle', methods=['POST'])
@login_required
def toggle_active(employee_id):
    """Mitarbeiter aktivieren/deaktivieren"""
    employee = Employee.query.get_or_404(employee_id)
    employee.is_active = not employee.is_active
    if employee.user:
        employee.user.is_active = employee.is_active
    db.session.commit()

    status_text = 'aktiviert' if employee.is_active else 'deaktiviert'
    name = f'{employee.user.first_name} {employee.user.last_name}' if employee.user else 'Mitarbeiter'
    flash(f'{name} wurde {status_text}.', 'success')
    return redirect(url_for('employees.index'))


# ============================================================
# Arbeitszeiten
# ============================================================

@employees_bp.route('/<int:employee_id>/schedules', methods=['GET', 'POST'])
@login_required
def schedules(employee_id):
    """Arbeitszeiten verwalten"""
    employee = Employee.query.get_or_404(employee_id)

    if request.method == 'POST':
        return _save_schedules(employee)

    work_schedules = WorkSchedule.query.filter_by(employee_id=employee_id).order_by(
        WorkSchedule.day_of_week, WorkSchedule.start_time
    ).all()

    # Gruppiert nach Tag
    schedules_by_day = {}
    for day in range(7):
        schedules_by_day[day] = [ws for ws in work_schedules if ws.day_of_week == day]

    locations = Location.query.filter_by(is_active=True).order_by(Location.name).all()

    return render_template('employees/schedules.html',
                           employee=employee,
                           schedules_by_day=schedules_by_day,
                           locations=locations)


def _save_schedules(employee):
    """Speichert Arbeitszeiten"""
    # Bestehende Arbeitszeiten loeschen und neu erstellen
    WorkSchedule.query.filter_by(employee_id=employee.id).delete()

    day_names = ['montag', 'dienstag', 'mittwoch', 'donnerstag', 'freitag', 'samstag', 'sonntag']

    for day_idx, day_name in enumerate(day_names):
        block_idx = 0
        while True:
            start_key = f'{day_name}_start_{block_idx}'
            end_key = f'{day_name}_end_{block_idx}'
            type_key = f'{day_name}_type_{block_idx}'
            loc_key = f'{day_name}_location_{block_idx}'

            start_str = request.form.get(start_key, '').strip()
            end_str = request.form.get(end_key, '').strip()

            if not start_str or not end_str:
                break

            try:
                start_t = datetime.strptime(start_str, '%H:%M').time()
                end_t = datetime.strptime(end_str, '%H:%M').time()
            except ValueError:
                block_idx += 1
                continue

            work_type = request.form.get(type_key, 'treatment')
            loc_id = request.form.get(loc_key, '')

            schedule = WorkSchedule(
                employee_id=employee.id,
                location_id=int(loc_id) if loc_id else employee.default_location_id,
                day_of_week=day_idx,
                start_time=start_t,
                end_time=end_t,
                work_type=work_type
            )
            db.session.add(schedule)
            block_idx += 1

    db.session.commit()
    flash('Arbeitszeiten wurden gespeichert.', 'success')
    return redirect(url_for('employees.detail', employee_id=employee.id))


# ============================================================
# Absenzen
# ============================================================

@employees_bp.route('/<int:employee_id>/absences')
@login_required
def absences(employee_id):
    """Absenzen eines Mitarbeiters"""
    employee = Employee.query.get_or_404(employee_id)
    absences_list = Absence.query.filter_by(employee_id=employee_id).order_by(Absence.start_date.desc()).all()

    # Kontingent
    today = date.today()
    quota = AbsenceQuota.query.filter_by(
        employee_id=employee_id,
        year=today.year,
        absence_type='vacation'
    ).first()

    return render_template('employees/absences.html',
                           employee=employee,
                           absences=absences_list,
                           quota=quota)


@employees_bp.route('/<int:employee_id>/absences/new', methods=['GET', 'POST'])
@login_required
def create_absence(employee_id):
    """Neue Absenz erstellen"""
    employee = Employee.query.get_or_404(employee_id)

    if request.method == 'POST':
        absence_type = request.form.get('absence_type', 'vacation')
        start_str = request.form.get('start_date', '')
        end_str = request.form.get('end_date', '')
        half_day = request.form.get('half_day') == 'on'
        notes = request.form.get('notes', '').strip()

        errors = []
        try:
            start_date = datetime.strptime(start_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_str, '%Y-%m-%d').date()
            if end_date < start_date:
                errors.append('Enddatum darf nicht vor dem Startdatum liegen.')
        except ValueError:
            errors.append('Bitte geben Sie gueltige Datumswerte ein.')
            start_date = end_date = date.today()

        if errors:
            for e in errors:
                flash(e, 'error')
            return render_template('employees/absence_form.html', employee=employee, absence=None)

        # Tage berechnen
        num_days = 0
        current = start_date
        while current <= end_date:
            if current.weekday() < 5:  # Mo-Fr
                num_days += 0.5 if half_day else 1
            current += timedelta(days=1)
        if half_day:
            num_days = 0.5

        absence = Absence(
            employee_id=employee.id,
            absence_type=absence_type,
            start_date=start_date,
            end_date=end_date,
            half_day=half_day,
            status='approved' if current_user.role == 'admin' else 'pending',
            requested_by=current_user.id,
            notes=notes
        )
        db.session.add(absence)

        # Kontingent aktualisieren bei Ferien
        if absence_type == 'vacation':
            quota = AbsenceQuota.query.filter_by(
                employee_id=employee.id,
                year=start_date.year,
                absence_type='vacation'
            ).first()
            if quota:
                quota.used_days += num_days

        db.session.commit()
        flash('Absenz wurde erstellt.', 'success')
        return redirect(url_for('employees.absences', employee_id=employee.id))

    return render_template('employees/absence_form.html', employee=employee, absence=None)


@employees_bp.route('/absences/<int:absence_id>/approve', methods=['POST'])
@login_required
def approve_absence(absence_id):
    """Absenz genehmigen"""
    absence = Absence.query.get_or_404(absence_id)
    action = request.form.get('action', 'approve')

    if action == 'approve':
        absence.status = 'approved'
        absence.approved_by = current_user.id
        flash('Absenz wurde genehmigt.', 'success')
    elif action == 'reject':
        absence.status = 'rejected'
        absence.approved_by = current_user.id
        # Kontingent zurueckbuchen bei Ferien
        if absence.absence_type == 'vacation':
            num_days = _count_business_days(absence.start_date, absence.end_date)
            if absence.half_day:
                num_days = 0.5
            quota = AbsenceQuota.query.filter_by(
                employee_id=absence.employee_id,
                year=absence.start_date.year,
                absence_type='vacation'
            ).first()
            if quota:
                quota.used_days = max(0, quota.used_days - num_days)
        flash('Absenz wurde abgelehnt.', 'info')

    db.session.commit()
    return redirect(url_for('employees.absences', employee_id=absence.employee_id))


@employees_bp.route('/absences/<int:absence_id>/delete', methods=['POST'])
@login_required
def delete_absence(absence_id):
    """Absenz loeschen"""
    absence = Absence.query.get_or_404(absence_id)
    emp_id = absence.employee_id

    # Kontingent zurueckbuchen bei Ferien
    if absence.absence_type == 'vacation' and absence.status == 'approved':
        num_days = _count_business_days(absence.start_date, absence.end_date)
        if absence.half_day:
            num_days = 0.5
        quota = AbsenceQuota.query.filter_by(
            employee_id=emp_id,
            year=absence.start_date.year,
            absence_type='vacation'
        ).first()
        if quota:
            quota.used_days = max(0, quota.used_days - num_days)

    db.session.delete(absence)
    db.session.commit()
    flash('Absenz wurde geloescht.', 'success')
    return redirect(url_for('employees.absences', employee_id=emp_id))


def _count_business_days(start_date, end_date):
    """Zaehlt Arbeitstage (Mo-Fr) zwischen zwei Daten"""
    count = 0
    current = start_date
    while current <= end_date:
        if current.weekday() < 5:
            count += 1
        current += timedelta(days=1)
    return count


# ============================================================
# Zertifikate
# ============================================================

@employees_bp.route('/<int:employee_id>/certificates/new', methods=['POST'])
@login_required
def create_certificate(employee_id):
    """Neues Zertifikat erstellen"""
    employee = Employee.query.get_or_404(employee_id)

    name = request.form.get('cert_name', '').strip()
    if not name:
        flash('Zertifikatsname ist ein Pflichtfeld.', 'error')
        return redirect(url_for('employees.detail', employee_id=employee_id))

    issued_str = request.form.get('cert_issued_date', '')
    expiry_str = request.form.get('cert_expiry_date', '')

    cert = Certificate(
        employee_id=employee.id,
        name=name,
        issued_date=datetime.strptime(issued_str, '%Y-%m-%d').date() if issued_str else None,
        expiry_date=datetime.strptime(expiry_str, '%Y-%m-%d').date() if expiry_str else None
    )
    db.session.add(cert)
    db.session.commit()

    flash(f'Zertifikat "{name}" wurde hinzugefuegt.', 'success')
    return redirect(url_for('employees.detail', employee_id=employee_id))


@employees_bp.route('/certificates/<int:cert_id>/delete', methods=['POST'])
@login_required
def delete_certificate(cert_id):
    """Zertifikat loeschen"""
    cert = Certificate.query.get_or_404(cert_id)
    emp_id = cert.employee_id
    db.session.delete(cert)
    db.session.commit()
    flash('Zertifikat wurde geloescht.', 'success')
    return redirect(url_for('employees.detail', employee_id=emp_id))


# ============================================================
# Urlaubskalender
# ============================================================

@employees_bp.route('/calendar')
@login_required
def absence_calendar():
    """Urlaubskalender: Monatsansicht aller Mitarbeiter"""
    year = request.args.get('year', date.today().year, type=int)
    month = request.args.get('month', date.today().month, type=int)

    # Navigation
    if month < 1:
        month = 12
        year -= 1
    elif month > 12:
        month = 1
        year += 1

    # Tage im Monat
    _, days_in_month = calendar.monthrange(year, month)
    month_dates = [date(year, month, d) for d in range(1, days_in_month + 1)]

    # Mitarbeiter
    employees = Employee.query.filter_by(
        organization_id=current_user.organization_id,
        is_active=True
    ).all()

    # Absenzen im Monat
    month_start = date(year, month, 1)
    month_end = date(year, month, days_in_month)
    absences_list = Absence.query.filter(
        Absence.start_date <= month_end,
        Absence.end_date >= month_start,
        Absence.status.in_(['approved', 'pending'])
    ).all()

    # Absenzen nach Mitarbeiter gruppieren
    absence_map = {}
    for absence in absences_list:
        if absence.employee_id not in absence_map:
            absence_map[absence.employee_id] = []
        absence_map[absence.employee_id].append(absence)

    # Feiertage
    holidays_list = Holiday.query.filter(
        Holiday.date >= month_start,
        Holiday.date <= month_end
    ).all()
    holiday_dates = {h.date for h in holidays_list}

    month_names = ['Januar', 'Februar', 'Maerz', 'April', 'Mai', 'Juni',
                   'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember']

    return render_template('employees/calendar.html',
                           employees=employees,
                           month_dates=month_dates,
                           absence_map=absence_map,
                           holiday_dates=holiday_dates,
                           year=year,
                           month=month,
                           month_name=month_names[month - 1],
                           today=date.today())


# ============================================================
# Einsatzplanung
# ============================================================

@employees_bp.route('/deployment')
@login_required
def deployment():
    """Einsatzplanung: Wochenansicht"""
    # Woche bestimmen
    date_str = request.args.get('date', '')
    if date_str:
        try:
            ref_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            ref_date = date.today()
    else:
        ref_date = date.today()

    # Wochentage Mo-Fr
    week_start = ref_date - timedelta(days=ref_date.weekday())
    week_dates = [week_start + timedelta(days=i) for i in range(5)]

    # Mitarbeiter
    employees = Employee.query.filter_by(
        organization_id=current_user.organization_id,
        is_active=True
    ).all()

    # Termine der Woche
    week_end = week_start + timedelta(days=4)
    appointments = Appointment.query.filter(
        Appointment.start_time >= datetime.combine(week_start, time(0, 0)),
        Appointment.start_time <= datetime.combine(week_end, time(23, 59)),
        Appointment.status != 'cancelled'
    ).all()

    # Termine nach Mitarbeiter und Tag gruppieren
    appointment_map = {}
    for appt in appointments:
        key = (appt.employee_id, appt.start_time.date())
        if key not in appointment_map:
            appointment_map[key] = []
        appointment_map[key].append(appt)

    # Arbeitszeiten laden
    schedule_map = {}
    for emp in employees:
        schedules = WorkSchedule.query.filter_by(employee_id=emp.id).all()
        for ws in schedules:
            key = (emp.id, ws.day_of_week)
            if key not in schedule_map:
                schedule_map[key] = []
            schedule_map[key].append(ws)

    # Absenzen der Woche
    absences_list = Absence.query.filter(
        Absence.start_date <= week_end,
        Absence.end_date >= week_start,
        Absence.status == 'approved'
    ).all()
    absence_dates = {}
    for absence in absences_list:
        current = max(absence.start_date, week_start)
        while current <= min(absence.end_date, week_end):
            key = (absence.employee_id, current)
            absence_dates[key] = absence
            current += timedelta(days=1)

    return render_template('employees/deployment.html',
                           employees=employees,
                           week_dates=week_dates,
                           appointment_map=appointment_map,
                           schedule_map=schedule_map,
                           absence_dates=absence_dates,
                           week_start=week_start,
                           today=date.today())


# ============================================================
# API-Endpunkte
# ============================================================

@employees_bp.route('/api/rooms/<int:location_id>')
@login_required
def api_rooms_by_location(location_id):
    """Raeume nach Standort (fuer AJAX)"""
    rooms = Resource.query.filter_by(
        location_id=location_id,
        resource_type='room',
        is_active=True
    ).order_by(Resource.name).all()

    return jsonify([{'id': r.id, 'name': r.name} for r in rooms])
