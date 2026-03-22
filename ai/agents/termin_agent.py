# Termin-Agent: Spezialist für Kalender, Termine, Planung, Verfügbarkeit

from datetime import datetime, date, time, timedelta
from models import db, Appointment, Employee, Patient, WorkSchedule, Resource, Location
from ai.base_agent import BaseAgent

SYSTEM_PROMPT = """Du bist der Termin-Spezialist der OMNIA Praxissoftware. Du bist Experte für Kalender, Terminplanung und Verfügbarkeit.

Du kennst die Arbeitszeiten aller Therapeuten, die Praxis-Öffnungszeiten und die Ressourcen (Räume, Geräte).

Bei der Terminsuche berücksichtigst du immer:
- Öffnungszeiten der Praxis
- Arbeitszeiten des Therapeuten
- Bestehende Termine (keine Überschneidungen)
- Ressourcen-Verfügbarkeit
- Patienten-Präferenzen (wenn bekannt)

Regeln:
- Antworte immer auf Deutsch, kurz und professionell
- Nenne bei Terminen immer Datum, Uhrzeit und Therapeut
- Bei Terminverschiebungen: alten und neuen Termin nennen
- Zeitformat: HH:MM (24h), Datum: DD.MM.YYYY"""

TOOLS = [
    {
        "name": "termine_anzeigen",
        "description": "Zeigt Termine für einen bestimmten Tag und optional einen bestimmten Therapeuten.",
        "input_schema": {
            "type": "object",
            "properties": {
                "datum": {"type": "string", "description": "Datum im Format YYYY-MM-DD"},
                "therapeut_id": {"type": "integer", "description": "Optional: ID des Therapeuten"},
            },
            "required": ["datum"]
        }
    },
    {
        "name": "termin_erstellen",
        "description": "Erstellt einen neuen Termin für einen Patienten bei einem Therapeuten.",
        "input_schema": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "integer", "description": "ID des Patienten"},
                "therapeut_id": {"type": "integer", "description": "ID des Therapeuten"},
                "datum": {"type": "string", "description": "Datum im Format YYYY-MM-DD"},
                "uhrzeit": {"type": "string", "description": "Startzeit im Format HH:MM"},
                "dauer_minuten": {"type": "integer", "description": "Dauer in Minuten (Standard: 30)"},
                "notizen": {"type": "string", "description": "Optional: Notizen zum Termin"},
            },
            "required": ["patient_id", "therapeut_id", "datum", "uhrzeit"]
        }
    },
    {
        "name": "termin_verschieben",
        "description": "Verschiebt einen bestehenden Termin auf ein neues Datum/Uhrzeit.",
        "input_schema": {
            "type": "object",
            "properties": {
                "termin_id": {"type": "integer", "description": "ID des zu verschiebenden Termins"},
                "neues_datum": {"type": "string", "description": "Neues Datum im Format YYYY-MM-DD"},
                "neue_uhrzeit": {"type": "string", "description": "Neue Startzeit im Format HH:MM"},
            },
            "required": ["termin_id", "neues_datum", "neue_uhrzeit"]
        }
    },
    {
        "name": "termin_absagen",
        "description": "Sagt einen Termin ab.",
        "input_schema": {
            "type": "object",
            "properties": {
                "termin_id": {"type": "integer", "description": "ID des Termins"},
                "grund": {"type": "string", "description": "Grund der Absage"},
            },
            "required": ["termin_id"]
        }
    },
    {
        "name": "naechster_freier_termin",
        "description": "Findet den nächsten freien Terminslot bei einem Therapeuten.",
        "input_schema": {
            "type": "object",
            "properties": {
                "therapeut_id": {"type": "integer", "description": "Optional: ID des Therapeuten (sonst alle)"},
                "dauer_minuten": {"type": "integer", "description": "Gewünschte Dauer (Standard: 30)"},
                "ab_datum": {"type": "string", "description": "Ab welchem Datum suchen (Standard: heute)"},
            },
            "required": []
        }
    },
    {
        "name": "patient_termine_auflisten",
        "description": "Zeigt alle Termine eines Patienten (vergangene und zukünftige).",
        "input_schema": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "integer", "description": "ID des Patienten"},
                "nur_zukuenftige": {"type": "boolean", "description": "Nur zukünftige Termine zeigen (Standard: true)"},
            },
            "required": ["patient_id"]
        }
    },
    {
        "name": "tagesplan_anzeigen",
        "description": "Zeigt den kompletten Tagesplan mit allen Therapeuten und ihren Terminen.",
        "input_schema": {
            "type": "object",
            "properties": {
                "datum": {"type": "string", "description": "Datum im Format YYYY-MM-DD (Standard: heute)"},
            },
            "required": []
        }
    },
]


def execute_tool(tool_name, tool_input):
    """Führt ein Termin-Tool aus."""

    if tool_name == 'termine_anzeigen':
        datum = datetime.strptime(tool_input['datum'], '%Y-%m-%d').date()
        start = datetime.combine(datum, time.min)
        end = datetime.combine(datum, time.max)

        query = Appointment.query.filter(
            Appointment.start_time >= start,
            Appointment.start_time <= end,
            Appointment.status != 'cancelled'
        )
        if tool_input.get('therapeut_id'):
            query = query.filter_by(employee_id=tool_input['therapeut_id'])

        termine = query.order_by(Appointment.start_time).all()

        if not termine:
            return {'message': f'Keine Termine am {datum.strftime("%d.%m.%Y")}', 'termine': []}

        result = []
        for t in termine:
            result.append({
                'id': t.id,
                'patient': t.patient.full_name,
                'therapeut': t.employee.display_name,
                'start': t.start_time.strftime('%H:%M'),
                'ende': t.end_time.strftime('%H:%M'),
                'status': t.status,
                'notizen': t.notes or '',
            })
        return {'message': f'{len(result)} Termine am {datum.strftime("%d.%m.%Y")}', 'termine': result}

    elif tool_name == 'termin_erstellen':
        patient = Patient.query.get(tool_input['patient_id'])
        if not patient:
            return {'error': 'Patient nicht gefunden'}

        employee = Employee.query.get(tool_input['therapeut_id'])
        if not employee:
            return {'error': 'Therapeut nicht gefunden'}

        datum = datetime.strptime(tool_input['datum'], '%Y-%m-%d').date()
        uhrzeit = datetime.strptime(tool_input['uhrzeit'], '%H:%M').time()
        dauer = tool_input.get('dauer_minuten', 30)

        start_dt = datetime.combine(datum, uhrzeit)
        end_dt = start_dt + timedelta(minutes=dauer)

        # Überschneidungen prüfen
        overlap = Appointment.query.filter(
            Appointment.employee_id == employee.id,
            Appointment.status != 'cancelled',
            Appointment.start_time < end_dt,
            Appointment.end_time > start_dt
        ).first()

        if overlap:
            return {'error': f'Terminkonflikt: {overlap.patient.full_name} hat bereits einen Termin von {overlap.start_time.strftime("%H:%M")} bis {overlap.end_time.strftime("%H:%M")}'}

        # Standort ermitteln
        location_id = None
        schedule = WorkSchedule.query.filter_by(
            employee_id=employee.id,
            day_of_week=datum.weekday()
        ).first()
        if schedule:
            location_id = schedule.location_id

        termin = Appointment(
            patient_id=patient.id,
            employee_id=employee.id,
            location_id=location_id,
            start_time=start_dt,
            end_time=end_dt,
            status='scheduled',
            type='treatment',
            notes=tool_input.get('notizen', ''),
        )
        db.session.add(termin)
        db.session.commit()

        return {
            'message': f'Termin erstellt: {patient.full_name} bei {employee.display_name} am {datum.strftime("%d.%m.%Y")} um {uhrzeit.strftime("%H:%M")} ({dauer} Min.)',
            'termin_id': termin.id,
        }

    elif tool_name == 'termin_verschieben':
        termin = Appointment.query.get(tool_input['termin_id'])
        if not termin:
            return {'error': 'Termin nicht gefunden'}

        altes_datum = termin.start_time.strftime('%d.%m.%Y %H:%M')
        neues_datum = datetime.strptime(tool_input['neues_datum'], '%Y-%m-%d').date()
        neue_uhrzeit = datetime.strptime(tool_input['neue_uhrzeit'], '%H:%M').time()
        dauer = (termin.end_time - termin.start_time).total_seconds() / 60

        new_start = datetime.combine(neues_datum, neue_uhrzeit)
        new_end = new_start + timedelta(minutes=dauer)

        # Überschneidungen prüfen
        overlap = Appointment.query.filter(
            Appointment.employee_id == termin.employee_id,
            Appointment.id != termin.id,
            Appointment.status != 'cancelled',
            Appointment.start_time < new_end,
            Appointment.end_time > new_start
        ).first()

        if overlap:
            return {'error': f'Terminkonflikt am neuen Zeitpunkt: {overlap.patient.full_name} von {overlap.start_time.strftime("%H:%M")} bis {overlap.end_time.strftime("%H:%M")}'}

        termin.start_time = new_start
        termin.end_time = new_end
        db.session.commit()

        return {
            'message': f'Termin verschoben: {termin.patient.full_name} von {altes_datum} auf {neues_datum.strftime("%d.%m.%Y")} {neue_uhrzeit.strftime("%H:%M")}',
        }

    elif tool_name == 'termin_absagen':
        termin = Appointment.query.get(tool_input['termin_id'])
        if not termin:
            return {'error': 'Termin nicht gefunden'}

        termin.status = 'cancelled'
        termin.cancellation_reason = tool_input.get('grund', '')
        db.session.commit()

        return {
            'message': f'Termin abgesagt: {termin.patient.full_name} am {termin.start_time.strftime("%d.%m.%Y %H:%M")} bei {termin.employee.display_name}',
        }

    elif tool_name == 'naechster_freier_termin':
        dauer = tool_input.get('dauer_minuten', 30)
        ab_datum = date.today()
        if tool_input.get('ab_datum'):
            ab_datum = datetime.strptime(tool_input['ab_datum'], '%Y-%m-%d').date()

        therapeut_id = tool_input.get('therapeut_id')

        # Therapeuten ermitteln
        if therapeut_id:
            therapeuten = [Employee.query.get(therapeut_id)]
        else:
            therapeuten = Employee.query.filter_by(is_active=True).all()

        slots = []
        # Nächste 14 Tage durchsuchen
        for day_offset in range(14):
            check_date = ab_datum + timedelta(days=day_offset)
            weekday = check_date.weekday()

            for emp in therapeuten:
                if not emp:
                    continue
                # Arbeitszeiten für diesen Tag
                schedules = WorkSchedule.query.filter_by(
                    employee_id=emp.id,
                    day_of_week=weekday,
                    work_type='working'
                ).all()

                for sched in schedules:
                    # Bestehende Termine an diesem Tag laden
                    day_start = datetime.combine(check_date, sched.start_time)
                    day_end = datetime.combine(check_date, sched.end_time)
                    existing = Appointment.query.filter(
                        Appointment.employee_id == emp.id,
                        Appointment.status != 'cancelled',
                        Appointment.start_time >= day_start,
                        Appointment.start_time < day_end
                    ).order_by(Appointment.start_time).all()

                    # Freie Slots finden
                    current = day_start
                    for apt in existing:
                        if (apt.start_time - current).total_seconds() >= dauer * 60:
                            slots.append({
                                'therapeut': emp.display_name,
                                'therapeut_id': emp.id,
                                'datum': check_date.strftime('%d.%m.%Y'),
                                'uhrzeit': current.strftime('%H:%M'),
                                'bis': (current + timedelta(minutes=dauer)).strftime('%H:%M'),
                            })
                            if len(slots) >= 5:
                                return {'message': f'{len(slots)} freie Termine gefunden', 'slots': slots}
                        current = max(current, apt.end_time)

                    # Nach letztem Termin
                    if (day_end - current).total_seconds() >= dauer * 60:
                        slots.append({
                            'therapeut': emp.display_name,
                            'therapeut_id': emp.id,
                            'datum': check_date.strftime('%d.%m.%Y'),
                            'uhrzeit': current.strftime('%H:%M'),
                            'bis': (current + timedelta(minutes=dauer)).strftime('%H:%M'),
                        })
                        if len(slots) >= 5:
                            return {'message': f'{len(slots)} freie Termine gefunden', 'slots': slots}

        if slots:
            return {'message': f'{len(slots)} freie Termine gefunden', 'slots': slots}
        return {'message': 'Keine freien Termine in den nächsten 14 Tagen gefunden', 'slots': []}

    elif tool_name == 'patient_termine_auflisten':
        patient = Patient.query.get(tool_input['patient_id'])
        if not patient:
            return {'error': 'Patient nicht gefunden'}

        query = Appointment.query.filter_by(patient_id=patient.id)
        if tool_input.get('nur_zukuenftige', True):
            query = query.filter(Appointment.start_time >= datetime.now())
        query = query.order_by(Appointment.start_time)

        termine = query.all()
        result = []
        for t in termine:
            result.append({
                'id': t.id,
                'datum': t.start_time.strftime('%d.%m.%Y'),
                'uhrzeit': t.start_time.strftime('%H:%M'),
                'ende': t.end_time.strftime('%H:%M'),
                'therapeut': t.employee.display_name,
                'status': t.status,
            })

        return {
            'message': f'{len(result)} Termine für {patient.full_name}',
            'patient': patient.full_name,
            'termine': result,
        }

    elif tool_name == 'tagesplan_anzeigen':
        datum_str = tool_input.get('datum', date.today().isoformat())
        datum = datetime.strptime(datum_str, '%Y-%m-%d').date()
        start = datetime.combine(datum, time.min)
        end = datetime.combine(datum, time.max)

        therapeuten = Employee.query.filter_by(is_active=True).all()
        plan = []
        for emp in therapeuten:
            termine = Appointment.query.filter(
                Appointment.employee_id == emp.id,
                Appointment.start_time >= start,
                Appointment.start_time <= end,
                Appointment.status != 'cancelled'
            ).order_by(Appointment.start_time).all()

            emp_plan = {
                'therapeut': emp.display_name,
                'therapeut_id': emp.id,
                'farbe': emp.color_code,
                'termine': [{
                    'id': t.id,
                    'patient': t.patient.full_name,
                    'start': t.start_time.strftime('%H:%M'),
                    'ende': t.end_time.strftime('%H:%M'),
                    'status': t.status,
                } for t in termine]
            }
            plan.append(emp_plan)

        return {
            'message': f'Tagesplan für {datum.strftime("%d.%m.%Y")}',
            'datum': datum.strftime('%d.%m.%Y'),
            'therapeuten': plan,
        }

    return {'error': f'Unbekanntes Tool: {tool_name}'}


def create_termin_agent():
    """Erstellt eine Instanz des Termin-Agenten."""
    return BaseAgent(
        name='termin_agent',
        system_prompt=SYSTEM_PROMPT,
        tools=TOOLS,
        tool_executor=execute_tool,
    )
