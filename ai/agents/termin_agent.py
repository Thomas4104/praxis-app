# Termin-Agent: Spezialist für Kalender, Termine, Planung, Verfügbarkeit, Constraint-Solver

from datetime import datetime, date, time, timedelta
from models import (db, Appointment, Employee, Patient, WorkSchedule,
                    Resource, Location, TreatmentSeries, TreatmentSeriesTemplate,
                    WaitlistEntry)
from ai.base_agent import BaseAgent
from ai.constraint_solver import solver

SYSTEM_PROMPT = """Du bist der Termin-Spezialist der OMNIA Praxissoftware. Du bist Experte für Kalender, Terminplanung und Verfügbarkeit.

Du kennst die Arbeitszeiten aller Therapeuten, die Praxis-Öffnungszeiten und die Ressourcen (Räume, Geräte).

Bei der Terminsuche berücksichtigst du IMMER alle 7 Abhängigkeiten:
1. Praxis-Öffnungszeiten (inkl. Feiertage)
2. Arbeitszeiten des Therapeuten (inkl. Abwesenheiten)
3. Kapazität des Therapeuten
4. Patientenpräferenzen (bevorzugte Zeiten)
5. Bestehende Termine (keine Überschneidungen)
6. Ressourcen-Verfügbarkeit (Räume, Geräte)
7. Serien-Templates (Mindestabstände zwischen Terminen)

Du kannst:
- Termine anzeigen, erstellen, verschieben, absagen
- Freie Termine finden (intelligenter Constraint-Solver)
- Komplette Behandlungsserien planen
- Verfügbarkeit prüfen mit Erklärung
- Ressourcen prüfen
- Warteliste verwalten

Regeln:
- Antworte immer auf Deutsch, kurz und professionell
- Nenne bei Terminen immer Datum, Uhrzeit und Therapeut
- Bei Terminverschiebungen: alten und neuen Termin nennen
- Zeitformat: HH:MM (24h), Datum: DD.MM.YYYY
- Bei Konflikten: erkläre warum ein Slot nicht verfügbar ist"""

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
        "description": "Erstellt einen neuen Termin. Prüft automatisch alle Constraints.",
        "input_schema": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "integer"},
                "therapeut_id": {"type": "integer"},
                "datum": {"type": "string", "description": "Datum YYYY-MM-DD"},
                "uhrzeit": {"type": "string", "description": "Startzeit HH:MM"},
                "dauer_minuten": {"type": "integer", "description": "Standard: 30"},
                "serie_id": {"type": "integer", "description": "Optional: Zugehörige Behandlungsserie"},
                "ressource_id": {"type": "integer", "description": "Optional: Raum/Gerät"},
                "notizen": {"type": "string"},
            },
            "required": ["patient_id", "therapeut_id", "datum", "uhrzeit"]
        }
    },
    {
        "name": "termin_verschieben",
        "description": "Verschiebt einen bestehenden Termin.",
        "input_schema": {
            "type": "object",
            "properties": {
                "termin_id": {"type": "integer"},
                "neues_datum": {"type": "string", "description": "YYYY-MM-DD"},
                "neue_uhrzeit": {"type": "string", "description": "HH:MM"},
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
                "termin_id": {"type": "integer"},
                "grund": {"type": "string"},
            },
            "required": ["termin_id"]
        }
    },
    {
        "name": "naechster_freier_termin",
        "description": "Findet freie Terminslots mit dem intelligenten Constraint-Solver. Berücksichtigt alle 7 Abhängigkeiten.",
        "input_schema": {
            "type": "object",
            "properties": {
                "therapeut_id": {"type": "integer", "description": "Optional: bestimmter Therapeut"},
                "dauer_minuten": {"type": "integer", "description": "Standard: 30"},
                "ab_datum": {"type": "string", "description": "Ab welchem Datum (YYYY-MM-DD)"},
                "patient_id": {"type": "integer", "description": "Optional: für Patientenpräferenzen"},
                "bevorzugte_tage": {"type": "array", "items": {"type": "integer"}, "description": "Optional: bevorzugte Wochentage (0=Mo, 4=Fr)"},
                "bevorzugte_zeit_von": {"type": "string", "description": "Optional: früheste Uhrzeit HH:MM"},
                "bevorzugte_zeit_bis": {"type": "string", "description": "Optional: späteste Uhrzeit HH:MM"},
                "anzahl_vorschlaege": {"type": "integer", "description": "Standard: 5"},
            },
            "required": []
        }
    },
    {
        "name": "serie_planen",
        "description": "Plant eine komplette Behandlungsserie mit dem Constraint-Solver. Gibt Terminvorschläge für alle Termine der Serie zurück.",
        "input_schema": {
            "type": "object",
            "properties": {
                "serie_id": {"type": "integer", "description": "ID der Behandlungsserie"},
                "bevorzugter_tag": {"type": "integer", "description": "Optional: bevorzugter Wochentag (0=Mo, 4=Fr)"},
                "bevorzugte_uhrzeit": {"type": "string", "description": "Optional: bevorzugte Uhrzeit HH:MM"},
                "startdatum": {"type": "string", "description": "Optional: Startdatum YYYY-MM-DD"},
                "automatisch_buchen": {"type": "boolean", "description": "Termine direkt buchen? Standard: false"},
            },
            "required": ["serie_id"]
        }
    },
    {
        "name": "verfuegbarkeit_pruefen",
        "description": "Prüft ob ein bestimmter Zeitslot verfügbar ist und erklärt warum nicht.",
        "input_schema": {
            "type": "object",
            "properties": {
                "therapeut_id": {"type": "integer"},
                "datum": {"type": "string", "description": "YYYY-MM-DD"},
                "uhrzeit": {"type": "string", "description": "HH:MM"},
                "dauer_minuten": {"type": "integer", "description": "Standard: 30"},
                "ressource_id": {"type": "integer", "description": "Optional: Ressource prüfen"},
                "patient_id": {"type": "integer", "description": "Optional: für Patientenpräferenzen"},
                "serie_id": {"type": "integer", "description": "Optional: für Serien-Interval"},
            },
            "required": ["therapeut_id", "datum", "uhrzeit"]
        }
    },
    {
        "name": "ressource_pruefen",
        "description": "Prüft die Verfügbarkeit einer Ressource (Raum/Gerät) an einem bestimmten Tag.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ressource_id": {"type": "integer", "description": "ID der Ressource"},
                "datum": {"type": "string", "description": "Datum YYYY-MM-DD"},
            },
            "required": ["ressource_id", "datum"]
        }
    },
    {
        "name": "warteliste_verwalten",
        "description": "Verwaltet die Warteliste: anzeigen, hinzufügen, entfernen.",
        "input_schema": {
            "type": "object",
            "properties": {
                "aktion": {"type": "string", "description": "anzeigen/hinzufuegen/entfernen", "enum": ["anzeigen", "hinzufuegen", "entfernen"]},
                "patient_id": {"type": "integer", "description": "Für hinzufuegen: Patient-ID"},
                "therapeut_id": {"type": "integer", "description": "Für hinzufuegen: bevorzugter Therapeut"},
                "dauer_minuten": {"type": "integer", "description": "Für hinzufuegen: Termindauer"},
                "prioritaet": {"type": "integer", "description": "1-10, Standard: 5"},
                "eintrag_id": {"type": "integer", "description": "Für entfernen: Eintrag-ID"},
                "notizen": {"type": "string"},
            },
            "required": ["aktion"]
        }
    },
    {
        "name": "patient_termine_auflisten",
        "description": "Zeigt alle Termine eines Patienten.",
        "input_schema": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "integer"},
                "nur_zukuenftige": {"type": "boolean", "description": "Standard: true"},
            },
            "required": ["patient_id"]
        }
    },
    {
        "name": "tagesplan_anzeigen",
        "description": "Zeigt den kompletten Tagesplan mit allen Therapeuten.",
        "input_schema": {
            "type": "object",
            "properties": {
                "datum": {"type": "string", "description": "YYYY-MM-DD (Standard: heute)"},
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

        return {
            'message': f'{len(termine)} Termine am {datum.strftime("%d.%m.%Y")}',
            'termine': [{
                'id': t.id, 'patient': t.patient.full_name,
                'therapeut': t.employee.display_name,
                'start': t.start_time.strftime('%H:%M'),
                'ende': t.end_time.strftime('%H:%M'),
                'status': t.status, 'notizen': t.notes or '',
            } for t in termine]
        }

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

        # Constraint-Solver: Alle 7 Abhängigkeiten prüfen
        results = solver.check_all_constraints(
            start_dt, end_dt, employee.id,
            resource_id=tool_input.get('ressource_id'),
            patient_id=patient.id,
            series_id=tool_input.get('serie_id'),
        )

        # Fehler sammeln
        errors = [r.reason for r in results if not r.ok]
        if errors:
            return {'error': 'Termin nicht möglich:\n' + '\n'.join(f'- {e}' for e in errors)}

        # Standort ermitteln
        location_id = None
        schedule = WorkSchedule.query.filter_by(
            employee_id=employee.id, day_of_week=datum.weekday()
        ).first()
        if schedule:
            location_id = schedule.location_id

        termin = Appointment(
            patient_id=patient.id,
            employee_id=employee.id,
            location_id=location_id,
            resource_id=tool_input.get('ressource_id'),
            series_id=tool_input.get('serie_id'),
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

        # Constraints prüfen
        results = solver.check_all_constraints(
            new_start, new_end, termin.employee_id,
            resource_id=termin.resource_id,
            patient_id=termin.patient_id,
            series_id=termin.series_id,
            exclude_appointment_id=termin.id,
        )
        errors = [r.reason for r in results if not r.ok]
        if errors:
            return {'error': 'Verschiebung nicht möglich:\n' + '\n'.join(f'- {e}' for e in errors)}

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

        # Warteliste prüfen: gibt es jemanden der diesen Slot nutzen könnte?
        waitlist = WaitlistEntry.query.filter_by(status='waiting').order_by(
            WaitlistEntry.priority, WaitlistEntry.created_at
        ).limit(3).all()

        warteliste_hinweis = ''
        if waitlist:
            namen = [w.patient.full_name for w in waitlist]
            warteliste_hinweis = f'\nAuf der Warteliste: {", ".join(namen)}'

        return {
            'message': f'Termin abgesagt: {termin.patient.full_name} am {termin.start_time.strftime("%d.%m.%Y %H:%M")} bei {termin.employee.display_name}{warteliste_hinweis}',
        }

    elif tool_name == 'naechster_freier_termin':
        dauer = tool_input.get('dauer_minuten', 30)
        ab_datum = date.today()
        if tool_input.get('ab_datum'):
            ab_datum = datetime.strptime(tool_input['ab_datum'], '%Y-%m-%d').date()

        therapeut_id = tool_input.get('therapeut_id')

        if therapeut_id:
            # Constraint-Solver für einzelnen Therapeuten
            slots = solver.find_slots(
                employee_id=therapeut_id,
                duration_minutes=dauer,
                num_slots=tool_input.get('anzahl_vorschlaege', 5),
                start_date=ab_datum,
                patient_id=tool_input.get('patient_id'),
                preferred_days=tool_input.get('bevorzugte_tage'),
                preferred_time_from=tool_input.get('bevorzugte_zeit_von'),
                preferred_time_to=tool_input.get('bevorzugte_zeit_bis'),
            )
            if slots:
                emp = Employee.query.get(therapeut_id)
                return {
                    'message': f'{len(slots)} freie Termine bei {emp.display_name if emp else "Therapeut"} gefunden',
                    'slots': [s.to_dict() for s in slots]
                }
            return {'message': 'Keine freien Termine gefunden', 'slots': []}
        else:
            # Alle Therapeuten durchsuchen
            all_slots = []
            therapeuten = Employee.query.filter_by(is_active=True).all()
            for emp in therapeuten:
                if not emp.user or emp.user.role != 'therapist':
                    continue
                emp_slots = solver.find_slots(
                    employee_id=emp.id,
                    duration_minutes=dauer,
                    num_slots=2,
                    start_date=ab_datum,
                    patient_id=tool_input.get('patient_id'),
                    preferred_days=tool_input.get('bevorzugte_tage'),
                    preferred_time_from=tool_input.get('bevorzugte_zeit_von'),
                    preferred_time_to=tool_input.get('bevorzugte_zeit_bis'),
                )
                for s in emp_slots:
                    d = s.to_dict()
                    d['therapeut'] = emp.display_name
                    all_slots.append((s.score, d))

            all_slots.sort(key=lambda x: x[0], reverse=True)
            best = [s[1] for s in all_slots[:tool_input.get('anzahl_vorschlaege', 5)]]

            if best:
                return {'message': f'{len(best)} freie Termine gefunden', 'slots': best}
            return {'message': 'Keine freien Termine in den nächsten 14 Tagen', 'slots': []}

    elif tool_name == 'serie_planen':
        serie = TreatmentSeries.query.get(tool_input['serie_id'])
        if not serie:
            return {'error': 'Serie nicht gefunden'}
        if not serie.template:
            return {'error': 'Serie hat kein Template. Termine müssen einzeln geplant werden.'}

        start_date = date.today() + timedelta(days=1)
        if tool_input.get('startdatum'):
            start_date = datetime.strptime(tool_input['startdatum'], '%Y-%m-%d').date()

        result = solver.plan_series(
            patient_id=serie.patient_id,
            employee_id=serie.therapist_id,
            template_id=serie.template_id,
            start_date=start_date,
            preferred_day=tool_input.get('bevorzugter_tag'),
            preferred_time=tool_input.get('bevorzugte_uhrzeit'),
            series_id=serie.id,
        )

        if tool_input.get('automatisch_buchen') and result.get('vorschlaege'):
            count = 0
            for v in result['vorschlaege']:
                if v.get('error'):
                    continue
                try:
                    # Datum konvertieren: DD.MM.YYYY → datetime
                    parts = v['datum'].split('.')
                    slot_date = date(int(parts[2]), int(parts[1]), int(parts[0]))
                    slot_time = datetime.strptime(v['start'], '%H:%M').time()
                    end_time = datetime.strptime(v['ende'], '%H:%M').time()

                    termin = Appointment(
                        series_id=serie.id,
                        patient_id=serie.patient_id,
                        employee_id=serie.therapist_id,
                        location_id=v.get('location_id'),
                        resource_id=v.get('resource_id'),
                        start_time=datetime.combine(slot_date, slot_time),
                        end_time=datetime.combine(slot_date, end_time),
                        status='scheduled',
                        type='treatment',
                    )
                    db.session.add(termin)
                    count += 1
                except (ValueError, KeyError, IndexError):
                    pass

            db.session.commit()
            result['gebucht'] = count
            result['message'] = f'{count} Termine für {serie.patient.full_name} gebucht'

        return result

    elif tool_name == 'verfuegbarkeit_pruefen':
        datum = datetime.strptime(tool_input['datum'], '%Y-%m-%d').date()
        uhrzeit = datetime.strptime(tool_input['uhrzeit'], '%H:%M').time()
        dauer = tool_input.get('dauer_minuten', 30)

        start_dt = datetime.combine(datum, uhrzeit)
        end_dt = start_dt + timedelta(minutes=dauer)

        results = solver.check_all_constraints(
            start_dt, end_dt, tool_input['therapeut_id'],
            resource_id=tool_input.get('ressource_id'),
            patient_id=tool_input.get('patient_id'),
            series_id=tool_input.get('serie_id'),
        )

        ok_count = sum(1 for r in results if r.ok)
        errors = [r.reason for r in results if not r.ok]

        employee = Employee.query.get(tool_input['therapeut_id'])
        emp_name = employee.display_name if employee else f'Therapeut #{tool_input["therapeut_id"]}'

        if errors:
            return {
                'verfuegbar': False,
                'message': f'{emp_name} am {datum.strftime("%d.%m.%Y")} um {uhrzeit.strftime("%H:%M")} NICHT verfügbar',
                'gruende': errors,
                'geprueft': f'{ok_count}/{len(results)} Constraints erfüllt',
            }
        return {
            'verfuegbar': True,
            'message': f'{emp_name} am {datum.strftime("%d.%m.%Y")} um {uhrzeit.strftime("%H:%M")} ist verfügbar',
            'geprueft': f'{ok_count}/{len(results)} Constraints erfüllt',
        }

    elif tool_name == 'ressource_pruefen':
        resource = Resource.query.get(tool_input['ressource_id'])
        if not resource:
            return {'error': 'Ressource nicht gefunden'}

        datum = datetime.strptime(tool_input['datum'], '%Y-%m-%d').date()
        start_dt = datetime.combine(datum, time.min)
        end_dt = datetime.combine(datum, time.max)

        belegungen = Appointment.query.filter(
            Appointment.resource_id == resource.id,
            Appointment.status != 'cancelled',
            Appointment.start_time >= start_dt,
            Appointment.start_time <= end_dt
        ).order_by(Appointment.start_time).all()

        return {
            'ressource': resource.name,
            'typ': resource.type,
            'standort': resource.location.name if resource.location else '-',
            'kapazitaet': resource.capacity,
            'datum': datum.strftime('%d.%m.%Y'),
            'belegungen': [{
                'start': b.start_time.strftime('%H:%M'),
                'ende': b.end_time.strftime('%H:%M'),
                'patient': b.patient.full_name,
                'therapeut': b.employee.display_name,
            } for b in belegungen],
            'belegt': len(belegungen),
            'frei': max(0, resource.capacity - len(belegungen)),
        }

    elif tool_name == 'warteliste_verwalten':
        aktion = tool_input['aktion']

        if aktion == 'anzeigen':
            eintraege = WaitlistEntry.query.filter_by(status='waiting').order_by(
                WaitlistEntry.priority, WaitlistEntry.created_at
            ).all()

            if not eintraege:
                return {'message': 'Warteliste ist leer', 'eintraege': []}

            return {
                'message': f'{len(eintraege)} Patient(en) auf der Warteliste',
                'eintraege': [{
                    'id': e.id,
                    'patient': e.patient.full_name,
                    'patient_id': e.patient_id,
                    'therapeut': e.therapist.display_name if e.therapist else 'Beliebig',
                    'dauer': e.duration_minutes,
                    'prioritaet': e.priority,
                    'seit': e.created_at.strftime('%d.%m.%Y'),
                    'notizen': e.notes or '',
                } for e in eintraege]
            }

        elif aktion == 'hinzufuegen':
            patient_id = tool_input.get('patient_id')
            if not patient_id:
                return {'error': 'patient_id ist erforderlich'}

            patient = Patient.query.get(patient_id)
            if not patient:
                return {'error': 'Patient nicht gefunden'}

            entry = WaitlistEntry(
                patient_id=patient_id,
                therapist_id=tool_input.get('therapeut_id'),
                duration_minutes=tool_input.get('dauer_minuten', 30),
                priority=tool_input.get('prioritaet', 5),
                notes=tool_input.get('notizen', ''),
            )
            db.session.add(entry)
            db.session.commit()

            return {'message': f'{patient.full_name} zur Warteliste hinzugefügt (Priorität: {entry.priority})'}

        elif aktion == 'entfernen':
            eintrag_id = tool_input.get('eintrag_id')
            if not eintrag_id:
                return {'error': 'eintrag_id ist erforderlich'}

            entry = WaitlistEntry.query.get(eintrag_id)
            if not entry:
                return {'error': 'Wartelisten-Eintrag nicht gefunden'}

            entry.status = 'cancelled'
            db.session.commit()
            return {'message': f'{entry.patient.full_name} von der Warteliste entfernt'}

        return {'error': f'Unbekannte Aktion: {aktion}'}

    elif tool_name == 'patient_termine_auflisten':
        patient = Patient.query.get(tool_input['patient_id'])
        if not patient:
            return {'error': 'Patient nicht gefunden'}

        query = Appointment.query.filter_by(patient_id=patient.id)
        if tool_input.get('nur_zukuenftige', True):
            query = query.filter(Appointment.start_time >= datetime.now())
        query = query.order_by(Appointment.start_time)

        termine = query.all()
        return {
            'message': f'{len(termine)} Termine für {patient.full_name}',
            'patient': patient.full_name,
            'termine': [{
                'id': t.id,
                'datum': t.start_time.strftime('%d.%m.%Y'),
                'uhrzeit': t.start_time.strftime('%H:%M'),
                'ende': t.end_time.strftime('%H:%M'),
                'therapeut': t.employee.display_name,
                'status': t.status,
                'serie_id': t.series_id,
            } for t in termine],
        }

    elif tool_name == 'tagesplan_anzeigen':
        datum_str = tool_input.get('datum', date.today().isoformat())
        datum = datetime.strptime(datum_str, '%Y-%m-%d').date()
        start = datetime.combine(datum, time.min)
        end = datetime.combine(datum, time.max)

        therapeuten = Employee.query.filter_by(is_active=True).all()
        plan = []
        for emp in therapeuten:
            if not emp.user or emp.user.role != 'therapist':
                continue
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
                    'id': t.id, 'patient': t.patient.full_name,
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
