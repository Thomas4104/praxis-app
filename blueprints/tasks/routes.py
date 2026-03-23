"""Routen fuer Aufgaben-Verwaltung"""
from datetime import datetime, date
from flask import render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from blueprints.tasks import tasks_bp
from models import db, Task, TaskComment, Patient, User, Employee
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

    # Mitarbeiter fuer Zuweisung
    mitarbeiter = User.query.filter_by(
        organization_id=current_user.organization_id, is_active=True
    ).all()

    return render_template('tasks/index.html',
                           aufgaben=aufgaben,
                           tab=tab,
                           category_filter=category,
                           priority_filter=priority,
                           status_filter=status,
                           mitarbeiter=mitarbeiter,
                           page=page,
                           total_pages=total_pages,
                           total=total)


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
            status='open',
            task_type='manual'
        )
        db.session.add(aufgabe)
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
            status='open',
            task_type='manual'
        )
        db.session.add(aufgabe)
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
