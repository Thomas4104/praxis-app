from datetime import datetime, timedelta
from flask import render_template, request, jsonify
from flask_login import login_required, current_user
from blueprints.dashboard import dashboard_bp
from models import db, Appointment, Patient, Employee, Task, ChatMessage, TreatmentSeries
from ai.coordinator import Coordinator


@dashboard_bp.route('/')
@login_required
def index():
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today.replace(hour=23, minute=59, second=59)

    # Heutige Termine zaehlen
    employee = Employee.query.filter_by(user_id=current_user.id).first()

    if employee:
        termine_heute = Appointment.query.filter(
            Appointment.employee_id == employee.id,
            Appointment.start_time >= today,
            Appointment.start_time <= today_end,
            Appointment.status.in_(['scheduled', 'confirmed'])
        ).count()

        # Heutige Patienten (eindeutig)
        patienten_heute = db.session.query(Appointment.patient_id).filter(
            Appointment.employee_id == employee.id,
            Appointment.start_time >= today,
            Appointment.start_time <= today_end,
            Appointment.status.in_(['scheduled', 'confirmed'])
        ).distinct().count()

        # Naechste Termine
        naechste_termine = Appointment.query.filter(
            Appointment.employee_id == employee.id,
            Appointment.start_time >= datetime.now(),
            Appointment.start_time <= today_end,
            Appointment.status.in_(['scheduled', 'confirmed'])
        ).order_by(Appointment.start_time).limit(5).all()
    else:
        # Fuer Empfang: alle Termine
        termine_heute = Appointment.query.filter(
            Appointment.start_time >= today,
            Appointment.start_time <= today_end,
            Appointment.status.in_(['scheduled', 'confirmed'])
        ).count()

        patienten_heute = db.session.query(Appointment.patient_id).filter(
            Appointment.start_time >= today,
            Appointment.start_time <= today_end,
            Appointment.status.in_(['scheduled', 'confirmed'])
        ).distinct().count()

        naechste_termine = Appointment.query.filter(
            Appointment.start_time >= datetime.now(),
            Appointment.start_time <= today_end,
            Appointment.status.in_(['scheduled', 'confirmed'])
        ).order_by(Appointment.start_time).limit(5).all()

    # Offene Aufgaben
    offene_aufgaben = Task.query.filter(
        Task.organization_id == current_user.organization_id,
        Task.status.in_(['open', 'in_progress'])
    ).count()

    # Aktive Serien
    aktive_serien = TreatmentSeries.query.filter(
        TreatmentSeries.status == 'active'
    ).count()

    return render_template('dashboard/index.html',
                           termine_heute=termine_heute,
                           patienten_heute=patienten_heute,
                           offene_aufgaben=offene_aufgaben,
                           aktive_serien=aktive_serien,
                           naechste_termine=naechste_termine)


# === Chat API ===

@dashboard_bp.route('/api/chat', methods=['POST'])
@login_required
def chat():
    data = request.get_json()
    message = data.get('message', '').strip()

    if not message:
        return jsonify({'error': 'Nachricht darf nicht leer sein.'}), 400

    # Benutzer-Nachricht speichern
    user_msg = ChatMessage(
        user_id=current_user.id,
        role='user',
        content=message
    )
    db.session.add(user_msg)
    db.session.commit()

    # KI-Antwort generieren
    coordinator = Coordinator()
    try:
        response_text = coordinator.process(message, current_user)
    except Exception as e:
        response_text = f'Es ist ein Fehler aufgetreten. Bitte versuchen Sie es erneut.'

    # KI-Antwort speichern
    ai_msg = ChatMessage(
        user_id=current_user.id,
        role='assistant',
        content=response_text
    )
    db.session.add(ai_msg)
    db.session.commit()

    return jsonify({
        'response': response_text,
        'timestamp': ai_msg.created_at.strftime('%H:%M')
    })


@dashboard_bp.route('/api/chat/history', methods=['GET'])
@login_required
def chat_history():
    messages = ChatMessage.query.filter_by(
        user_id=current_user.id
    ).order_by(ChatMessage.created_at.asc()).limit(100).all()

    return jsonify({
        'messages': [{
            'role': msg.role,
            'content': msg.content,
            'timestamp': msg.created_at.strftime('%H:%M')
        } for msg in messages]
    })


@dashboard_bp.route('/api/chat/clear', methods=['POST'])
@login_required
def chat_clear():
    ChatMessage.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    return jsonify({'status': 'ok'})


@dashboard_bp.route('/api/search', methods=['GET'])
@login_required
def global_search():
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify({'results': []})

    results = []

    # Patienten suchen
    patients = Patient.query.filter(
        db.or_(
            Patient.first_name.ilike(f'%{q}%'),
            Patient.last_name.ilike(f'%{q}%'),
            Patient.patient_number.ilike(f'%{q}%'),
            (Patient.first_name + ' ' + Patient.last_name).ilike(f'%{q}%')
        ),
        Patient.is_active == True,
        Patient.organization_id == current_user.organization_id
    ).limit(5).all()

    for p in patients:
        results.append({
            'type': 'patient',
            'label': f'{p.first_name} {p.last_name}',
            'sublabel': f'Pat.-Nr. {p.patient_number}',
            'url': '#',
            'icon': 'person'
        })

    # Mitarbeiter suchen
    from models import User as UserModel
    employees = UserModel.query.filter(
        db.or_(
            UserModel.first_name.ilike(f'%{q}%'),
            UserModel.last_name.ilike(f'%{q}%')
        ),
        UserModel.is_active == True,
        UserModel.organization_id == current_user.organization_id
    ).limit(3).all()

    for e in employees:
        results.append({
            'type': 'employee',
            'label': f'{e.first_name} {e.last_name}',
            'sublabel': e.role,
            'url': '#',
            'icon': 'badge'
        })

    return jsonify({'results': results})
