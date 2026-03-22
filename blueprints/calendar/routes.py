# Kalender-Routen: Tagesansicht, Wochenansicht, Termin-API

from datetime import datetime, date, time, timedelta
from flask import render_template, request, jsonify
from flask_login import login_required, current_user
from blueprints.calendar import calendar_bp
from models import db, Appointment, Employee, Patient, User, WorkSchedule


@calendar_bp.route('/')
@login_required
def index():
    """Kalenderansicht (Tag/Woche)."""
    view = request.args.get('view', 'day')  # day oder week
    datum_str = request.args.get('date', date.today().isoformat())
    try:
        current_date = datetime.strptime(datum_str, '%Y-%m-%d').date()
    except ValueError:
        current_date = date.today()

    therapeuten = Employee.query.filter_by(is_active=True).join(User).filter(
        User.role == 'therapist'
    ).all()

    return render_template('calendar/index.html',
                           view=view,
                           current_date=current_date,
                           therapeuten=therapeuten)


@calendar_bp.route('/api/appointments')
@login_required
def api_appointments():
    """API: Termine für einen Zeitraum laden."""
    start_str = request.args.get('start', date.today().isoformat())
    end_str = request.args.get('end', date.today().isoformat())
    employee_id = request.args.get('employee_id', type=int)

    try:
        start_date = datetime.strptime(start_str, '%Y-%m-%d')
        end_date = datetime.strptime(end_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
    except ValueError:
        return jsonify({'error': 'Ungültiges Datum'}), 400

    query = Appointment.query.filter(
        Appointment.start_time >= start_date,
        Appointment.start_time <= end_date,
        Appointment.status != 'cancelled'
    )

    if employee_id:
        query = query.filter_by(employee_id=employee_id)

    termine = query.order_by(Appointment.start_time).all()

    return jsonify([{
        'id': t.id,
        'title': t.patient.full_name,
        'start': t.start_time.isoformat(),
        'end': t.end_time.isoformat(),
        'employee_id': t.employee_id,
        'employee_name': t.employee.display_name,
        'color': t.employee.color_code if t.employee else '#4a90d9',
        'status': t.status,
        'patient_id': t.patient_id,
        'notes': t.notes or '',
    } for t in termine])


@calendar_bp.route('/api/appointments', methods=['POST'])
@login_required
def api_create_appointment():
    """API: Termin erstellen."""
    data = request.get_json()

    patient_id = data.get('patient_id')
    employee_id = data.get('employee_id')
    start_str = data.get('start')
    end_str = data.get('end')

    if not all([patient_id, employee_id, start_str, end_str]):
        return jsonify({'error': 'Fehlende Pflichtfelder'}), 400

    patient = Patient.query.get(patient_id)
    employee = Employee.query.get(employee_id)
    if not patient or not employee:
        return jsonify({'error': 'Patient oder Therapeut nicht gefunden'}), 404

    start_time = datetime.fromisoformat(start_str)
    end_time = datetime.fromisoformat(end_str)

    # Überschneidung prüfen
    overlap = Appointment.query.filter(
        Appointment.employee_id == employee_id,
        Appointment.status != 'cancelled',
        Appointment.start_time < end_time,
        Appointment.end_time > start_time,
    ).first()

    if overlap:
        return jsonify({'error': 'Terminkonflikt'}), 409

    # Standort aus Arbeitszeit ermitteln
    schedule = WorkSchedule.query.filter_by(
        employee_id=employee_id,
        day_of_week=start_time.weekday()
    ).first()

    termin = Appointment(
        patient_id=patient_id,
        employee_id=employee_id,
        location_id=schedule.location_id if schedule else None,
        start_time=start_time,
        end_time=end_time,
        status='scheduled',
        type=data.get('type', 'treatment'),
        notes=data.get('notes', ''),
    )
    db.session.add(termin)
    db.session.commit()

    return jsonify({
        'id': termin.id,
        'message': f'Termin erstellt: {patient.full_name} bei {employee.display_name}',
    }), 201


@calendar_bp.route('/api/appointments/<int:id>', methods=['PUT'])
@login_required
def api_update_appointment(id):
    """API: Termin verschieben (Drag & Drop)."""
    termin = Appointment.query.get_or_404(id)
    data = request.get_json()

    new_start = datetime.fromisoformat(data['start'])
    new_end = datetime.fromisoformat(data['end'])
    new_employee_id = data.get('employee_id', termin.employee_id)

    # Überschneidung prüfen
    overlap = Appointment.query.filter(
        Appointment.employee_id == new_employee_id,
        Appointment.id != termin.id,
        Appointment.status != 'cancelled',
        Appointment.start_time < new_end,
        Appointment.end_time > new_start,
    ).first()

    if overlap:
        return jsonify({'error': 'Terminkonflikt'}), 409

    termin.start_time = new_start
    termin.end_time = new_end
    termin.employee_id = new_employee_id
    db.session.commit()

    return jsonify({'message': 'Termin verschoben'})


@calendar_bp.route('/api/appointments/<int:id>', methods=['DELETE'])
@login_required
def api_delete_appointment(id):
    """API: Termin absagen."""
    termin = Appointment.query.get_or_404(id)
    termin.status = 'cancelled'
    termin.cancellation_reason = request.get_json().get('reason', '')
    db.session.commit()

    return jsonify({'message': 'Termin abgesagt'})


@calendar_bp.route('/api/work-schedules')
@login_required
def api_work_schedules():
    """API: Arbeitszeiten für alle Therapeuten laden."""
    schedules = WorkSchedule.query.filter_by(work_type='working').all()

    result = {}
    for s in schedules:
        emp_id = str(s.employee_id)
        if emp_id not in result:
            result[emp_id] = []
        result[emp_id].append({
            'day': s.day_of_week,
            'start': s.start_time.strftime('%H:%M'),
            'end': s.end_time.strftime('%H:%M'),
        })

    return jsonify(result)
