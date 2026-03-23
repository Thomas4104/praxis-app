"""KI-Tools fuer den Aufgaben-Bereich"""
import json
from datetime import datetime, date
from flask_login import current_user
from models import db, Task, TaskComment, Patient, User, Employee


TASK_TOOLS = [
    {
        'name': 'aufgaben_auflisten',
        'description': 'Listet Aufgaben auf, optional gefiltert nach Status, Prioritaet oder Zuweisung.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'status': {'type': 'string', 'description': 'Statusfilter: open, completed'},
                'prioritaet': {'type': 'string', 'description': 'Prioritaetsfilter: critical, high, normal, low'},
                'zugewiesen_an': {'type': 'integer', 'description': 'User-ID des zugewiesenen Mitarbeiters'}
            },
            'required': []
        }
    },
    {
        'name': 'aufgabe_erstellen',
        'description': 'Erstellt eine neue manuelle Aufgabe.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'titel': {'type': 'string', 'description': 'Titel der Aufgabe'},
                'beschreibung': {'type': 'string', 'description': 'Detailbeschreibung'},
                'prioritaet': {'type': 'string', 'description': 'Prioritaet: critical, high, normal, low'},
                'kategorie': {'type': 'string', 'description': 'Kategorie: patientendaten, versicherung, arzt, verordnung, abrechnung, gutsprache, sonstiges'},
                'zugewiesen_an': {'type': 'integer', 'description': 'User-ID'},
                'faellig_am': {'type': 'string', 'description': 'Faelligkeitsdatum (YYYY-MM-DD)'},
                'patient_id': {'type': 'integer', 'description': 'Verknuepfter Patient (optional)'}
            },
            'required': ['titel']
        }
    },
    {
        'name': 'aufgabe_erledigen',
        'description': 'Markiert eine Aufgabe als erledigt.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'aufgabe_id': {'type': 'integer', 'description': 'ID der Aufgabe'}
            },
            'required': ['aufgabe_id']
        }
    },
    {
        'name': 'aufgabe_zuweisen',
        'description': 'Weist eine Aufgabe einem Mitarbeiter zu.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'aufgabe_id': {'type': 'integer', 'description': 'ID der Aufgabe'},
                'mitarbeiter_id': {'type': 'integer', 'description': 'User-ID des Mitarbeiters'}
            },
            'required': ['aufgabe_id', 'mitarbeiter_id']
        }
    },
    {
        'name': 'offene_aufgaben_anzahl',
        'description': 'Gibt die Anzahl offener Aufgaben zurueck.',
        'input_schema': {
            'type': 'object',
            'properties': {},
            'required': []
        }
    },
    {
        'name': 'meine_aufgaben',
        'description': 'Listet die Aufgaben des aktuellen Benutzers auf.',
        'input_schema': {
            'type': 'object',
            'properties': {},
            'required': []
        }
    },
    {
        'name': 'fehlende_daten_pruefen',
        'description': 'Prueft auf fehlende Daten bei Patienten und Serien und erstellt automatische Aufgaben.',
        'input_schema': {
            'type': 'object',
            'properties': {},
            'required': []
        }
    }
]


def _format_task(aufgabe):
    """Formatiert eine Aufgabe fuer die KI-Ausgabe"""
    priority_map = {'critical': 'Kritisch', 'high': 'Hoch', 'normal': 'Mittel', 'low': 'Niedrig'}
    category_map = {
        'patientendaten': 'Patientendaten', 'versicherung': 'Versicherung',
        'arzt': 'Arzt', 'verordnung': 'Verordnung', 'abrechnung': 'Abrechnung',
        'gutsprache': 'Gutsprache', 'sonstiges': 'Sonstiges'
    }
    return {
        'id': aufgabe.id,
        'titel': aufgabe.title,
        'beschreibung': aufgabe.description,
        'prioritaet': priority_map.get(aufgabe.priority, aufgabe.priority),
        'kategorie': category_map.get(aufgabe.category, aufgabe.category),
        'status': 'Offen' if aufgabe.status == 'open' else 'Erledigt',
        'faellig': aufgabe.due_date.strftime('%d.%m.%Y') if aufgabe.due_date else None,
        'zugewiesen_an': f'{aufgabe.assigned_to.first_name} {aufgabe.assigned_to.last_name}' if aufgabe.assigned_to else None,
        'patient': f'{aufgabe.related_patient.first_name} {aufgabe.related_patient.last_name}' if aufgabe.related_patient else None,
        'automatisch': aufgabe.auto_generated,
        'erstellt_am': aufgabe.created_at.strftime('%d.%m.%Y')
    }


def task_tool_executor(tool_name, tool_input):
    """Fuehrt Aufgaben-Tools aus"""
    org_id = current_user.organization_id

    if tool_name == 'aufgaben_auflisten':
        status = tool_input.get('status')
        prioritaet = tool_input.get('prioritaet')
        zugewiesen_an = tool_input.get('zugewiesen_an')

        query = Task.query.filter_by(organization_id=org_id)
        if status:
            query = query.filter_by(status=status)
        else:
            query = query.filter(Task.status != 'completed')
        if prioritaet:
            query = query.filter_by(priority=prioritaet)
        if zugewiesen_an:
            query = query.filter_by(assigned_to_id=zugewiesen_an)

        aufgaben = query.order_by(Task.created_at.desc()).limit(50).all()
        return {
            'aufgaben': [_format_task(a) for a in aufgaben],
            'anzahl': len(aufgaben)
        }

    elif tool_name == 'aufgabe_erstellen':
        titel = tool_input.get('titel', '')
        if not titel:
            return {'error': 'Titel ist Pflichtfeld.'}

        faellig_am = None
        if tool_input.get('faellig_am'):
            try:
                faellig_am = datetime.strptime(tool_input['faellig_am'], '%Y-%m-%d').date()
            except ValueError:
                pass

        aufgabe = Task(
            organization_id=org_id,
            title=titel,
            description=tool_input.get('beschreibung', ''),
            priority=tool_input.get('prioritaet', 'normal'),
            category=tool_input.get('kategorie', 'sonstiges'),
            assigned_to_id=tool_input.get('zugewiesen_an'),
            created_by_id=None,
            due_date=faellig_am,
            related_patient_id=tool_input.get('patient_id'),
            status='open',
            task_type='manual'
        )
        db.session.add(aufgabe)
        db.session.commit()

        return {
            'success': True,
            'aufgabe_id': aufgabe.id,
            'message': f'Aufgabe "{titel}" wurde erstellt.'
        }

    elif tool_name == 'aufgabe_erledigen':
        aufgabe_id = tool_input.get('aufgabe_id')
        aufgabe = Task.query.get(aufgabe_id)
        if not aufgabe or aufgabe.organization_id != org_id:
            return {'error': f'Aufgabe {aufgabe_id} nicht gefunden.'}

        aufgabe.status = 'completed'
        aufgabe.completed_at = datetime.utcnow()
        db.session.commit()
        return {'success': True, 'message': f'Aufgabe "{aufgabe.title}" wurde als erledigt markiert.'}

    elif tool_name == 'aufgabe_zuweisen':
        aufgabe_id = tool_input.get('aufgabe_id')
        mitarbeiter_id = tool_input.get('mitarbeiter_id')
        aufgabe = Task.query.get(aufgabe_id)
        if not aufgabe or aufgabe.organization_id != org_id:
            return {'error': f'Aufgabe {aufgabe_id} nicht gefunden.'}

        aufgabe.assigned_to_id = mitarbeiter_id
        db.session.commit()

        user = User.query.get(mitarbeiter_id)
        name = f'{user.first_name} {user.last_name}' if user else 'Unbekannt'
        return {'success': True, 'message': f'Aufgabe wurde {name} zugewiesen.'}

    elif tool_name == 'offene_aufgaben_anzahl':
        count = Task.query.filter(
            Task.organization_id == org_id,
            Task.status.in_(['open', 'in_progress'])
        ).count()
        return {'anzahl': count}

    elif tool_name == 'meine_aufgaben':
        try:
            user_id = current_user.id
        except Exception:
            return {'error': 'Kein Benutzer angemeldet.'}

        aufgaben = Task.query.filter(
            Task.organization_id == org_id,
            db.or_(Task.assigned_to_id == user_id, Task.created_by_id == user_id),
            Task.status != 'completed'
        ).order_by(Task.created_at.desc()).all()

        return {
            'aufgaben': [_format_task(a) for a in aufgaben],
            'anzahl': len(aufgaben)
        }

    elif tool_name == 'fehlende_daten_pruefen':
        from services.task_generator import TaskGenerator
        try:
            generator = TaskGenerator(org_id)
            created, removed = generator.run()
            return {
                'success': True,
                'erstellt': created,
                'entfernt': removed,
                'message': f'{created} neue Aufgaben erstellt, {removed} erledigte entfernt.'
            }
        except Exception as e:
            return {'error': f'Fehler bei der Pruefung: {str(e)}'}

    return {'error': f'Unbekanntes Tool: {tool_name}'}
