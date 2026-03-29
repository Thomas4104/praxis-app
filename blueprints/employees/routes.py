"""Mitarbeiter-Blueprint: Verwaltung von Mitarbeitern, Arbeitszeiten, Absenzen und Qualifikationen"""
import json
import calendar
from datetime import datetime, date, time, timedelta
from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from blueprints.employees import employees_bp
from models import db, User, Employee, WorkSchedule, Absence, AbsenceQuota, Certificate, \
    Location, Resource, Appointment, Holiday
from sqlalchemy.orm import joinedload
from utils.auth import check_org
from services.user_rights_service import require_right


# ============================================================
# Mitarbeiteruebersicht
# ============================================================

@employees_bp.route('/')
@login_required
@require_right('employee', 'can_read')
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

    # Rollen-Filter und Suchfilter auf DB-Ebene (statt in-memory)
    if role or search:
        query = query.join(User, Employee.user_id == User.id)
        if role:
            query = query.filter(User.role == role)
        if search:
            search_pattern = f'%{search}%'
            query = query.filter(
                db.or_(
                    User.first_name.ilike(search_pattern),
                    User.last_name.ilike(search_pattern),
                    Employee.employee_number.ilike(search_pattern)
                )
            )

    # Ergebnisse laden mit eager loading
    employees = query.options(joinedload(Employee.user)).all()

    # Standorte fuer Filter-Dropdown
    locations = Location.query.filter_by(organization_id=current_user.organization_id, is_active=True).order_by(Location.name).all()

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
@require_right('employee', 'can_edit')
def create():
    """Neuen Mitarbeiter erstellen"""
    if request.method == 'POST':
        return _save_employee(None)

    org_id = current_user.organization_id
    locations = Location.query.filter_by(organization_id=org_id, is_active=True).order_by(Location.name).all()
    rooms = Resource.query.filter_by(organization_id=org_id, resource_type='room', is_active=True).order_by(Resource.name).all()
    return render_template('employees/form.html', employee=None, locations=locations, rooms=rooms)


@employees_bp.route('/<int:employee_id>/edit', methods=['GET', 'POST'])
@login_required
@require_right('employee', 'can_edit')
def edit(employee_id):
    """Mitarbeiter bearbeiten"""
    employee = Employee.query.get_or_404(employee_id)
    check_org(employee)

    if request.method == 'POST':
        return _save_employee(employee)

    org_id = current_user.organization_id
    locations = Location.query.filter_by(organization_id=org_id, is_active=True).order_by(Location.name).all()
    rooms = Resource.query.filter_by(organization_id=org_id, resource_type='room', is_active=True).order_by(Resource.name).all()
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
        org_id = current_user.organization_id
        locations = Location.query.filter_by(organization_id=org_id, is_active=True).order_by(Location.name).all()
        rooms = Resource.query.filter_by(organization_id=org_id, resource_type='room', is_active=True).order_by(Resource.name).all()
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
    employee.contract_type = request.form.get('contract_type', 'permanent')
    employee.color_code = request.form.get('color_code', '#4a90d9')
    employee.zsr_number = request.form.get('zsr_number', '').strip()
    employee.gln_number = request.form.get('gln_number', '').strip()
    employee.ahv_number = request.form.get('ahv_number', '').strip()
    employee.emr_number = request.form.get('emr_number', '').strip()
    employee.asca_number = request.form.get('asca_number', '').strip()
    employee.degree = request.form.get('degree', '').strip()
    employee.notes = request.form.get('notes', '').strip()
    employee.is_active = request.form.get('is_active') == 'on'

    # Persoenliche Daten
    employee.salutation = request.form.get('salutation', '').strip()
    employee.sex = request.form.get('sex', '').strip()
    employee.private_email = request.form.get('private_email', '').strip()
    employee.phone_office = request.form.get('phone_office', '').strip()
    employee.mobile = request.form.get('mobile', '').strip()
    employee.phone_private = request.form.get('phone_private', '').strip()

    # Geburtstag
    birthday_str = request.form.get('birthday', '').strip()
    if birthday_str:
        try:
            employee.birthday = datetime.strptime(birthday_str, '%Y-%m-%d').date()
        except ValueError:
            pass
    else:
        employee.birthday = None

    # Adresse
    employee.street = request.form.get('street', '').strip()
    employee.zipcode = request.form.get('zipcode', '').strip()
    employee.town = request.form.get('town', '').strip()
    employee.kanton = request.form.get('kanton', '').strip()
    employee.country = request.form.get('country', 'CH').strip()

    # Aktiv seit
    active_from_str = request.form.get('active_from', '').strip()
    if active_from_str:
        try:
            employee.active_from = datetime.strptime(active_from_str, '%Y-%m-%d').date()
        except ValueError:
            pass

    # Kalender-Intervall
    cal_interval = request.form.get('calendar_default_interval', '')
    if cal_interval:
        try:
            interval = int(cal_interval)
            if interval >= 15 and interval % 5 == 0:
                employee.calendar_default_interval = interval
        except ValueError:
            pass

    # Online-Buchung
    employee.booking_book_active = request.form.get('booking_book_active') == 'on'
    sync_from_str = request.form.get('booking_sync_from', '').strip()
    if sync_from_str:
        try:
            employee.booking_sync_from = datetime.strptime(sync_from_str, '%Y-%m-%d').date()
        except ValueError:
            pass
    else:
        employee.booking_sync_from = None
    sync_till_str = request.form.get('booking_sync_till', '').strip()
    if sync_till_str:
        try:
            employee.booking_sync_till = datetime.strptime(sync_till_str, '%Y-%m-%d').date()
        except ValueError:
            pass
    else:
        employee.booking_sync_till = None

    # Standort und Raum
    loc_id = request.form.get('default_location_id', '')
    employee.default_location_id = int(loc_id) if loc_id else None

    room_id = request.form.get('default_room_id', '')
    employee.default_room_id = int(room_id) if room_id else None

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
    check_org(employee)

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

    # Kapazitaeten laden
    from models import EmployeeCapacity, EmployeeWorkplan, VacationAllotment, \
        EmployeeGroup, EmployeeGroupMember, OvertimeHistory
    capacities = EmployeeCapacity.query.filter_by(
        employee_id=employee_id, is_deleted=False
    ).order_by(EmployeeCapacity.valid_from.desc()).all()

    # Aktuelle Kapazitaet bestimmen
    current_capacity = None
    for cap in capacities:
        if cap.valid_from and cap.valid_from <= today:
            current_capacity = cap
            break

    # Arbeitsplaene laden
    workplans = EmployeeWorkplan.query.filter_by(
        employee_id=employee_id
    ).order_by(EmployeeWorkplan.from_date.desc()).all()

    # Ferienkontingente laden
    vacation_allotments = VacationAllotment.query.filter_by(
        employee_id=employee_id, planned_year=today.year
    ).all()

    # Benutzergruppen laden
    group_memberships = db.session.query(EmployeeGroup).join(
        EmployeeGroupMember, EmployeeGroup.id == EmployeeGroupMember.group_id
    ).filter(EmployeeGroupMember.employee_id == employee_id).all()

    # Ueberstunden-Historie laden (letzte 6 Monate)
    six_months_ago = (today.replace(day=1) - timedelta(days=180)).replace(day=1)
    overtime_history = OvertimeHistory.query.filter(
        OvertimeHistory.employee_id == employee_id,
        OvertimeHistory.month >= six_months_ago
    ).order_by(OvertimeHistory.month.desc()).all()

    return render_template('employees/detail.html',
                           employee=employee,
                           upcoming_appointments=upcoming_appointments,
                           current_absences=current_absences,
                           work_schedules=work_schedules,
                           utilization=utilization,
                           booked_minutes=booked_minutes,
                           total_work_minutes=total_work_minutes,
                           certificates=certificates,
                           quota=quota,
                           capacities=capacities,
                           current_capacity=current_capacity,
                           workplans=workplans,
                           vacation_allotments=vacation_allotments,
                           group_memberships=group_memberships,
                           overtime_history=overtime_history)


# ============================================================
# Mitarbeiter aktivieren/deaktivieren
# ============================================================

@employees_bp.route('/<int:employee_id>/toggle', methods=['POST'])
@login_required
@require_right('employee', 'can_edit')
def toggle_active(employee_id):
    """Mitarbeiter aktivieren/deaktivieren"""
    employee = Employee.query.get_or_404(employee_id)
    check_org(employee)
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
@require_right('employee', 'can_edit_work_schedule')
def schedules(employee_id):
    """Arbeitszeiten verwalten"""
    employee = Employee.query.get_or_404(employee_id)
    check_org(employee)

    if request.method == 'POST':
        return _save_schedules(employee)

    work_schedules = WorkSchedule.query.filter_by(employee_id=employee_id).order_by(
        WorkSchedule.day_of_week, WorkSchedule.start_time
    ).all()

    # Gruppiert nach Tag
    schedules_by_day = {}
    for day in range(7):
        schedules_by_day[day] = [ws for ws in work_schedules if ws.day_of_week == day]

    locations = Location.query.filter_by(organization_id=current_user.organization_id, is_active=True).order_by(Location.name).all()

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
    check_org(employee)
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
@require_right('employee', 'can_add_vacation')
def create_absence(employee_id):
    """Neue Absenz erstellen"""
    employee = Employee.query.get_or_404(employee_id)
    check_org(employee)

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
    # IDOR-Schutz: Mitarbeiter der Absenz muss zur Organisation gehoeren
    emp = Employee.query.get_or_404(absence.employee_id)
    check_org(emp)
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
    # IDOR-Schutz: Mitarbeiter der Absenz muss zur Organisation gehoeren
    emp = Employee.query.get_or_404(absence.employee_id)
    check_org(emp)
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
    flash('Absenz wurde gelöscht.', 'success')
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
    check_org(employee)

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

    flash(f'Zertifikat "{name}" wurde hinzugefügt.', 'success')
    return redirect(url_for('employees.detail', employee_id=employee_id))


@employees_bp.route('/certificates/<int:cert_id>/delete', methods=['POST'])
@login_required
def delete_certificate(cert_id):
    """Zertifikat loeschen"""
    cert = Certificate.query.get_or_404(cert_id)
    # IDOR-Schutz: Mitarbeiter des Zertifikats muss zur Organisation gehoeren
    emp = Employee.query.get_or_404(cert.employee_id)
    check_org(emp)
    emp_id = cert.employee_id
    db.session.delete(cert)
    db.session.commit()
    flash('Zertifikat wurde gelöscht.', 'success')
    return redirect(url_for('employees.detail', employee_id=emp_id))


# ============================================================
# Urlaubskalender
# ============================================================

@employees_bp.route('/calendar')
@login_required
@require_right('employee', 'can_access_vacation_plan')
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

    # Absenzen im Monat (nur fuer Mitarbeiter der eigenen Organisation)
    month_start = date(year, month, 1)
    month_end = date(year, month, days_in_month)
    org_employee_ids = [e.id for e in employees]
    absences_list = Absence.query.filter(
        Absence.employee_id.in_(org_employee_ids),
        Absence.start_date <= month_end,
        Absence.end_date >= month_start,
        Absence.status.in_(['approved', 'pending'])
    ).all() if org_employee_ids else []

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

    # Termine der Woche (nur fuer Mitarbeiter der eigenen Organisation)
    week_end = week_start + timedelta(days=4)
    org_employee_ids = [e.id for e in employees]
    appointments = Appointment.query.filter(
        Appointment.employee_id.in_(org_employee_ids),
        Appointment.start_time >= datetime.combine(week_start, time(0, 0)),
        Appointment.start_time <= datetime.combine(week_end, time(23, 59)),
        Appointment.status != 'cancelled'
    ).all() if org_employee_ids else []

    # Termine nach Mitarbeiter und Tag gruppieren
    appointment_map = {}
    for appt in appointments:
        key = (appt.employee_id, appt.start_time.date())
        if key not in appointment_map:
            appointment_map[key] = []
        appointment_map[key].append(appt)

    # Arbeitszeiten laden (eine Query statt N+1)
    schedule_map = {}
    if org_employee_ids:
        all_schedules = WorkSchedule.query.filter(
            WorkSchedule.employee_id.in_(org_employee_ids)
        ).all()
        for ws in all_schedules:
            key = (ws.employee_id, ws.day_of_week)
            if key not in schedule_map:
                schedule_map[key] = []
            schedule_map[key].append(ws)

    # Absenzen der Woche (nur fuer Mitarbeiter der eigenen Organisation)
    absences_list = Absence.query.filter(
        Absence.employee_id.in_(org_employee_ids),
        Absence.start_date <= week_end,
        Absence.end_date >= week_start,
        Absence.status == 'approved'
    ).all() if org_employee_ids else []
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
    # Standort muss zur Organisation gehoeren
    location = Location.query.get_or_404(location_id)
    check_org(location)
    rooms = Resource.query.filter_by(
        location_id=location_id,
        resource_type='room',
        is_active=True
    ).order_by(Resource.name).all()

    return jsonify([{'id': r.id, 'name': r.name} for r in rooms])


# ============================================================
# Cenplex Phase 4: Kapazitaets-Management
# ============================================================

@employees_bp.route('/<int:employee_id>/capacities')
@login_required
def api_capacities(employee_id):
    """Mitarbeiter-Kapazitaeten laden (Cenplex: GetCapacities)"""
    from models import EmployeeCapacity
    employee = Employee.query.get_or_404(employee_id)
    check_org(employee)

    caps = EmployeeCapacity.query.filter_by(
        employee_id=employee.id, is_deleted=False
    ).order_by(EmployeeCapacity.valid_from.desc()).all()

    return jsonify([{
        'id': c.id,
        'capacity': c.capacity,
        'valid_from': c.valid_from.isoformat() if c.valid_from else '',
    } for c in caps])


@employees_bp.route('/<int:employee_id>/capacities', methods=['POST'])
@login_required
def save_capacity(employee_id):
    """Kapazitaet aendern/erstellen (Cenplex: ChangeCapacity)"""
    from models import EmployeeCapacity
    employee = Employee.query.get_or_404(employee_id)
    check_org(employee)

    data = request.get_json() if request.is_json else request.form
    capacity_id = data.get('id')
    capacity_val = int(data.get('capacity', 100))
    valid_from_str = data.get('valid_from')

    if not valid_from_str:
        return jsonify({'error': 'valid_from ist Pflicht'}), 400

    from datetime import datetime as dt
    try:
        valid_from = dt.strptime(valid_from_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'error': 'Ungültiges Datum'}), 400

    if capacity_id:
        cap = EmployeeCapacity.query.get_or_404(int(capacity_id))
        if cap.employee_id != employee.id:
            return jsonify({'error': 'Nicht erlaubt'}), 403
        cap.capacity = capacity_val
        cap.valid_from = valid_from
    else:
        cap = EmployeeCapacity(
            employee_id=employee.id,
            capacity=capacity_val,
            valid_from=valid_from
        )
        db.session.add(cap)

    db.session.commit()
    return jsonify({'success': True, 'id': cap.id})


@employees_bp.route('/<int:employee_id>/capacities/<int:cap_id>', methods=['DELETE'])
@login_required
def delete_capacity(employee_id, cap_id):
    """Kapazitaet loeschen"""
    from models import EmployeeCapacity
    employee = Employee.query.get_or_404(employee_id)
    check_org(employee)
    cap = EmployeeCapacity.query.get_or_404(cap_id)
    if cap.employee_id != employee.id:
        return jsonify({'error': 'Nicht erlaubt'}), 403
    cap.is_deleted = True
    db.session.commit()
    return jsonify({'success': True})


# ============================================================
# Cenplex Phase 4: Arbeitsplan-Verwaltung (Workplans)
# ============================================================

@employees_bp.route('/<int:employee_id>/workplans')
@login_required
def api_workplans(employee_id):
    """Arbeitsplaene laden (Cenplex: EmployeeWorkplan)"""
    from models import EmployeeWorkplan
    employee = Employee.query.get_or_404(employee_id)
    check_org(employee)

    plans = EmployeeWorkplan.query.filter_by(employee_id=employee.id) \
        .order_by(EmployeeWorkplan.from_date.desc()).all()
    return jsonify([{
        'id': p.id,
        'name': p.name or '',
        'from_date': p.from_date.isoformat() if p.from_date else '',
        'to_date': p.to_date.isoformat() if p.to_date else '',
        'planned_date': p.planned_date.isoformat() if p.planned_date else '',
        'work_schedule_json': p.work_schedule_json
    } for p in plans])


@employees_bp.route('/<int:employee_id>/workplans', methods=['POST'])
@login_required
def save_workplan(employee_id):
    """Arbeitsplan erstellen/aktualisieren"""
    from models import EmployeeWorkplan
    employee = Employee.query.get_or_404(employee_id)
    check_org(employee)

    data = request.get_json()
    plan_id = data.get('id')

    if plan_id:
        plan = EmployeeWorkplan.query.get_or_404(int(plan_id))
        if plan.employee_id != employee.id:
            return jsonify({'error': 'Nicht erlaubt'}), 403
    else:
        plan = EmployeeWorkplan(employee_id=employee.id)

    plan.name = data.get('name', '')
    from datetime import datetime as dt
    plan.from_date = dt.strptime(data['from_date'], '%Y-%m-%d').date() if data.get('from_date') else None
    plan.to_date = dt.strptime(data['to_date'], '%Y-%m-%d').date() if data.get('to_date') else None
    plan.planned_date = dt.strptime(data['planned_date'], '%Y-%m-%d').date() if data.get('planned_date') else None
    plan.work_schedule_json = json.dumps(data.get('work_schedule')) if data.get('work_schedule') else None

    if not plan_id:
        db.session.add(plan)
    db.session.commit()
    return jsonify({'success': True, 'id': plan.id})


# ============================================================
# Cenplex Phase 4: Urlaubskontingente (Vacation Allotments)
# ============================================================

@employees_bp.route('/api/vacation-allotments')
@login_required
def api_vacation_allotments():
    """Urlaubskontingente laden (Cenplex: GetAllotments)"""
    from models import VacationAllotment
    year = request.args.get('year', type=int, default=date.today().year)
    employee_ids = request.args.get('employee_ids', '')

    org_id = current_user.organization_id
    query = VacationAllotment.query.filter_by(
        organization_id=org_id, planned_year=year
    )

    if employee_ids:
        try:
            ids = [int(x) for x in employee_ids.split(',') if x.strip()]
            if ids:
                query = query.filter(VacationAllotment.employee_id.in_(ids))
        except ValueError:
            pass

    allotments = query.all()
    return jsonify([{
        'id': a.id,
        'employee_id': a.employee_id,
        'planned_year': a.planned_year,
        'days': float(a.days) if a.days else None,
        'hours': float(a.hours) if a.hours else None,
        'hours_per_day': float(a.hours_per_day) if a.hours_per_day else None,
        'pensum': float(a.pensum) if a.pensum else None,
        'comments': a.comments or ''
    } for a in allotments])


@employees_bp.route('/api/vacation-allotments', methods=['POST'])
@login_required
def save_vacation_allotments():
    """Urlaubskontingente speichern (Cenplex: SaveAllotments)"""
    from models import VacationAllotment
    data = request.get_json()
    if not data or not isinstance(data, list):
        return jsonify({'error': 'Array von Allotments erwartet'}), 400

    org_id = current_user.organization_id
    for item in data:
        allot_id = item.get('id')
        if allot_id:
            allot = VacationAllotment.query.get(allot_id)
        else:
            allot = VacationAllotment(
                organization_id=org_id,
                employee_id=item['employee_id'],
                planned_year=item['planned_year']
            )
            db.session.add(allot)

        if allot:
            allot.days = item.get('days')
            allot.hours = item.get('hours')
            allot.hours_per_day = item.get('hours_per_day')
            allot.pensum = item.get('pensum')
            allot.comments = item.get('comments', '')

    db.session.commit()
    return jsonify({'success': True})


# ============================================================
# Cenplex Phase 4: Ueberstunden-Berechnung
# ============================================================

@employees_bp.route('/api/overtime')
@login_required
def api_overtime():
    """Ueberstunden laden (Cenplex: GetOvertimes)"""
    from models import OvertimeHistory
    month_str = request.args.get('month')
    employee_ids = request.args.get('employee_ids', '')

    if month_str:
        from datetime import datetime as dt
        try:
            month_date = dt.strptime(month_str, '%Y-%m').date().replace(day=1)
        except ValueError:
            month_date = date.today().replace(day=1)
    else:
        month_date = date.today().replace(day=1)

    # SECURITY: Nur Mitarbeiter der eigenen Organisation
    org_employees = Employee.query.filter_by(
        organization_id=current_user.organization_id
    ).with_entities(Employee.id).all()
    org_emp_ids = [e.id for e in org_employees]

    query = OvertimeHistory.query.filter(
        OvertimeHistory.employee_id.in_(org_emp_ids),
        OvertimeHistory.month == month_date
    )

    if employee_ids:
        try:
            ids = [int(x) for x in employee_ids.split(',') if x.strip()]
            if ids:
                query = query.filter(OvertimeHistory.employee_id.in_(ids))
        except ValueError:
            pass

    entries = query.all()
    return jsonify([{
        'id': e.id,
        'employee_id': e.employee_id,
        'month': e.month.isoformat(),
        'planned_worktime': float(e.planned_worktime or 0),
        'treatment_time': float(e.treatment_time or 0),
        'admin_time': float(e.admin_time or 0),
        'overtime': float(e.overtime or 0)
    } for e in entries])


# ============================================================
# Cenplex Phase 4: Benutzergruppen (Employee Groups)
# ============================================================

@employees_bp.route('/api/groups')
@login_required
def api_employee_groups():
    """Benutzergruppen laden (Cenplex: GetUserGroups)"""
    from models import EmployeeGroup, EmployeeGroupMember
    org_id = current_user.organization_id
    groups = EmployeeGroup.query.filter_by(organization_id=org_id).all()
    result = []
    for g in groups:
        members = EmployeeGroupMember.query.filter_by(group_id=g.id).all()
        result.append({
            'id': g.id,
            'title': g.title,
            'description': g.description or '',
            'member_count': len(members),
            'member_ids': [m.employee_id for m in members]
        })
    return jsonify(result)


@employees_bp.route('/api/groups', methods=['POST'])
@login_required
def save_employee_group():
    """Benutzergruppe erstellen/aktualisieren"""
    from models import EmployeeGroup, EmployeeGroupMember
    data = request.get_json()
    org_id = current_user.organization_id

    group_id = data.get('id')
    if group_id:
        group = EmployeeGroup.query.get_or_404(int(group_id))
    else:
        group = EmployeeGroup(organization_id=org_id)

    group.title = data.get('title', '')
    group.description = data.get('description', '')
    group.user_rights_json = json.dumps(data.get('user_rights')) if data.get('user_rights') else None

    if not group_id:
        db.session.add(group)
        db.session.flush()

    # Mitglieder aktualisieren
    if 'member_ids' in data:
        EmployeeGroupMember.query.filter_by(group_id=group.id).delete()
        for emp_id in data['member_ids']:
            member = EmployeeGroupMember(group_id=group.id, employee_id=int(emp_id))
            db.session.add(member)

    db.session.commit()
    return jsonify({'success': True, 'id': group.id})


# ============================================================
# Cenplex Phase 4: Ferienkontingente-Seite (HTML)
# ============================================================

@employees_bp.route('/vacation-allotments')
@login_required
@require_right('employee', 'can_edit_vacation_allotment_settings')
def vacation_allotments_page():
    """Ferienkontingente-Verwaltung (HTML-Seite)"""
    from models import VacationAllotment
    org_id = current_user.organization_id
    year = request.args.get('year', type=int, default=date.today().year)

    employees = Employee.query.filter_by(
        organization_id=org_id, is_active=True
    ).join(User).order_by(User.last_name).all()

    allotments = VacationAllotment.query.filter_by(
        organization_id=org_id, planned_year=year
    ).all()

    # Map: employee_id -> allotment
    allotment_map = {a.employee_id: a for a in allotments}

    return render_template('employees/vacation_allotments.html',
                           employees=employees,
                           allotment_map=allotment_map,
                           year=year)


@employees_bp.route('/vacation-allotments', methods=['POST'])
@login_required
def save_vacation_allotments_page():
    """Ferienkontingente speichern (Form POST)"""
    from models import VacationAllotment
    org_id = current_user.organization_id
    year = int(request.form.get('year', date.today().year))

    employees = Employee.query.filter_by(
        organization_id=org_id, is_active=True
    ).all()

    for emp in employees:
        days = request.form.get(f'days_{emp.id}', '').strip()
        hours = request.form.get(f'hours_{emp.id}', '').strip()
        hours_per_day = request.form.get(f'hours_per_day_{emp.id}', '').strip()
        pensum = request.form.get(f'pensum_{emp.id}', '').strip()
        comments = request.form.get(f'comments_{emp.id}', '').strip()

        allot = VacationAllotment.query.filter_by(
            organization_id=org_id, employee_id=emp.id, planned_year=year
        ).first()

        if not allot:
            allot = VacationAllotment(
                organization_id=org_id, employee_id=emp.id, planned_year=year
            )
            db.session.add(allot)

        allot.days = float(days) if days else None
        allot.hours = float(hours) if hours else None
        allot.hours_per_day = float(hours_per_day) if hours_per_day else None
        allot.pensum = float(pensum) if pensum else emp.pensum_percent
        allot.comments = comments

    db.session.commit()
    flash('Ferienkontingente gespeichert.', 'success')
    return redirect(url_for('employees.vacation_allotments_page', year=year))


# ============================================================
# Cenplex Phase 4: Ueberstunden-Seite (HTML)
# ============================================================

@employees_bp.route('/overtime')
@login_required
def overtime_page():
    """Ueberstunden-Uebersicht (HTML-Seite)"""
    from models import OvertimeHistory
    org_id = current_user.organization_id
    month_str = request.args.get('month', '')

    if month_str:
        try:
            selected_month = datetime.strptime(month_str, '%Y-%m').date().replace(day=1)
        except ValueError:
            selected_month = date.today().replace(day=1)
    else:
        selected_month = date.today().replace(day=1)

    employees = Employee.query.filter_by(
        organization_id=org_id, is_active=True
    ).join(User).order_by(User.last_name).all()
    emp_ids = [e.id for e in employees]

    overtime_entries = OvertimeHistory.query.filter(
        OvertimeHistory.employee_id.in_(emp_ids),
        OvertimeHistory.month == selected_month
    ).all() if emp_ids else []

    # Map: employee_id -> overtime
    overtime_map = {ot.employee_id: ot for ot in overtime_entries}

    # Vorherige 6 Monate fuer Navigation
    months = []
    m = date.today().replace(day=1)
    for i in range(6):
        months.append(m)
        m = (m - timedelta(days=1)).replace(day=1)

    return render_template('employees/overtime.html',
                           employees=employees,
                           overtime_map=overtime_map,
                           selected_month=selected_month,
                           months=months)


# ============================================================
# Cenplex Phase 4: Benutzergruppen-Seite (HTML)
# ============================================================

@employees_bp.route('/groups')
@login_required
@require_right('employee', 'can_edit_user_groups')
def employee_groups_page():
    """Benutzergruppen-Verwaltung (HTML-Seite)"""
    from models import EmployeeGroup, EmployeeGroupMember
    org_id = current_user.organization_id

    groups = EmployeeGroup.query.filter_by(organization_id=org_id).all()

    # Gruppenmitglieder laden
    group_data = []
    for g in groups:
        members = db.session.query(Employee).join(
            EmployeeGroupMember, Employee.id == EmployeeGroupMember.employee_id
        ).filter(EmployeeGroupMember.group_id == g.id).all()
        group_data.append({
            'group': g,
            'members': members
        })

    employees = Employee.query.filter_by(
        organization_id=org_id, is_active=True
    ).join(User).order_by(User.last_name).all()

    return render_template('employees/groups.html',
                           group_data=group_data,
                           employees=employees)


@employees_bp.route('/groups/save', methods=['POST'])
@login_required
def save_employee_group_page():
    """Benutzergruppe speichern (Form POST)"""
    from models import EmployeeGroup, EmployeeGroupMember
    org_id = current_user.organization_id

    group_id = request.form.get('group_id', '').strip()
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    member_ids = request.form.getlist('member_ids')

    if not title:
        flash('Gruppenname ist ein Pflichtfeld.', 'error')
        return redirect(url_for('employees.employee_groups_page'))

    if group_id:
        group = EmployeeGroup.query.get_or_404(int(group_id))
    else:
        group = EmployeeGroup(organization_id=org_id)
        db.session.add(group)

    group.title = title
    group.description = description
    db.session.flush()

    # Mitglieder aktualisieren
    EmployeeGroupMember.query.filter_by(group_id=group.id).delete()
    for emp_id in member_ids:
        member = EmployeeGroupMember(group_id=group.id, employee_id=int(emp_id))
        db.session.add(member)

    db.session.commit()
    flash(f'Benutzergruppe "{title}" gespeichert.', 'success')
    return redirect(url_for('employees.employee_groups_page'))


@employees_bp.route('/groups/<int:group_id>/delete', methods=['POST'])
@login_required
def delete_employee_group_page(group_id):
    """Benutzergruppe loeschen (Form POST)"""
    from models import EmployeeGroup, EmployeeGroupMember
    group = EmployeeGroup.query.get_or_404(group_id)
    if group.organization_id != current_user.organization_id:
        flash('Keine Berechtigung.', 'error')
        return redirect(url_for('employees.employee_groups_page'))

    EmployeeGroupMember.query.filter_by(group_id=group.id).delete()
    db.session.delete(group)
    db.session.commit()
    flash('Benutzergruppe gelöscht.', 'success')
    return redirect(url_for('employees.employee_groups_page'))


# ============================================================
# Cenplex Phase 4: Raumplanung (HTML)
# ============================================================

@employees_bp.route('/room-planning')
@login_required
@require_right('employee', 'can_edit_room_plan')
def room_planning():
    """Raumplanung: Wochenansicht der Raumbelegung"""
    org_id = current_user.organization_id
    date_str = request.args.get('date', '')
    if date_str:
        try:
            ref_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            ref_date = date.today()
    else:
        ref_date = date.today()

    week_start = ref_date - timedelta(days=ref_date.weekday())
    week_dates = [week_start + timedelta(days=i) for i in range(5)]

    # Raeume laden
    rooms = Resource.query.filter_by(
        organization_id=org_id, resource_type='room', is_active=True
    ).order_by(Resource.name).all()

    # Termine pro Raum und Tag
    room_ids = [r.id for r in rooms]
    week_end = week_start + timedelta(days=4)
    appointments = Appointment.query.filter(
        Appointment.resource_id.in_(room_ids),
        Appointment.start_time >= datetime.combine(week_start, time(0, 0)),
        Appointment.start_time <= datetime.combine(week_end, time(23, 59)),
        Appointment.status != 'cancelled'
    ).all() if room_ids else []

    # Map: (room_id, date) -> [appointments]
    room_appointment_map = {}
    for appt in appointments:
        key = (appt.resource_id, appt.start_time.date())
        if key not in room_appointment_map:
            room_appointment_map[key] = []
        room_appointment_map[key].append(appt)

    # Arbeitszeiten pro Raum via Mitarbeiter-Standort
    locations = Location.query.filter_by(organization_id=org_id, is_active=True).all()

    return render_template('employees/room_planning.html',
                           rooms=rooms,
                           week_dates=week_dates,
                           room_appointment_map=room_appointment_map,
                           week_start=week_start,
                           locations=locations,
                           today=date.today())


@employees_bp.route('/api/groups/<int:group_id>', methods=['DELETE'])
@login_required
def delete_employee_group(group_id):
    """Benutzergruppe loeschen"""
    from models import EmployeeGroup, EmployeeGroupMember
    group = EmployeeGroup.query.get_or_404(group_id)
    if group.organization_id != current_user.organization_id:
        return jsonify({'error': 'Nicht erlaubt'}), 403

    EmployeeGroupMember.query.filter_by(group_id=group.id).delete()
    db.session.delete(group)
    db.session.commit()
    return jsonify({'success': True})


@employees_bp.route('/api/groups/<int:group_id>/rights', methods=['PUT'])
@login_required
def save_group_rights(group_id):
    """Gruppen-Berechtigungen speichern (Cenplex: SaveGroupRights)"""
    from models import EmployeeGroup
    from services.user_rights_service import save_group_rights as _save
    group = EmployeeGroup.query.get_or_404(group_id)
    if group.organization_id != current_user.organization_id:
        return jsonify({'error': 'Nicht erlaubt'}), 403

    data = request.get_json()
    _save(group_id, data)
    return jsonify({'success': True})
