"""Kalender-Blueprint: Tages-, Wochen-, Monatsansicht und API-Endpunkte"""
import json
from datetime import datetime, date, time, timedelta
from flask import render_template, request, jsonify, redirect, url_for
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload, selectinload
from models import db, Appointment, Employee, Patient, Location, Resource, \
    WorkSchedule, Absence, Holiday, TreatmentSeries, TreatmentSeriesTemplate, \
    WaitingList, ResourceBooking
from blueprints.calendar import calendar_bp
from services.settings_service import get_setting
from utils.auth import check_org


# ============================================================
# Seiten-Routen (HTML)
# ============================================================

@calendar_bp.route('/')
@login_required
def index():
    """Tagesansicht (Standard-Kalenderansicht)"""
    date_str = request.args.get('date')
    location_id = request.args.get('location_id', type=int)

    if date_str:
        try:
            current_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            current_date = date.today()
    else:
        current_date = date.today()

    org_id = current_user.organization_id
    locations = Location.query.filter_by(organization_id=org_id, is_active=True).all()
    if not location_id and locations:
        # Standard: Standort des aktuellen Benutzers
        if current_user.employee and current_user.employee.default_location_id:
            location_id = current_user.employee.default_location_id
        else:
            location_id = locations[0].id

    # Therapeuten am Standort
    employees = Employee.query.filter_by(organization_id=org_id, is_active=True) \
        .filter(Employee.default_location_id == location_id).all()
    # Fallback: alle aktiven Mitarbeiter der Organisation anzeigen
    if not employees:
        employees = Employee.query.filter_by(organization_id=org_id, is_active=True).all()

    # Raeume am Standort
    rooms = Resource.query.filter_by(
        organization_id=org_id, location_id=location_id, resource_type='room', is_active=True
    ).all()

    # Serienvorlagen fuer Quick-Add
    templates = TreatmentSeriesTemplate.query.filter_by(organization_id=org_id, is_active=True).all()

    # Kalender-Einstellungen aus Settings-Service laden
    org_id = current_user.organization_id
    calendar_settings = {
        'time_grid': get_setting(org_id, 'calendar_time_grid', 15),
        'day_start': get_setting(org_id, 'calendar_day_start', '07:00'),
        'day_end': get_setting(org_id, 'calendar_day_end', '19:00'),
        'default_duration': get_setting(org_id, 'calendar_default_duration', 30),
    }

    return render_template('calendar/index.html',
                           current_date=current_date,
                           locations=locations,
                           current_location_id=location_id,
                           employees=employees,
                           rooms=rooms,
                           templates=templates,
                           calendar_settings=calendar_settings)


@calendar_bp.route('/week')
@login_required
def week():
    """Wochenansicht fuer einen Therapeuten"""
    date_str = request.args.get('date')
    employee_id = request.args.get('employee_id', type=int)

    if date_str:
        try:
            current_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            current_date = date.today()
    else:
        current_date = date.today()

    # Montag der aktuellen Woche
    monday = current_date - timedelta(days=current_date.weekday())

    org_id = current_user.organization_id
    employees = Employee.query.filter_by(organization_id=org_id, is_active=True).all()
    if not employee_id:
        if current_user.employee:
            employee_id = current_user.employee.id
        elif employees:
            employee_id = employees[0].id

    locations = Location.query.filter_by(organization_id=org_id, is_active=True).all()
    rooms = Resource.query.filter_by(organization_id=org_id, resource_type='room', is_active=True).all()
    templates = TreatmentSeriesTemplate.query.filter_by(organization_id=org_id, is_active=True).all()

    # Kalender-Einstellungen
    org_id = current_user.organization_id
    calendar_settings = {
        'time_grid': get_setting(org_id, 'calendar_time_grid', 15),
        'day_start': get_setting(org_id, 'calendar_day_start', '07:00'),
        'day_end': get_setting(org_id, 'calendar_day_end', '19:00'),
        'default_duration': get_setting(org_id, 'calendar_default_duration', 30),
    }

    return render_template('calendar/week.html',
                           current_date=current_date,
                           monday=monday,
                           employees=employees,
                           current_employee_id=employee_id,
                           locations=locations,
                           rooms=rooms,
                           templates=templates,
                           calendar_settings=calendar_settings)


@calendar_bp.route('/month')
@login_required
def month():
    """Monatsansicht"""
    date_str = request.args.get('date')
    location_id = request.args.get('location_id', type=int)

    if date_str:
        try:
            current_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            current_date = date.today()
    else:
        current_date = date.today()

    org_id = current_user.organization_id
    locations = Location.query.filter_by(organization_id=org_id, is_active=True).all()
    if not location_id and locations:
        if current_user.employee and current_user.employee.default_location_id:
            location_id = current_user.employee.default_location_id
        else:
            location_id = locations[0].id
    calendar_settings = {
        'time_grid': get_setting(org_id, 'calendar_time_grid', 15),
        'day_start': get_setting(org_id, 'calendar_day_start', '07:00'),
        'day_end': get_setting(org_id, 'calendar_day_end', '19:00'),
        'default_duration': get_setting(org_id, 'calendar_default_duration', 30),
    }

    return render_template('calendar/month.html',
                           current_date=current_date,
                           locations=locations,
                           current_location_id=location_id,
                           calendar_settings=calendar_settings)


@calendar_bp.route('/serie-planen')
@login_required
def serie_planen():
    """Serienplanung Wizard"""
    org_id = current_user.organization_id
    employees = Employee.query.filter_by(organization_id=org_id, is_active=True).all()
    templates = TreatmentSeriesTemplate.query.filter_by(organization_id=org_id, is_active=True).all()
    locations = Location.query.filter_by(organization_id=org_id, is_active=True).all()

    return render_template('calendar/serie_planen.html',
                           employees=employees,
                           templates=templates,
                           locations=locations)


# ============================================================
# API-Endpunkte (JSON)
# ============================================================

@calendar_bp.route('/api/appointments')
@login_required
def api_get_appointments():
    """Termine fuer einen Tag/Zeitraum laden"""
    date_str = request.args.get('date')
    start_str = request.args.get('start')
    end_str = request.args.get('end')
    location_id = request.args.get('location_id', type=int)
    employee_ids_str = request.args.get('employee_ids', '')

    if start_str and end_str:
        try:
            start_dt = datetime.strptime(start_str, '%Y-%m-%d')
            end_dt = datetime.strptime(end_str, '%Y-%m-%d') + timedelta(days=1)
        except ValueError:
            return jsonify({'error': 'Ungültiges Datumsformat'}), 400
    elif date_str:
        try:
            day = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'Ungültiges Datumsformat'}), 400
        start_dt = datetime.combine(day, time(0, 0))
        end_dt = datetime.combine(day + timedelta(days=1), time(0, 0))
    else:
        day = date.today()
        start_dt = datetime.combine(day, time(0, 0))
        end_dt = datetime.combine(day + timedelta(days=1), time(0, 0))

    # Multi-Tenancy: nur Termine der eigenen Organisation (ueber Employee)
    org_id = current_user.organization_id
    query = Appointment.query.join(
        Employee, Appointment.employee_id == Employee.id
    ).filter(
        Employee.organization_id == org_id,
        Appointment.start_time >= start_dt,
        Appointment.start_time < end_dt
    )

    if location_id:
        query = query.filter(Appointment.location_id == location_id)

    if employee_ids_str:
        try:
            emp_ids = [int(x) for x in employee_ids_str.split(',') if x.strip()]
            if emp_ids:
                query = query.filter(Appointment.employee_id.in_(emp_ids))
        except ValueError:
            pass

    # Eager Loading: Patient, Employee->User, Resource und Serie->Template in einer Query
    # Verhindert N+1 Queries (vorher ~150 Queries pro Tagesansicht)
    query = query.options(
        joinedload(Appointment.patient),
        joinedload(Appointment.employee).joinedload(Employee.user),
        joinedload(Appointment.resource),
        joinedload(Appointment.series).joinedload(TreatmentSeries.template)
    )

    appointments = query.order_by(Appointment.start_time).all()

    result = []
    for a in appointments:
        patient_name = ''
        if a.patient:
            patient_name = f'{a.patient.last_name} {a.patient.first_name}'

        employee_name = ''
        employee_color = '#4a90d9'
        if a.employee:
            if a.employee.user:
                employee_name = f'{a.employee.user.first_name} {a.employee.user.last_name}'
            employee_color = a.employee.color_code or '#4a90d9'

        # Serieninfo effizient aus eager-loaded Daten
        series_total = None
        series_counter = None
        if a.series_id and a.series and a.series.template:
            series_total = a.series.template.num_appointments
        if a.series_number and series_total:
            series_counter = f'{a.series_number}/{series_total}'
        elif a.series_number:
            series_counter = f'{a.series_number}'

        # Dokumentation vorhanden?
        is_documented = bool(
            a.soap_subjective or a.soap_objective or
            a.soap_assessment or a.soap_plan
        )

        result.append({
            'id': a.id,
            'patient_id': a.patient_id,
            'patient_name': patient_name,
            'employee_id': a.employee_id,
            'employee_name': employee_name,
            'employee_color': employee_color,
            'location_id': a.location_id,
            'resource_id': a.resource_id,
            'resource_name': a.resource.name if a.resource else '',
            'start_time': a.start_time.isoformat(),
            'end_time': a.end_time.isoformat(),
            'duration_minutes': a.duration_minutes,
            'status': a.status,
            'appointment_type': a.appointment_type,
            'title': a.title or '',
            'notes': a.notes or '',
            'soap_subjective': a.soap_subjective or '',
            'soap_objective': a.soap_objective or '',
            'soap_assessment': a.soap_assessment or '',
            'soap_plan': a.soap_plan or '',
            'series_id': a.series_id,
            'series_number': a.series_number,
            'series_total': series_total,
            'series_counter': series_counter,
            'is_documented': is_documented,
            'is_billed': False,  # TODO: Rechnungsstatus pruefen
            'is_domicile': a.is_domicile or False,
            'is_termin_0': a.is_termin_0 or False,
            'is_group': a.is_group or False,
            'color_category': a.color_category,
            'cancellation_reason': a.cancellation_reason or '',
            'therapist_name': employee_name,
        })

    return jsonify(result)


@calendar_bp.route('/api/appointments', methods=['POST'])
@login_required
def api_create_appointment():
    """Neuen Termin erstellen"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Keine Daten erhalten'}), 400

    required = ['patient_id', 'employee_id', 'start_time', 'duration_minutes']
    for field in required:
        if field not in data:
            return jsonify({'error': f'Pflichtfeld fehlt: {field}'}), 400

    try:
        start = datetime.fromisoformat(data['start_time'])
    except (ValueError, TypeError):
        return jsonify({'error': 'Ungültiges Startzeit-Format'}), 400

    duration = int(data['duration_minutes'])
    end = start + timedelta(minutes=duration)

    # Multi-Tenancy: Patient und Mitarbeiter muessen zur Organisation gehoeren
    org_id = current_user.organization_id
    patient = Patient.query.get_or_404(data['patient_id'])
    check_org(patient)
    emp = Employee.query.get_or_404(data['employee_id'])
    check_org(emp)
    if data.get('location_id'):
        loc = Location.query.get_or_404(data['location_id'])
        check_org(loc)

    # Doppelbuchungs-Pruefung (Employee ist bereits org-geprueft)
    existing = Appointment.query.join(Employee).filter(
        Employee.organization_id == org_id,
        Appointment.employee_id == data['employee_id'],
        Appointment.status.notin_(['cancelled', 'no_show']),
        Appointment.start_time < end,
        Appointment.end_time > start
    ).first()

    if existing:
        return jsonify({
            'error': 'Terminüberschneidung: Der Therapeut hat bereits einen Termin zu dieser Zeit.',
            'conflict_id': existing.id
        }), 409

    appointment = Appointment(
        patient_id=data['patient_id'],
        employee_id=data['employee_id'],
        location_id=data.get('location_id'),
        resource_id=data.get('resource_id'),
        series_id=data.get('series_id'),
        start_time=start,
        end_time=end,
        duration_minutes=duration,
        status='scheduled',
        appointment_type=data.get('appointment_type', 'treatment'),
        title=data.get('title', ''),
        notes=data.get('notes', ''),
        is_domicile=data.get('is_domicile', False)
    )
    # Farbkategorie setzen falls angegeben
    if data.get('color_category'):
        appointment.color_category = data['color_category']

    # Automatische Seriennummer vergeben wenn Serie vorhanden
    series_id = data.get('series_id')
    if series_id:
        # Naechste Seriennummer bestimmen (Termin 0 zaehlt nicht)
        max_series_nr = db.session.query(db.func.max(Appointment.series_number)).filter(
            Appointment.series_id == series_id,
            Appointment.is_termin_0 == False
        ).scalar() or 0
        appointment.series_number = max_series_nr + 1

    db.session.add(appointment)

    # Raum-Buchung erstellen wenn Raum angegeben
    if data.get('resource_id'):
        booking = ResourceBooking(
            resource_id=data['resource_id'],
            appointment_id=appointment.id,
            start_time=start,
            end_time=end
        )
        db.session.add(booking)

    db.session.commit()

    return jsonify({
        'success': True,
        'id': appointment.id,
        'message': 'Termin wurde erstellt.'
    }), 201


@calendar_bp.route('/api/appointments/<int:appointment_id>', methods=['PUT'])
@login_required
def api_update_appointment(appointment_id):
    """Termin aktualisieren"""
    appointment = Appointment.query.get_or_404(appointment_id)
    # IDOR-Schutz: Mitarbeiter des Termins muss zur Organisation gehoeren
    emp = Employee.query.get_or_404(appointment.employee_id)
    check_org(emp)
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Keine Daten erhalten'}), 400

    if 'start_time' in data:
        try:
            new_start = datetime.fromisoformat(data['start_time'])
        except (ValueError, TypeError):
            return jsonify({'error': 'Ungültiges Startzeit-Format'}), 400

        duration = data.get('duration_minutes', appointment.duration_minutes)
        new_end = new_start + timedelta(minutes=int(duration))

        appointment.start_time = new_start
        appointment.end_time = new_end
        appointment.duration_minutes = int(duration)

    if 'employee_id' in data:
        appointment.employee_id = data['employee_id']
    if 'resource_id' in data:
        appointment.resource_id = data['resource_id']
    if 'notes' in data:
        appointment.notes = data['notes']
    if 'title' in data:
        appointment.title = data['title']
    if 'appointment_type' in data:
        appointment.appointment_type = data['appointment_type']
    if 'soap_subjective' in data:
        appointment.soap_subjective = data['soap_subjective']
    if 'soap_objective' in data:
        appointment.soap_objective = data['soap_objective']
    if 'soap_assessment' in data:
        appointment.soap_assessment = data['soap_assessment']
    if 'soap_plan' in data:
        appointment.soap_plan = data['soap_plan']
    if 'series_id' in data:
        appointment.series_id = data['series_id']
    if 'location_id' in data:
        appointment.location_id = data['location_id']
    if 'color_category' in data:
        appointment.color_category = data['color_category']

    db.session.commit()
    return jsonify({'success': True, 'message': 'Termin wurde aktualisiert.'})


@calendar_bp.route('/api/appointments/<int:appointment_id>/move', methods=['PUT'])
@login_required
def api_move_appointment(appointment_id):
    """Termin verschieben (Drag & Drop)"""
    appointment = Appointment.query.get_or_404(appointment_id)
    # IDOR-Schutz
    emp = Employee.query.get_or_404(appointment.employee_id)
    check_org(emp)
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Keine Daten erhalten'}), 400

    try:
        new_start = datetime.fromisoformat(data['new_start_time'])
    except (ValueError, TypeError, KeyError):
        return jsonify({'error': 'Ungültige neue Startzeit'}), 400

    new_employee_id = data.get('new_employee_id', appointment.employee_id)
    new_end = new_start + timedelta(minutes=appointment.duration_minutes)

    # Doppelbuchungs-Pruefung (eigenen Termin ausschliessen)
    existing = Appointment.query.join(Employee).filter(
        Employee.organization_id == current_user.organization_id,
        Appointment.employee_id == new_employee_id,
        Appointment.id != appointment_id,
        Appointment.status.notin_(['cancelled', 'no_show']),
        Appointment.start_time < new_end,
        Appointment.end_time > new_start
    ).first()

    if existing:
        return jsonify({
            'error': 'Terminüberschneidung: Der Therapeut hat bereits einen Termin zu dieser Zeit.',
            'conflict_id': existing.id
        }), 409

    appointment.start_time = new_start
    appointment.end_time = new_end
    appointment.employee_id = new_employee_id

    # Ressource aktualisieren falls mitgegeben
    if 'new_resource_id' in data:
        new_resource_id = data.get('new_resource_id')
        appointment.resource_id = new_resource_id
        # Bestehende Raum-Buchung aktualisieren
        ResourceBooking.query.filter_by(appointment_id=appointment_id).delete()
        if new_resource_id:
            booking = ResourceBooking(
                resource_id=new_resource_id,
                appointment_id=appointment_id,
                start_time=new_start,
                end_time=new_end
            )
            db.session.add(booking)

    db.session.commit()
    return jsonify({'success': True, 'message': 'Termin wurde verschoben.'})


@calendar_bp.route('/api/appointments/<int:appointment_id>/status', methods=['PUT'])
@login_required
def api_update_status(appointment_id):
    """Termin-Status aendern"""
    appointment = Appointment.query.get_or_404(appointment_id)
    # IDOR-Schutz
    emp = Employee.query.get_or_404(appointment.employee_id)
    check_org(emp)
    data = request.get_json()

    valid_statuses = ['scheduled', 'confirmed', 'appeared', 'cancelled', 'no_show']
    new_status = data.get('status')
    if new_status not in valid_statuses:
        return jsonify({'error': f'Ungültiger Status. Erlaubt: {", ".join(valid_statuses)}'}), 400

    appointment.status = new_status
    db.session.commit()
    return jsonify({'success': True, 'message': f'Status auf "{new_status}" geändert.'})


@calendar_bp.route('/api/appointments/<int:appointment_id>', methods=['DELETE'])
@login_required
def api_delete_appointment(appointment_id):
    """Termin loeschen (nur Admin)"""
    if current_user.role != 'admin':
        return jsonify({'error': 'Nur Administratoren dürfen Termine löschen.'}), 403

    appointment = Appointment.query.get_or_404(appointment_id)
    # IDOR-Schutz
    emp = Employee.query.get_or_404(appointment.employee_id)
    check_org(emp)
    # Zugehoerige Raum-Buchungen loeschen
    ResourceBooking.query.filter_by(appointment_id=appointment_id).delete()
    db.session.delete(appointment)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Termin wurde gelöscht.'})


@calendar_bp.route('/api/appointments/<int:appointment_id>/cancel', methods=['POST'])
@login_required
def api_cancel_appointment(appointment_id):
    """Termin absagen mit optionalem 'Trotzdem abrechnen'"""
    appointment = Appointment.query.get_or_404(appointment_id)
    emp = Employee.query.get_or_404(appointment.employee_id)
    check_org(emp)
    data = request.get_json() or {}

    appointment.status = 'cancelled'
    appointment.cancellation_reason = data.get('reason', '')

    # Trotzdem abrechnen (Spaetabsage)
    if data.get('charge_despite_cancel'):
        appointment.is_termin_0 = True
        appointment.charge_despite_cancel = True
        if data.get('fee_amount'):
            appointment.cancellation_fee = float(data['fee_amount'])
    else:
        appointment.is_termin_0 = False
        appointment.charge_despite_cancel = False
        if data.get('charge_fee'):
            appointment.cancellation_fee = float(data.get('fee_amount', 0))

    db.session.commit()

    from services.audit_service import log_action
    log_action('cancel', 'appointment', appointment_id, changes={
        'status': {'old': 'scheduled', 'new': 'cancelled'},
        'charge_despite_cancel': {'new': appointment.charge_despite_cancel},
        'reason': {'new': appointment.cancellation_reason},
    })

    return jsonify({
        'success': True,
        'message': 'Termin wurde abgesagt.',
        'is_termin_0': appointment.is_termin_0,
        'charge_despite_cancel': appointment.charge_despite_cancel,
    })


@calendar_bp.route('/api/available-slots')
@login_required
def api_available_slots():
    """Verfuegbare Slots finden (nutzt Constraint-Solver)"""
    employee_id = request.args.get('employee_id', type=int)
    duration = request.args.get('duration', 30, type=int)
    date_str = request.args.get('date')
    location_id = request.args.get('location_id', type=int)
    num_slots = request.args.get('num_slots', 5, type=int)

    if not employee_id:
        return jsonify({'error': 'employee_id ist erforderlich'}), 400

    start_date = date.today()
    if date_str:
        try:
            start_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            pass

    from ai.constraint_solver import find_available_slots
    slots = find_available_slots(
        employee_id=employee_id,
        location_id=location_id,
        duration_minutes=duration,
        num_slots=num_slots,
        min_interval_days=0,
        start_date=start_date
    )

    return jsonify(slots)


@calendar_bp.route('/api/work-schedules')
@login_required
def api_get_work_schedules():
    """Arbeitszeiten fuer Therapeuten laden"""
    employee_ids_str = request.args.get('employee_ids', '')
    date_str = request.args.get('date')

    if date_str:
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            target_date = date.today()
    else:
        target_date = date.today()

    day_of_week = target_date.weekday()

    query = WorkSchedule.query.filter_by(day_of_week=day_of_week)

    if employee_ids_str:
        try:
            emp_ids = [int(x) for x in employee_ids_str.split(',') if x.strip()]
            if emp_ids:
                query = query.filter(WorkSchedule.employee_id.in_(emp_ids))
        except ValueError:
            pass

    schedules = query.all()
    result = {}
    for ws in schedules:
        emp_id = str(ws.employee_id)
        if emp_id not in result:
            result[emp_id] = []
        result[emp_id].append({
            'start_time': ws.start_time.strftime('%H:%M'),
            'end_time': ws.end_time.strftime('%H:%M'),
            'work_type': ws.work_type
        })

    return jsonify(result)


@calendar_bp.route('/api/absences')
@login_required
def api_get_absences():
    """Absenzen laden"""
    date_str = request.args.get('date')
    start_str = request.args.get('start')
    end_str = request.args.get('end')

    if start_str and end_str:
        try:
            start_d = datetime.strptime(start_str, '%Y-%m-%d').date()
            end_d = datetime.strptime(end_str, '%Y-%m-%d').date()
        except ValueError:
            start_d = date.today()
            end_d = date.today()
    elif date_str:
        try:
            start_d = datetime.strptime(date_str, '%Y-%m-%d').date()
            end_d = start_d
        except ValueError:
            start_d = date.today()
            end_d = date.today()
    else:
        start_d = date.today()
        end_d = date.today()

    # Multi-Tenancy: nur Absenzen von Mitarbeitern der eigenen Organisation
    absences = Absence.query.join(
        Employee, Absence.employee_id == Employee.id
    ).filter(
        Employee.organization_id == current_user.organization_id,
        Absence.start_date <= end_d,
        Absence.end_date >= start_d,
        Absence.status == 'approved'
    ).all()

    result = []
    for a in absences:
        result.append({
            'employee_id': a.employee_id,
            'absence_type': a.absence_type,
            'start_date': a.start_date.isoformat(),
            'end_date': a.end_date.isoformat(),
            'notes': a.notes or ''
        })

    return jsonify(result)


@calendar_bp.route('/api/holidays')
@login_required
def api_get_holidays():
    """Feiertage laden"""
    date_str = request.args.get('date')
    start_str = request.args.get('start')
    end_str = request.args.get('end')

    if start_str and end_str:
        try:
            start_d = datetime.strptime(start_str, '%Y-%m-%d').date()
            end_d = datetime.strptime(end_str, '%Y-%m-%d').date()
        except ValueError:
            start_d = date.today()
            end_d = date.today()
    elif date_str:
        try:
            start_d = datetime.strptime(date_str, '%Y-%m-%d').date()
            end_d = start_d
        except ValueError:
            start_d = date.today()
            end_d = date.today()
    else:
        year = date.today().year
        start_d = date(year, 1, 1)
        end_d = date(year, 12, 31)

    holidays = Holiday.query.filter(
        Holiday.date >= start_d,
        Holiday.date <= end_d
    ).all()

    return jsonify([{
        'name': h.name,
        'date': h.date.isoformat()
    } for h in holidays])


@calendar_bp.route('/api/patients/search')
@login_required
def api_search_patients():
    """Patienten-Suche fuer Autocomplete"""
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify([])

    patients = Patient.query.filter(
        Patient.organization_id == current_user.organization_id,
        Patient.is_active == True,
        db.or_(
            Patient.first_name.ilike(f'%{q}%'),
            Patient.last_name.ilike(f'%{q}%'),
            Patient.patient_number.ilike(f'%{q}%'),
            (Patient.first_name + ' ' + Patient.last_name).ilike(f'%{q}%')
        )
    ).limit(10).all()

    return jsonify([{
        'id': p.id,
        'name': f'{p.first_name} {p.last_name}',
        'patient_number': p.patient_number,
        'date_of_birth': p.date_of_birth.strftime('%d.%m.%Y') if p.date_of_birth else ''
    } for p in patients])


@calendar_bp.route('/api/patient-series/<int:patient_id>')
@login_required
def api_patient_series(patient_id):
    """Aktive Serien eines Patienten"""
    patient = Patient.query.get_or_404(patient_id)
    check_org(patient)
    series = TreatmentSeries.query.filter_by(
        patient_id=patient_id, status='active'
    ).all()

    return jsonify([{
        'id': s.id,
        'name': s.template.name if s.template else 'Serie',
        'template_id': s.template_id,
        'therapist_id': s.therapist_id,
        'diagnosis': f'{s.diagnosis_code}: {s.diagnosis_text}' if s.diagnosis_text else ''
    } for s in series])


@calendar_bp.route('/api/month-data')
@login_required
def api_month_data():
    """Daten fuer Monatsansicht"""
    year = request.args.get('year', date.today().year, type=int)
    month_num = request.args.get('month', date.today().month, type=int)
    location_id = request.args.get('location_id', type=int)

    import calendar as cal_mod
    _, num_days = cal_mod.monthrange(year, month_num)

    start_dt = datetime(year, month_num, 1)
    end_dt = datetime(year, month_num, num_days, 23, 59, 59)

    org_id = current_user.organization_id
    query = Appointment.query.join(
        Employee, Appointment.employee_id == Employee.id
    ).filter(
        Employee.organization_id == org_id,
        Appointment.start_time >= start_dt,
        Appointment.start_time <= end_dt,
        Appointment.status.notin_(['cancelled'])
    )
    if location_id:
        query = query.filter(Appointment.location_id == location_id)

    # Eager Loading: Employee und Patient fuer Detailansicht
    query = query.options(
        joinedload(Appointment.employee).joinedload(Employee.user),
        joinedload(Appointment.patient)
    )

    appointments = query.all()

    # Nach Tag gruppieren mit Termin-Details
    days_data = {}
    for a in appointments:
        day_key = a.start_time.strftime('%Y-%m-%d')
        if day_key not in days_data:
            days_data[day_key] = {'count': 0, 'employees': {}, 'appointments': []}
        days_data[day_key]['count'] += 1
        emp_id = str(a.employee_id)
        if emp_id not in days_data[day_key]['employees']:
            color = a.employee.color_code if a.employee else '#4a90d9'
            days_data[day_key]['employees'][emp_id] = {
                'color': color,
                'count': 0
            }
        days_data[day_key]['employees'][emp_id]['count'] += 1

        # Termin-Details fuer Monatsansicht
        patient_name = ''
        if a.patient:
            patient_name = f'{a.patient.first_name} {a.patient.last_name}'
        employee_name = ''
        if a.employee and a.employee.user:
            employee_name = f'{a.employee.user.first_name} {a.employee.user.last_name}'

        days_data[day_key]['appointments'].append({
            'id': a.id,
            'start_time': a.start_time.isoformat(),
            'patient_name': patient_name,
            'employee_name': employee_name,
            'employee_color': a.employee.color_code if a.employee else '#4a90d9',
            'status': a.status,
            'appointment_type': a.appointment_type
        })

    # Termine innerhalb jedes Tages nach Startzeit sortieren
    for day_key in days_data:
        days_data[day_key]['appointments'].sort(key=lambda x: x['start_time'])

    # Feiertage
    holidays = Holiday.query.filter(
        Holiday.date >= start_dt.date(),
        Holiday.date <= end_dt.date()
    ).all()
    holidays_map = {h.date.isoformat(): h.name for h in holidays}

    return jsonify({
        'days': days_data,
        'holidays': holidays_map
    })


@calendar_bp.route('/api/waiting-list')
@login_required
def api_get_waiting_list():
    """Warteliste laden"""
    # Multi-Tenancy: Warteliste ueber Patient filtern
    entries = WaitingList.query.join(
        Patient, WaitingList.patient_id == Patient.id
    ).filter(
        Patient.organization_id == current_user.organization_id,
        WaitingList.status == 'waiting'
    ).order_by(WaitingList.priority.desc(), WaitingList.created_at).all()

    return jsonify([{
        'id': e.id,
        'patient_name': f'{e.patient.first_name} {e.patient.last_name}' if e.patient else '',
        'patient_id': e.patient_id,
        'template_name': e.template.name if e.template else '',
        'preferred_employee': f'{e.preferred_employee.user.first_name} {e.preferred_employee.user.last_name}' if e.preferred_employee and e.preferred_employee.user else '',
        'preferred_days': json.loads(e.preferred_days_json) if e.preferred_days_json else [],
        'preferred_times': json.loads(e.preferred_times_json) if e.preferred_times_json else [],
        'priority': e.priority,
        'notes': e.notes or '',
        'status': e.status,
        'created_at': e.created_at.strftime('%d.%m.%Y')
    } for e in entries])


@calendar_bp.route('/api/waiting-list', methods=['POST'])
@login_required
def api_add_waiting_list():
    """Eintrag zur Warteliste hinzufuegen"""
    data = request.get_json()
    if not data or not data.get('patient_id'):
        return jsonify({'error': 'Patient ist erforderlich'}), 400

    # Multi-Tenancy: Patient muss zur Organisation gehoeren
    patient = Patient.query.get_or_404(data['patient_id'])
    check_org(patient)

    entry = WaitingList(
        patient_id=data['patient_id'],
        template_id=data.get('template_id'),
        preferred_employee_id=data.get('preferred_employee_id'),
        preferred_days_json=json.dumps(data.get('preferred_days', [])),
        preferred_times_json=json.dumps(data.get('preferred_times', [])),
        priority=data.get('priority', 0),
        notes=data.get('notes', ''),
        status='waiting'
    )
    db.session.add(entry)
    db.session.commit()

    return jsonify({'success': True, 'id': entry.id, 'message': 'Patient auf Warteliste gesetzt.'}), 201


# ============================================================
# Gruppentherapie: Teilnehmer-Verwaltung
# ============================================================

@calendar_bp.route('/api/appointments/<int:appointment_id>/participants', methods=['GET'])
@login_required
def api_get_participants(appointment_id):
    """Teilnehmer einer Gruppentherapie laden"""
    from models import GroupAppointmentParticipant
    appointment = Appointment.query.get_or_404(appointment_id)
    emp = Employee.query.get_or_404(appointment.employee_id)
    check_org(emp)

    participants = GroupAppointmentParticipant.query.filter_by(
        appointment_id=appointment_id
    ).all()

    return jsonify([{
        'id': p.id,
        'patient_id': p.patient_id,
        'patient_name': f'{p.patient.last_name}, {p.patient.first_name}' if p.patient else '',
        'series_id': p.series_id,
        'status': p.status,
        'notes': p.notes or '',
    } for p in participants])


@calendar_bp.route('/api/appointments/<int:appointment_id>/participants', methods=['POST'])
@login_required
def api_add_participant(appointment_id):
    """Teilnehmer zu Gruppentherapie hinzufuegen"""
    from models import GroupAppointmentParticipant
    appointment = Appointment.query.get_or_404(appointment_id)
    emp = Employee.query.get_or_404(appointment.employee_id)
    check_org(emp)

    if not appointment.is_group:
        return jsonify({'error': 'Kein Gruppentherapie-Termin'}), 400

    data = request.get_json() or {}
    patient_id = data.get('patient_id')
    if not patient_id:
        return jsonify({'error': 'patient_id erforderlich'}), 400

    # Pruefen ob bereits Teilnehmer
    existing = GroupAppointmentParticipant.query.filter_by(
        appointment_id=appointment_id,
        patient_id=patient_id,
    ).first()
    if existing:
        return jsonify({'error': 'Patient ist bereits Teilnehmer'}), 400

    # Max-Teilnehmer pruefen
    if appointment.max_participants:
        current_count = GroupAppointmentParticipant.query.filter_by(
            appointment_id=appointment_id
        ).count()
        if current_count >= appointment.max_participants:
            return jsonify({'error': f'Maximale Teilnehmerzahl ({appointment.max_participants}) erreicht'}), 400

    participant = GroupAppointmentParticipant(
        appointment_id=appointment_id,
        patient_id=patient_id,
        series_id=data.get('series_id'),
        status='scheduled',
    )
    db.session.add(participant)
    db.session.commit()

    return jsonify({'id': participant.id, 'message': 'Teilnehmer hinzugefuegt'}), 201


@calendar_bp.route('/api/appointments/<int:appointment_id>/participants/<int:participant_id>', methods=['DELETE'])
@login_required
def api_remove_participant(appointment_id, participant_id):
    """Teilnehmer aus Gruppentherapie entfernen"""
    from models import GroupAppointmentParticipant
    participant = GroupAppointmentParticipant.query.get_or_404(participant_id)

    appointment = Appointment.query.get_or_404(appointment_id)
    emp = Employee.query.get_or_404(appointment.employee_id)
    check_org(emp)

    db.session.delete(participant)
    db.session.commit()
    return jsonify({'message': 'Teilnehmer entfernt'})


@calendar_bp.route('/api/appointment-config')
@login_required
def api_appointment_config():
    """Terminkarten-Konfiguration laden (Farben, Darstellung)"""
    import json

    org_id = current_user.organization_id
    config_str = get_setting(org_id, 'appointment_display_config', '{}')

    try:
        config = json.loads(config_str)
    except (json.JSONDecodeError, TypeError):
        config = {}

    # Standard-Farbkategorien falls keine konfiguriert
    if 'color_categories' not in config:
        config['color_categories'] = [
            {'name': 'Einzeltermin', 'color': '#6c757d'},
            {'name': 'Erstbefund', 'color': '#0d6efd'},
            {'name': 'Domizilbehandlung', 'color': '#198754'},
            {'name': 'Gruppentherapie', 'color': '#6f42c1'},
            {'name': 'Besprechung', 'color': '#fd7e14'},
        ]

    # Domizil- und Gruppen-Farbe
    config['domicile_color'] = '#198754'
    config['group_color'] = '#6f42c1'

    return jsonify(config)


@calendar_bp.route('/api/resources')
@login_required
def api_get_resources():
    """Ressourcen (Raeume) fuer einen Standort laden"""
    location_id = request.args.get('location_id', type=int)
    org_id = current_user.organization_id

    query = Resource.query.filter_by(
        organization_id=org_id,
        resource_type='room',
        is_active=True
    )
    if location_id:
        query = query.filter_by(location_id=location_id)

    resources = query.order_by(Resource.name).all()
    return jsonify([{
        'id': r.id,
        'name': r.name,
        'location_id': r.location_id,
        'resource_type': r.resource_type,
    } for r in resources])
