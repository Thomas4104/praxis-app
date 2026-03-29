"""Routen fuer Aufgaben-Verwaltung"""
from datetime import datetime, date, timezone
from flask import render_template, request, jsonify, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from blueprints.tasks import tasks_bp
from models import (db, Task, TaskComment, Patient, User, Employee,
                    MissionToEmployee, MissionResponse, MissionNote)
from utils.auth import check_org, get_org_id


@tasks_bp.route('/')
@login_required
def index():
    """Aufgaben-Uebersicht"""
    tab = request.args.get('tab', 'mine')
    category = request.args.get('category', '')
    priority = request.args.get('priority', '')
    status = request.args.get('status', '')

    query = Task.query.filter_by(organization_id=current_user.organization_id)

    if tab == 'mine':
        query = query.filter(
            db.or_(
                Task.assigned_to_id == current_user.id,
                Task.created_by_id == current_user.id
            )
        ).filter(Task.status != 'completed')
    elif tab == 'all':
        query = query.filter(Task.status != 'completed')
    elif tab == 'completed':
        query = query.filter(Task.status == 'completed')

    if category:
        query = query.filter(Task.category == category)
    if priority:
        query = query.filter(Task.priority == priority)
    if status and tab != 'completed':
        query = query.filter(Task.status == status)

    # Sortierung nach Prioritaet
    priority_order = db.case(
        (Task.priority == 'critical', 0),
        (Task.priority == 'high', 1),
        (Task.priority == 'normal', 2),
        (Task.priority == 'low', 3),
        else_=4
    )
    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = 25
    query = query.order_by(priority_order, Task.due_date.asc().nullslast(), Task.created_at.desc())
    total = query.count()
    aufgaben = query.offset((page - 1) * per_page).limit(per_page).all()
    total_pages = (total + per_page - 1) // per_page

    # Mitarbeiter fuer Zuweisung (User-Objekte)
    mitarbeiter = User.query.filter_by(
        organization_id=current_user.organization_id, is_active=True
    ).all()

    # Employee-Objekte fuer Weiterleitung (mit employee_id)
    from sqlalchemy.orm import joinedload
    employees = Employee.query.options(
        joinedload(Employee.user)
    ).filter_by(
        organization_id=current_user.organization_id, is_active=True
    ).all()

    return render_template('tasks/index.html',
                           aufgaben=aufgaben,
                           tab=tab,
                           category_filter=category,
                           priority_filter=priority,
                           status_filter=status,
                           mitarbeiter=mitarbeiter,
                           employees=employees,
                           page=page,
                           total_pages=total_pages,
                           total=total,
                           today=date.today())


@tasks_bp.route('/create', methods=['POST'])
@login_required
def create():
    """Neue Aufgabe erstellen"""
    data = request.get_json() if request.is_json else None

    if data:
        # API-Aufruf
        aufgabe = Task(
            organization_id=current_user.organization_id,
            title=data.get('title', ''),
            description=data.get('description', ''),
            priority=data.get('priority', 'normal'),
            category=data.get('category', 'sonstiges'),
            assigned_to_id=data.get('assigned_to_id'),
            created_by_id=current_user.id,
            due_date=datetime.strptime(data['due_date'], '%Y-%m-%d').date() if data.get('due_date') else None,
            related_patient_id=data.get('patient_id'),
            related_series_id=data.get('series_id'),
            related_invoice_id=data.get('invoice_id'),
            task_color=int(data.get('task_color', 0)),
            task_force_response=bool(data.get('task_force_response', False)),
            status='open',
            task_type='manual'
        )
        db.session.add(aufgabe)
        db.session.flush()  # ID generieren

        # Multi-Empfaenger (Cenplex: MissiontoemployeesDto)
        recipient_ids = data.get('recipient_ids', [])
        if data.get('assigned_to_id'):
            emp = Employee.query.filter_by(user_id=data['assigned_to_id']).first()
            if emp and emp.id not in recipient_ids:
                recipient_ids.append(emp.id)

        for emp_id in recipient_ids:
            assignment = MissionToEmployee(
                task_id=aufgabe.id,
                employee_id=int(emp_id)
            )
            db.session.add(assignment)

        db.session.commit()
        return jsonify({'success': True, 'id': aufgabe.id, 'message': 'Aufgabe erstellt.'})
    else:
        # Form-Aufruf
        aufgabe = Task(
            organization_id=current_user.organization_id,
            title=request.form.get('title', ''),
            description=request.form.get('description', ''),
            priority=request.form.get('priority', 'normal'),
            category=request.form.get('category', 'sonstiges'),
            assigned_to_id=request.form.get('assigned_to_id', type=int) or current_user.id,
            created_by_id=current_user.id,
            due_date=datetime.strptime(request.form['due_date'], '%Y-%m-%d').date() if request.form.get('due_date') else None,
            related_patient_id=request.form.get('patient_id', type=int),
            task_color=request.form.get('task_color', 0, type=int),
            task_force_response=bool(request.form.get('task_force_response')),
            status='open',
            task_type='manual'
        )
        db.session.add(aufgabe)
        db.session.flush()
        # MissionToEmployee fuer Hauptempfaenger
        assigned_id = request.form.get('assigned_to_id', type=int)
        if assigned_id:
            emp = Employee.query.filter_by(user_id=assigned_id).first()
            if emp:
                assignment = MissionToEmployee(task_id=aufgabe.id, employee_id=emp.id)
                db.session.add(assignment)
        db.session.commit()
        flash('Aufgabe erfolgreich erstellt.', 'success')
        return redirect(url_for('tasks.index'))


@tasks_bp.route('/api/<int:id>/complete', methods=['POST'])
@login_required
def complete(id):
    """Aufgabe als erledigt markieren"""
    aufgabe = Task.query.get_or_404(id)
    check_org(aufgabe)
    aufgabe.status = 'completed'
    aufgabe.completed_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'success': True, 'message': 'Aufgabe erledigt.'})


@tasks_bp.route('/api/<int:id>/reopen', methods=['POST'])
@login_required
def reopen(id):
    """Aufgabe wieder oeffnen"""
    aufgabe = Task.query.get_or_404(id)
    check_org(aufgabe)
    aufgabe.status = 'open'
    aufgabe.completed_at = None
    db.session.commit()
    return jsonify({'success': True, 'message': 'Aufgabe wieder geöffnet.'})


@tasks_bp.route('/api/<int:id>/assign', methods=['POST'])
@login_required
def assign(id):
    """Aufgabe zuweisen"""
    aufgabe = Task.query.get_or_404(id)
    check_org(aufgabe)
    data = request.get_json()
    aufgabe.assigned_to_id = data.get('assigned_to_id')
    db.session.commit()

    assigned_name = ''
    if aufgabe.assigned_to:
        assigned_name = f'{aufgabe.assigned_to.first_name} {aufgabe.assigned_to.last_name}'
    return jsonify({'success': True, 'message': f'Aufgabe zugewiesen an {assigned_name}.'})


@tasks_bp.route('/api/<int:id>/priority', methods=['POST'])
@login_required
def change_priority(id):
    """Prioritaet aendern"""
    aufgabe = Task.query.get_or_404(id)
    check_org(aufgabe)
    data = request.get_json()
    aufgabe.priority = data.get('priority', 'normal')
    db.session.commit()
    return jsonify({'success': True, 'message': 'Priorität geändert.'})


@tasks_bp.route('/api/<int:id>/comment', methods=['POST'])
@login_required
def add_comment(id):
    """Kommentar hinzufuegen"""
    aufgabe = Task.query.get_or_404(id)
    check_org(aufgabe)
    data = request.get_json()
    comment_text = data.get('comment', '').strip()
    if not comment_text:
        return jsonify({'error': 'Kommentar darf nicht leer sein.'}), 400

    comment = TaskComment(
        task_id=aufgabe.id,
        user_id=current_user.id,
        comment=comment_text
    )
    db.session.add(comment)
    db.session.commit()
    return jsonify({
        'success': True,
        'comment': {
            'id': comment.id,
            'user': f'{current_user.first_name} {current_user.last_name}',
            'comment': comment.comment,
            'created_at': comment.created_at.strftime('%d.%m.%Y %H:%M')
        }
    })


@tasks_bp.route('/api/<int:id>/detail')
@login_required
def detail_api(id):
    """Aufgabe-Details als JSON"""
    aufgabe = Task.query.get_or_404(id)
    check_org(aufgabe)
    comments = [{
        'id': c.id,
        'user': f'{c.user.first_name} {c.user.last_name}' if c.user else 'System',
        'comment': c.comment,
        'created_at': c.created_at.strftime('%d.%m.%Y %H:%M')
    } for c in aufgabe.comments.all()]

    priority_map = {'critical': 'Kritisch', 'high': 'Hoch', 'normal': 'Mittel', 'low': 'Niedrig'}
    category_map = {
        'patientendaten': 'Patientendaten', 'versicherung': 'Versicherung',
        'arzt': 'Arzt', 'verordnung': 'Verordnung', 'abrechnung': 'Abrechnung',
        'gutsprache': 'Gutsprache', 'sonstiges': 'Sonstiges'
    }

    return jsonify({
        'id': aufgabe.id,
        'title': aufgabe.title,
        'description': aufgabe.description,
        'priority': aufgabe.priority,
        'priority_label': priority_map.get(aufgabe.priority, aufgabe.priority),
        'category': aufgabe.category,
        'category_label': category_map.get(aufgabe.category, aufgabe.category),
        'status': aufgabe.status,
        'due_date': aufgabe.due_date.strftime('%d.%m.%Y') if aufgabe.due_date else None,
        'assigned_to': f'{aufgabe.assigned_to.first_name} {aufgabe.assigned_to.last_name}' if aufgabe.assigned_to else None,
        'assigned_to_id': aufgabe.assigned_to_id,
        'created_by': f'{aufgabe.created_by.first_name} {aufgabe.created_by.last_name}' if aufgabe.created_by else None,
        'patient': f'{aufgabe.related_patient.first_name} {aufgabe.related_patient.last_name}' if aufgabe.related_patient else None,
        'patient_id': aufgabe.related_patient_id,
        'auto_generated': aufgabe.auto_generated,
        'created_at': aufgabe.created_at.strftime('%d.%m.%Y %H:%M'),
        'completed_at': aufgabe.completed_at.strftime('%d.%m.%Y %H:%M') if aufgabe.completed_at else None,
        'comments': comments
    })


@tasks_bp.route('/api/open-count')
@login_required
def open_count():
    """Anzahl offener Aufgaben fuer Badge"""
    count = Task.query.filter(
        Task.organization_id == current_user.organization_id,
        Task.status.in_(['open', 'in_progress'])
    ).count()
    return jsonify({'count': count})


@tasks_bp.route('/api/generate', methods=['POST'])
@login_required
def generate_tasks():
    """Automatische Aufgaben-Erkennung ausloesen"""
    from services.task_generator import TaskGenerator
    generator = TaskGenerator(current_user.organization_id)
    created, removed = generator.run()
    return jsonify({
        'success': True,
        'created': created,
        'removed': removed,
        'message': f'{created} Aufgaben erstellt, {removed} erledigte entfernt.'
    })


# ============================================================
# Phase 11: Erweiterte Aufgaben-Features (Cenplex-Angleichung)
# ============================================================

@tasks_bp.route('/api/<int:id>/edit', methods=['POST'])
@login_required
def edit(id):
    """Aufgabe bearbeiten (Cenplex: UpdateMission)"""
    aufgabe = Task.query.get_or_404(id)
    check_org(aufgabe)
    data = request.get_json()

    if 'title' in data:
        aufgabe.title = data['title']
    if 'description' in data:
        aufgabe.description = data['description']
    if 'priority' in data:
        aufgabe.priority = data['priority']
    if 'category' in data:
        aufgabe.category = data['category']
    if 'due_date' in data:
        aufgabe.due_date = datetime.strptime(data['due_date'], '%Y-%m-%d').date() if data['due_date'] else None
    if 'task_color' in data:
        aufgabe.task_color = int(data['task_color'])
    if 'task_force_response' in data:
        aufgabe.task_force_response = bool(data['task_force_response'])

    db.session.commit()
    return jsonify({'success': True, 'message': 'Aufgabe aktualisiert.'})


@tasks_bp.route('/api/<int:id>/read', methods=['POST'])
@login_required
def mark_read(id):
    """Aufgabe als gelesen markieren (Cenplex: MissionRead)"""
    aufgabe = Task.query.get_or_404(id)
    check_org(aufgabe)

    employee = Employee.query.filter_by(user_id=current_user.id).first()
    if employee:
        assignment = MissionToEmployee.query.filter_by(
            task_id=aufgabe.id, employee_id=employee.id
        ).first()
        if assignment and not assignment.read_date:
            assignment.read_date = datetime.now(timezone.utc)
            assignment.has_updates = False
            db.session.commit()

    # Status aktualisieren wenn noch 'open'
    if aufgabe.status == 'open':
        aufgabe.has_updates = False
        db.session.commit()

    return jsonify({'success': True})


@tasks_bp.route('/api/<int:id>/start', methods=['POST'])
@login_required
def start(id):
    """Aufgabe starten (Cenplex: MissionStarted)"""
    aufgabe = Task.query.get_or_404(id)
    check_org(aufgabe)

    if aufgabe.status == 'open':
        aufgabe.status = 'in_progress'

    employee = Employee.query.filter_by(user_id=current_user.id).first()
    if employee:
        assignment = MissionToEmployee.query.filter_by(
            task_id=aufgabe.id, employee_id=employee.id
        ).first()
        if assignment and not assignment.started:
            assignment.started = datetime.now(timezone.utc)

    db.session.commit()
    return jsonify({'success': True, 'message': 'Aufgabe gestartet.'})


@tasks_bp.route('/api/<int:id>/respond', methods=['POST'])
@login_required
def respond(id):
    """Auf Aufgabe antworten (Cenplex: RespondToMission)"""
    aufgabe = Task.query.get_or_404(id)
    check_org(aufgabe)

    data = request.get_json()
    message = data.get('message', '').strip()
    if not message:
        return jsonify({'error': 'Nachricht darf nicht leer sein.'}), 400

    employee = Employee.query.filter_by(user_id=current_user.id).first()
    if not employee:
        return jsonify({'error': 'Kein Mitarbeiter-Profil'}), 400

    # Empfaenger: Ersteller der Aufgabe
    receiver_id = data.get('receiver_id')
    if not receiver_id and aufgabe.created_by:
        creator_emp = Employee.query.filter_by(user_id=aufgabe.created_by_id).first()
        receiver_id = creator_emp.id if creator_emp else employee.id

    response = MissionResponse(
        task_id=aufgabe.id,
        sender_id=employee.id,
        receiver_id=receiver_id or employee.id,
        response=message
    )
    aufgabe.has_updates = True
    db.session.add(response)
    db.session.commit()

    return jsonify({
        'success': True,
        'response': {
            'id': response.id,
            'sender': f'{employee.user.first_name} {employee.user.last_name}' if employee.user else 'System',
            'message': response.response,
            'created_at': response.created_at.strftime('%d.%m.%Y %H:%M')
        }
    })


@tasks_bp.route('/api/<int:id>/forward', methods=['POST'])
@login_required
def forward(id):
    """Aufgabe weiterleiten (Cenplex: ForwardMission)"""
    aufgabe = Task.query.get_or_404(id)
    check_org(aufgabe)

    data = request.get_json()
    employee_id = data.get('employee_id')
    message = data.get('message', '')

    if not employee_id:
        return jsonify({'error': 'Empfänger fehlt'}), 400

    # Neuen Empfaenger hinzufuegen
    existing = MissionToEmployee.query.filter_by(
        task_id=aufgabe.id, employee_id=int(employee_id)
    ).first()
    if not existing:
        assignment = MissionToEmployee(
            task_id=aufgabe.id,
            employee_id=int(employee_id),
            notes=message
        )
        db.session.add(assignment)

    # Auch als assigned_to setzen wenn noch kein Empfaenger
    target_emp = Employee.query.get(int(employee_id))
    if target_emp and target_emp.user_id:
        aufgabe.assigned_to_id = target_emp.user_id

    aufgabe.has_updates = True
    db.session.commit()

    emp_name = ''
    if target_emp and target_emp.user:
        emp_name = f'{target_emp.user.first_name} {target_emp.user.last_name}'

    return jsonify({'success': True, 'message': f'Aufgabe weitergeleitet an {emp_name}.'})


@tasks_bp.route('/api/<int:id>/full-detail')
@login_required
def full_detail(id):
    """Erweiterte Aufgabe-Details mit Antworten, Zuweisungen, Historie"""
    aufgabe = Task.query.get_or_404(id)
    check_org(aufgabe)

    # Kommentare
    comments = [{
        'id': c.id,
        'user': f'{c.user.first_name} {c.user.last_name}' if c.user else 'System',
        'comment': c.comment,
        'created_at': c.created_at.strftime('%d.%m.%Y %H:%M')
    } for c in aufgabe.comments.all()]

    # Antworten (MissionResponses)
    responses = []
    for r in aufgabe.mission_responses.order_by(MissionResponse.created_at.desc()).all():
        sender_name = ''
        if r.sender and r.sender.user:
            sender_name = f'{r.sender.user.first_name} {r.sender.user.last_name}'
        responses.append({
            'id': r.id,
            'sender': sender_name,
            'message': r.response,
            'read_date': r.read_date.strftime('%d.%m.%Y %H:%M') if r.read_date else None,
            'created_at': r.created_at.strftime('%d.%m.%Y %H:%M')
        })

    # Zuweisungen (MissionToEmployee)
    assignments = []
    for a in aufgabe.mission_assignments.all():
        emp_name = ''
        if a.employee and a.employee.user:
            emp_name = f'{a.employee.user.first_name} {a.employee.user.last_name}'
        assignments.append({
            'id': a.id,
            'employee': emp_name,
            'employee_id': a.employee_id,
            'read_date': a.read_date.strftime('%d.%m.%Y %H:%M') if a.read_date else None,
            'started': a.started.strftime('%d.%m.%Y %H:%M') if a.started else None,
            'finished': a.finished.strftime('%d.%m.%Y %H:%M') if a.finished else None,
            'notes': a.notes
        })

    # Mission-Notizen
    mission_notes = []
    for n in aufgabe.mission_notes.order_by(MissionNote.created_at.desc()).all():
        emp_name = ''
        if n.employee and n.employee.user:
            emp_name = f'{n.employee.user.first_name} {n.employee.user.last_name}'
        mission_notes.append({
            'id': n.id,
            'employee': emp_name,
            'notes': n.notes,
            'created_at': n.created_at.strftime('%d.%m.%Y %H:%M')
        })

    # Links parsen (task_links_json)
    import json
    links = {}
    if aufgabe.task_links_json:
        try:
            links = json.loads(aufgabe.task_links_json)
        except (json.JSONDecodeError, TypeError):
            pass

    priority_map = {'critical': 'Kritisch', 'high': 'Hoch', 'normal': 'Mittel', 'low': 'Niedrig'}
    category_map = {
        'patientendaten': 'Patientendaten', 'versicherung': 'Versicherung',
        'arzt': 'Arzt', 'verordnung': 'Verordnung', 'abrechnung': 'Abrechnung',
        'gutsprache': 'Gutsprache', 'sonstiges': 'Sonstiges'
    }
    color_names = ['Standard', 'Gelb', 'Grün', 'Blau', 'Rot', 'Lila', 'Rosa']

    return jsonify({
        'id': aufgabe.id,
        'title': aufgabe.title,
        'description': aufgabe.description,
        'priority': aufgabe.priority,
        'priority_label': priority_map.get(aufgabe.priority, aufgabe.priority),
        'category': aufgabe.category,
        'category_label': category_map.get(aufgabe.category, aufgabe.category),
        'status': aufgabe.status,
        'task_type': aufgabe.task_type,
        'due_date': aufgabe.due_date.strftime('%d.%m.%Y') if aufgabe.due_date else None,
        'due_date_iso': aufgabe.due_date.isoformat() if aufgabe.due_date else None,
        'assigned_to': f'{aufgabe.assigned_to.first_name} {aufgabe.assigned_to.last_name}' if aufgabe.assigned_to else None,
        'assigned_to_id': aufgabe.assigned_to_id,
        'created_by': f'{aufgabe.created_by.first_name} {aufgabe.created_by.last_name}' if aufgabe.created_by else None,
        'patient': f'{aufgabe.related_patient.first_name} {aufgabe.related_patient.last_name}' if aufgabe.related_patient else None,
        'patient_id': aufgabe.related_patient_id,
        'auto_generated': aufgabe.auto_generated,
        'task_color': aufgabe.task_color or 0,
        'task_color_name': color_names[aufgabe.task_color] if aufgabe.task_color and aufgabe.task_color < len(color_names) else 'Standard',
        'task_force_response': aufgabe.task_force_response,
        'has_updates': aufgabe.has_updates,
        'links': links,
        'created_at': aufgabe.created_at.strftime('%d.%m.%Y %H:%M'),
        'completed_at': aufgabe.completed_at.strftime('%d.%m.%Y %H:%M') if aufgabe.completed_at else None,
        'comments': comments,
        'responses': responses,
        'assignments': assignments,
        'mission_notes': mission_notes
    })


@tasks_bp.route('/api/<int:id>/add-recipients', methods=['POST'])
@login_required
def add_recipients(id):
    """Empfaenger zur Aufgabe hinzufuegen (Cenplex: Multi-Empfaenger)"""
    aufgabe = Task.query.get_or_404(id)
    check_org(aufgabe)

    data = request.get_json()
    employee_ids = data.get('employee_ids', [])
    added = 0

    for emp_id in employee_ids:
        existing = MissionToEmployee.query.filter_by(
            task_id=aufgabe.id, employee_id=int(emp_id)
        ).first()
        if not existing:
            assignment = MissionToEmployee(
                task_id=aufgabe.id,
                employee_id=int(emp_id)
            )
            db.session.add(assignment)
            added += 1

    db.session.commit()
    return jsonify({'success': True, 'added': added})
