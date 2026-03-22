# Mitarbeiter-Agent: Spezialist für Mitarbeiterdaten, Arbeitszeiten, Abwesenheiten

from datetime import datetime, date, time
from models import db, Employee, User, WorkSchedule, Absence, Appointment
from ai.base_agent import BaseAgent

SYSTEM_PROMPT = """Du bist der Mitarbeiter-Spezialist der OMNIA Praxissoftware. Du verwaltest alles rund um Personal: Mitarbeiterdaten, Arbeitszeiten und Abwesenheiten.

Regeln:
- Antworte immer auf Deutsch, kurz und professionell
- Nenne bei Mitarbeitern immer den vollständigen Namen
- Arbeitszeiten klar nach Wochentagen geordnet anzeigen
- Bei Abwesenheiten: Zeitraum und Art nennen"""

TOOLS = [
    {
        "name": "mitarbeiter_auflisten",
        "description": "Listet alle aktiven Mitarbeiter auf.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "mitarbeiter_details",
        "description": "Zeigt alle Details eines Mitarbeiters an.",
        "input_schema": {
            "type": "object",
            "properties": {
                "mitarbeiter_id": {"type": "integer", "description": "ID des Mitarbeiters"},
            },
            "required": ["mitarbeiter_id"]
        }
    },
    {
        "name": "arbeitszeiten_anzeigen",
        "description": "Zeigt die Arbeitszeiten eines Mitarbeiters an.",
        "input_schema": {
            "type": "object",
            "properties": {
                "mitarbeiter_id": {"type": "integer", "description": "ID des Mitarbeiters"},
            },
            "required": ["mitarbeiter_id"]
        }
    },
    {
        "name": "abwesenheit_erstellen",
        "description": "Erstellt eine neue Abwesenheit für einen Mitarbeiter.",
        "input_schema": {
            "type": "object",
            "properties": {
                "mitarbeiter_id": {"type": "integer", "description": "ID des Mitarbeiters"},
                "typ": {"type": "string", "description": "Art: vacation/illness/training"},
                "von": {"type": "string", "description": "Startdatum YYYY-MM-DD"},
                "bis": {"type": "string", "description": "Enddatum YYYY-MM-DD"},
                "notizen": {"type": "string", "description": "Optional: Bemerkungen"},
            },
            "required": ["mitarbeiter_id", "typ", "von", "bis"]
        }
    },
    {
        "name": "abwesenheiten_anzeigen",
        "description": "Zeigt Abwesenheiten eines Mitarbeiters oder aller Mitarbeiter.",
        "input_schema": {
            "type": "object",
            "properties": {
                "mitarbeiter_id": {"type": "integer", "description": "Optional: ID des Mitarbeiters (sonst alle)"},
            },
            "required": []
        }
    },
    {
        "name": "mitarbeiter_suchen",
        "description": "Sucht Mitarbeiter nach Name.",
        "input_schema": {
            "type": "object",
            "properties": {
                "suchbegriff": {"type": "string", "description": "Name oder Teil des Namens"},
            },
            "required": ["suchbegriff"]
        }
    },
]

ABSENCE_TYPES = {
    'vacation': 'Ferien',
    'illness': 'Krankheit',
    'training': 'Weiterbildung',
}


def execute_tool(tool_name, tool_input):
    """Führt ein Mitarbeiter-Tool aus."""

    if tool_name == 'mitarbeiter_auflisten':
        mitarbeiter = Employee.query.filter_by(is_active=True).all()
        result = []
        for m in mitarbeiter:
            result.append({
                'id': m.id,
                'name': m.display_name,
                'rolle': m.user.role if m.user else '',
                'pensum': f'{m.pensum_percent}%',
                'farbe': m.color_code,
                'qualifikationen': m.qualifications or [],
            })
        return {'message': f'{len(result)} Mitarbeiter', 'mitarbeiter': result}

    elif tool_name == 'mitarbeiter_details':
        emp = Employee.query.get(tool_input['mitarbeiter_id'])
        if not emp:
            return {'error': 'Mitarbeiter nicht gefunden'}

        # Arbeitszeiten
        schedules = WorkSchedule.query.filter_by(employee_id=emp.id).order_by(WorkSchedule.day_of_week).all()
        arbeitszeiten = [{
            'tag': s.day_name,
            'von': s.start_time.strftime('%H:%M'),
            'bis': s.end_time.strftime('%H:%M'),
            'typ': s.work_type,
        } for s in schedules]

        # Kommende Termine (nächste 7 Tage)
        from datetime import timedelta
        naechste_termine = Appointment.query.filter(
            Appointment.employee_id == emp.id,
            Appointment.start_time >= datetime.now(),
            Appointment.start_time <= datetime.now() + timedelta(days=7),
            Appointment.status != 'cancelled'
        ).count()

        return {
            'mitarbeiter': {
                'id': emp.id,
                'name': emp.display_name,
                'email': emp.user.email if emp.user else '',
                'rolle': emp.user.role if emp.user else '',
                'pensum': f'{emp.pensum_percent}%',
                'anstellungsmodell': emp.employment_model,
                'zsr_nummer': emp.zsr_number or '',
                'gln_nummer': emp.gln_number or '',
                'farbe': emp.color_code,
                'qualifikationen': emp.qualifications or [],
            },
            'arbeitszeiten': arbeitszeiten,
            'termine_naechste_7_tage': naechste_termine,
        }

    elif tool_name == 'arbeitszeiten_anzeigen':
        emp = Employee.query.get(tool_input['mitarbeiter_id'])
        if not emp:
            return {'error': 'Mitarbeiter nicht gefunden'}

        schedules = WorkSchedule.query.filter_by(employee_id=emp.id).order_by(
            WorkSchedule.day_of_week, WorkSchedule.start_time
        ).all()

        tage = {}
        for s in schedules:
            tag = s.day_name
            if tag not in tage:
                tage[tag] = []
            tage[tag].append({
                'von': s.start_time.strftime('%H:%M'),
                'bis': s.end_time.strftime('%H:%M'),
                'typ': s.work_type,
                'standort': s.location_id,
            })

        return {
            'mitarbeiter': emp.display_name,
            'arbeitszeiten': tage,
        }

    elif tool_name == 'abwesenheit_erstellen':
        emp = Employee.query.get(tool_input['mitarbeiter_id'])
        if not emp:
            return {'error': 'Mitarbeiter nicht gefunden'}

        von = datetime.strptime(tool_input['von'], '%Y-%m-%d').date()
        bis = datetime.strptime(tool_input['bis'], '%Y-%m-%d').date()

        absence = Absence(
            employee_id=emp.id,
            type=tool_input['typ'],
            start_date=von,
            end_date=bis,
            status='requested',
            notes=tool_input.get('notizen', ''),
        )
        db.session.add(absence)
        db.session.commit()

        typ_name = ABSENCE_TYPES.get(tool_input['typ'], tool_input['typ'])
        return {
            'message': f'{typ_name} für {emp.display_name} erfasst: {von.strftime("%d.%m.%Y")} bis {bis.strftime("%d.%m.%Y")}',
            'abwesenheit_id': absence.id,
        }

    elif tool_name == 'abwesenheiten_anzeigen':
        query = Absence.query
        if tool_input.get('mitarbeiter_id'):
            query = query.filter_by(employee_id=tool_input['mitarbeiter_id'])

        absences = query.filter(Absence.end_date >= date.today()).order_by(Absence.start_date).all()

        result = []
        for a in absences:
            result.append({
                'id': a.id,
                'mitarbeiter': a.employee.display_name,
                'typ': ABSENCE_TYPES.get(a.type, a.type),
                'von': a.start_date.strftime('%d.%m.%Y'),
                'bis': a.end_date.strftime('%d.%m.%Y'),
                'status': a.status,
            })

        return {'message': f'{len(result)} Abwesenheiten', 'abwesenheiten': result}

    elif tool_name == 'mitarbeiter_suchen':
        search = f'%{tool_input["suchbegriff"]}%'
        users = User.query.filter(User.name.ilike(search)).all()
        result = []
        for u in users:
            if u.employee:
                result.append({
                    'id': u.employee.id,
                    'name': u.name,
                    'rolle': u.role,
                })
        return {'message': f'{len(result)} Mitarbeiter gefunden', 'mitarbeiter': result}

    return {'error': f'Unbekanntes Tool: {tool_name}'}


def create_mitarbeiter_agent():
    """Erstellt eine Instanz des Mitarbeiter-Agenten."""
    return BaseAgent(
        name='mitarbeiter_agent',
        system_prompt=SYSTEM_PROMPT,
        tools=TOOLS,
        tool_executor=execute_tool,
    )
