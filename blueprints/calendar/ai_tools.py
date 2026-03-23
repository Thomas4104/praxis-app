"""KI-Tools fuer den Kalender- und Terminbereich"""
import json
from datetime import datetime, date, timedelta, time
from models import db, Appointment, Employee, Patient, Location, Resource, \
    TreatmentSeries, TreatmentSeriesTemplate, WaitingList, WorkSchedule


CALENDAR_TOOLS = [
    {
        'name': 'termine_anzeigen',
        'description': 'Zeigt alle Termine eines bestimmten Tages an, optional gefiltert nach Therapeut und Standort.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'datum': {'type': 'string', 'description': 'Datum im Format YYYY-MM-DD (Standard: heute)'},
                'therapeut_id': {'type': 'integer', 'description': 'ID des Therapeuten (optional)'},
                'standort_id': {'type': 'integer', 'description': 'ID des Standorts (optional)'}
            },
            'required': []
        }
    },
    {
        'name': 'termin_erstellen',
        'description': 'Erstellt einen neuen Termin fuer einen Patienten.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'patient_id': {'type': 'integer', 'description': 'ID des Patienten'},
                'employee_id': {'type': 'integer', 'description': 'ID des Therapeuten'},
                'datum': {'type': 'string', 'description': 'Datum im Format YYYY-MM-DD'},
                'uhrzeit': {'type': 'string', 'description': 'Uhrzeit im Format HH:MM'},
                'dauer': {'type': 'integer', 'description': 'Dauer in Minuten (Standard: 30)'},
                'raum_id': {'type': 'integer', 'description': 'ID des Raums (optional)'}
            },
            'required': ['patient_id', 'employee_id', 'datum', 'uhrzeit']
        }
    },
    {
        'name': 'termin_verschieben',
        'description': 'Verschiebt einen bestehenden Termin auf ein neues Datum/Uhrzeit oder zu einem anderen Therapeuten.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'termin_id': {'type': 'integer', 'description': 'ID des Termins'},
                'neues_datum': {'type': 'string', 'description': 'Neues Datum im Format YYYY-MM-DD'},
                'neue_uhrzeit': {'type': 'string', 'description': 'Neue Uhrzeit im Format HH:MM'},
                'neuer_therapeut_id': {'type': 'integer', 'description': 'ID des neuen Therapeuten (optional)'}
            },
            'required': ['termin_id', 'neues_datum', 'neue_uhrzeit']
        }
    },
    {
        'name': 'termin_absagen',
        'description': 'Sagt einen Termin ab mit Angabe des Grundes und optionaler Stornogebuehr.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'termin_id': {'type': 'integer', 'description': 'ID des Termins'},
                'grund': {'type': 'string', 'description': 'Grund der Absage (Patient, Praxis, Sonstiges)'},
                'stornogebuehr': {'type': 'number', 'description': 'Stornogebuehr in CHF (optional, 0 = keine)'}
            },
            'required': ['termin_id', 'grund']
        }
    },
    {
        'name': 'termin_status_aendern',
        'description': 'Aendert den Status eines Termins (geplant, bestaetigt, erschienen, nicht erschienen).',
        'input_schema': {
            'type': 'object',
            'properties': {
                'termin_id': {'type': 'integer', 'description': 'ID des Termins'},
                'status': {'type': 'string', 'description': 'Neuer Status: scheduled, confirmed, appeared, no_show'}
            },
            'required': ['termin_id', 'status']
        }
    },
    {
        'name': 'naechster_freier_termin',
        'description': 'Findet den naechsten freien Terminslot fuer einen Therapeuten. Beruecksichtigt Arbeitszeiten, Absenzen, bestehende Termine und Feiertage.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'therapeut_id': {'type': 'integer', 'description': 'ID des Therapeuten'},
                'dauer_minuten': {'type': 'integer', 'description': 'Gewuenschte Termindauer in Minuten (Standard: 30)'},
                'ab_datum': {'type': 'string', 'description': 'Ab welchem Datum suchen (Standard: heute, Format: YYYY-MM-DD)'}
            },
            'required': ['therapeut_id']
        }
    },
    {
        'name': 'verfuegbarkeit_pruefen',
        'description': 'Prueft ob ein Therapeut zu einem bestimmten Zeitpunkt verfuegbar ist.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'therapeut_id': {'type': 'integer', 'description': 'ID des Therapeuten'},
                'datum': {'type': 'string', 'description': 'Datum im Format YYYY-MM-DD'},
                'uhrzeit': {'type': 'string', 'description': 'Uhrzeit im Format HH:MM'},
                'dauer': {'type': 'integer', 'description': 'Dauer in Minuten (Standard: 30)'}
            },
            'required': ['therapeut_id', 'datum', 'uhrzeit']
        }
    },
    {
        'name': 'tagesplan',
        'description': 'Zeigt den kompletten Tagesplan mit allen Therapeuten und Terminen eines Standorts.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'datum': {'type': 'string', 'description': 'Datum im Format YYYY-MM-DD (Standard: heute)'},
                'standort_id': {'type': 'integer', 'description': 'ID des Standorts (optional)'}
            },
            'required': []
        }
    },
    {
        'name': 'serie_planen',
        'description': 'Plant eine Behandlungsserie mit mehreren Terminen basierend auf einer Vorlage. Nutzt den Constraint-Solver fuer optimale Terminvorschlaege.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'patient_id': {'type': 'integer', 'description': 'ID des Patienten'},
                'template_id': {'type': 'integer', 'description': 'ID der Serienvorlage'},
                'therapeut_id': {'type': 'integer', 'description': 'ID des Therapeuten'},
                'bevorzugter_tag': {'type': 'array', 'items': {'type': 'integer'}, 'description': 'Bevorzugte Wochentage (0=Mo, 4=Fr)'}
            },
            'required': ['patient_id', 'template_id', 'therapeut_id']
        }
    },
    {
        'name': 'termine_patient',
        'description': 'Zeigt alle Termine eines Patienten (vergangene und zukuenftige).',
        'input_schema': {
            'type': 'object',
            'properties': {
                'patient_id': {'type': 'integer', 'description': 'ID des Patienten'}
            },
            'required': ['patient_id']
        }
    },
    {
        'name': 'warteliste_hinzufuegen',
        'description': 'Setzt einen Patienten auf die Warteliste fuer eine Behandlung.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'patient_id': {'type': 'integer', 'description': 'ID des Patienten'},
                'template_id': {'type': 'integer', 'description': 'ID der Serienvorlage'},
                'bevorzugte_zeiten': {'type': 'array', 'items': {'type': 'string'}, 'description': 'Bevorzugte Zeitfenster (z.B. ["08:00-12:00", "14:00-17:00"])'}
            },
            'required': ['patient_id']
        }
    },
    {
        'name': 'luecken_finden',
        'description': 'Findet freie Luecken im Kalender eines Tages fuer spontane Termine.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'datum': {'type': 'string', 'description': 'Datum im Format YYYY-MM-DD (Standard: heute)'},
                'standort_id': {'type': 'integer', 'description': 'ID des Standorts (optional)'},
                'min_dauer': {'type': 'integer', 'description': 'Mindestdauer der Luecke in Minuten (Standard: 15)'}
            },
            'required': []
        }
    }
]


def calendar_tool_executor(tool_name, tool_input):
    """Fuehrt Kalender-Tools aus"""

    if tool_name == 'termine_anzeigen':
        datum_str = tool_input.get('datum', date.today().isoformat())
        try:
            target_date = datetime.strptime(datum_str, '%Y-%m-%d').date()
        except ValueError:
            target_date = date.today()

        query = Appointment.query.filter(
            Appointment.start_time >= datetime.combine(target_date, time(0, 0)),
            Appointment.start_time < datetime.combine(target_date + timedelta(days=1), time(0, 0))
        )

        if tool_input.get('therapeut_id'):
            query = query.filter(Appointment.employee_id == tool_input['therapeut_id'])
        if tool_input.get('standort_id'):
            query = query.filter(Appointment.location_id == tool_input['standort_id'])

        termine = query.order_by(Appointment.start_time).all()

        return {
            'datum': target_date.strftime('%d.%m.%Y'),
            'wochentag': ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag'][target_date.weekday()],
            'anzahl': len(termine),
            'termine': [{
                'id': t.id,
                'patient': f'{t.patient.first_name} {t.patient.last_name}' if t.patient else '-',
                'therapeut': f'{t.employee.user.first_name} {t.employee.user.last_name}' if t.employee and t.employee.user else '-',
                'uhrzeit': f'{t.start_time.strftime("%H:%M")} - {t.end_time.strftime("%H:%M")}',
                'dauer': t.duration_minutes,
                'typ': t.title or t.appointment_type,
                'status': t.status,
                'notizen': t.notes or ''
            } for t in termine]
        }

    elif tool_name == 'termin_erstellen':
        patient = Patient.query.get(tool_input.get('patient_id'))
        if not patient:
            return {'error': 'Patient nicht gefunden.'}

        employee = Employee.query.get(tool_input.get('employee_id'))
        if not employee:
            return {'error': 'Therapeut nicht gefunden.'}

        try:
            datum = datetime.strptime(tool_input['datum'], '%Y-%m-%d').date()
            parts = tool_input['uhrzeit'].split(':')
            uhrzeit = time(int(parts[0]), int(parts[1]))
        except (ValueError, KeyError):
            return {'error': 'Ungültiges Datum oder Uhrzeit.'}

        dauer = tool_input.get('dauer', 30)
        start_dt = datetime.combine(datum, uhrzeit)
        end_dt = start_dt + timedelta(minutes=dauer)

        # Doppelbuchung pruefen
        conflict = Appointment.query.filter(
            Appointment.employee_id == employee.id,
            Appointment.status.notin_(['cancelled', 'no_show']),
            Appointment.start_time < end_dt,
            Appointment.end_time > start_dt
        ).first()

        if conflict:
            return {
                'error': f'Terminüberschneidung! {employee.user.first_name} {employee.user.last_name} hat bereits einen Termin von {conflict.start_time.strftime("%H:%M")} bis {conflict.end_time.strftime("%H:%M")}.'
            }

        appt = Appointment(
            patient_id=patient.id,
            employee_id=employee.id,
            location_id=employee.default_location_id,
            resource_id=tool_input.get('raum_id'),
            start_time=start_dt,
            end_time=end_dt,
            duration_minutes=dauer,
            status='scheduled',
            appointment_type='treatment',
            title='Behandlung'
        )
        db.session.add(appt)
        db.session.commit()

        return {
            'erfolg': True,
            'termin_id': appt.id,
            'nachricht': f'Termin erstellt: {patient.first_name} {patient.last_name} bei {employee.user.first_name} {employee.user.last_name} am {datum.strftime("%d.%m.%Y")} um {uhrzeit.strftime("%H:%M")} ({dauer} Min.)'
        }

    elif tool_name == 'termin_verschieben':
        appt = Appointment.query.get(tool_input.get('termin_id'))
        if not appt:
            return {'error': 'Termin nicht gefunden.'}

        try:
            datum = datetime.strptime(tool_input['neues_datum'], '%Y-%m-%d').date()
            parts = tool_input['neue_uhrzeit'].split(':')
            uhrzeit = time(int(parts[0]), int(parts[1]))
        except (ValueError, KeyError):
            return {'error': 'Ungültiges Datum oder Uhrzeit.'}

        new_emp_id = tool_input.get('neuer_therapeut_id', appt.employee_id)
        new_start = datetime.combine(datum, uhrzeit)
        new_end = new_start + timedelta(minutes=appt.duration_minutes)

        # Doppelbuchung pruefen
        conflict = Appointment.query.filter(
            Appointment.employee_id == new_emp_id,
            Appointment.id != appt.id,
            Appointment.status.notin_(['cancelled', 'no_show']),
            Appointment.start_time < new_end,
            Appointment.end_time > new_start
        ).first()

        if conflict:
            return {'error': 'Terminüberschneidung am neuen Zeitpunkt.'}

        old_time = appt.start_time.strftime('%d.%m.%Y %H:%M')
        appt.start_time = new_start
        appt.end_time = new_end
        appt.employee_id = new_emp_id

        db.session.commit()

        return {
            'erfolg': True,
            'nachricht': f'Termin verschoben von {old_time} auf {datum.strftime("%d.%m.%Y")} um {uhrzeit.strftime("%H:%M")}.'
        }

    elif tool_name == 'termin_absagen':
        appt = Appointment.query.get(tool_input.get('termin_id'))
        if not appt:
            return {'error': 'Termin nicht gefunden.'}

        appt.status = 'cancelled'
        appt.cancellation_reason = tool_input.get('grund', '')
        fee = tool_input.get('stornogebuehr', 0)
        if fee:
            appt.cancellation_fee = float(fee)

        db.session.commit()

        patient_name = f'{appt.patient.first_name} {appt.patient.last_name}' if appt.patient else '-'
        return {
            'erfolg': True,
            'nachricht': f'Termin am {appt.start_time.strftime("%d.%m.%Y %H:%M")} fuer {patient_name} wurde abgesagt. Grund: {tool_input.get("grund", "-")}' +
                         (f', Stornogebühr: CHF {fee:.2f}' if fee else '')
        }

    elif tool_name == 'termin_status_aendern':
        appt = Appointment.query.get(tool_input.get('termin_id'))
        if not appt:
            return {'error': 'Termin nicht gefunden.'}

        valid = ['scheduled', 'confirmed', 'appeared', 'no_show']
        new_status = tool_input.get('status')
        if new_status not in valid:
            return {'error': f'Ungültiger Status. Erlaubt: {", ".join(valid)}'}

        appt.status = new_status
        db.session.commit()

        status_labels = {
            'scheduled': 'Geplant', 'confirmed': 'Bestätigt',
            'appeared': 'Erschienen', 'no_show': 'Nicht erschienen'
        }
        return {
            'erfolg': True,
            'nachricht': f'Status geändert auf: {status_labels.get(new_status, new_status)}'
        }

    elif tool_name == 'naechster_freier_termin':
        from ai.constraint_solver import find_available_slots

        emp_id = tool_input.get('therapeut_id')
        dauer = tool_input.get('dauer_minuten', 30)
        ab = tool_input.get('ab_datum', date.today().isoformat())

        employee = Employee.query.get(emp_id)
        if not employee:
            return {'error': 'Therapeut nicht gefunden.'}

        slots = find_available_slots(
            employee_id=emp_id,
            duration_minutes=dauer,
            num_slots=3,
            min_interval_days=0,
            start_date=ab
        )

        if not slots:
            return {'nachricht': 'Keine freien Termine in den nächsten 60 Tagen gefunden.'}

        emp_name = f'{employee.user.first_name} {employee.user.last_name}' if employee.user else '-'

        return {
            'therapeut': emp_name,
            'vorschlaege': [{
                'datum': s['datum'],
                'uhrzeit': f'{s["start_zeit"]} - {s["end_zeit"]}',
                'bewertung': s['score']
            } for s in slots]
        }

    elif tool_name == 'verfuegbarkeit_pruefen':
        from ai.constraint_solver import check_availability

        result = check_availability(
            employee_id=tool_input['therapeut_id'],
            check_date=tool_input['datum'],
            check_time=tool_input['uhrzeit'],
            duration_minutes=tool_input.get('dauer', 30)
        )

        return result

    elif tool_name == 'tagesplan':
        datum_str = tool_input.get('datum', date.today().isoformat())
        try:
            target_date = datetime.strptime(datum_str, '%Y-%m-%d').date()
        except ValueError:
            target_date = date.today()

        query = Employee.query.filter_by(is_active=True)
        if tool_input.get('standort_id'):
            query = query.filter_by(default_location_id=tool_input['standort_id'])
        employees = query.all()

        plan = []
        for emp in employees:
            emp_name = f'{emp.user.first_name} {emp.user.last_name}' if emp.user else f'MA #{emp.id}'

            termine = Appointment.query.filter(
                Appointment.employee_id == emp.id,
                Appointment.status.notin_(['cancelled']),
                Appointment.start_time >= datetime.combine(target_date, time(0, 0)),
                Appointment.start_time < datetime.combine(target_date + timedelta(days=1), time(0, 0))
            ).order_by(Appointment.start_time).all()

            plan.append({
                'therapeut': emp_name,
                'therapeut_id': emp.id,
                'anzahl_termine': len(termine),
                'termine': [{
                    'uhrzeit': f'{t.start_time.strftime("%H:%M")} - {t.end_time.strftime("%H:%M")}',
                    'patient': f'{t.patient.first_name} {t.patient.last_name}' if t.patient else '-',
                    'typ': t.title or t.appointment_type,
                    'status': t.status
                } for t in termine]
            })

        return {
            'datum': target_date.strftime('%d.%m.%Y'),
            'wochentag': ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag'][target_date.weekday()],
            'therapeuten': plan
        }

    elif tool_name == 'serie_planen':
        from ai.constraint_solver import find_available_slots

        patient = Patient.query.get(tool_input.get('patient_id'))
        if not patient:
            return {'error': 'Patient nicht gefunden.'}

        template = TreatmentSeriesTemplate.query.get(tool_input.get('template_id'))
        if not template:
            return {'error': 'Serienvorlage nicht gefunden.'}

        employee = Employee.query.get(tool_input.get('therapeut_id'))
        if not employee:
            return {'error': 'Therapeut nicht gefunden.'}

        slots = find_available_slots(
            employee_id=employee.id,
            location_id=employee.default_location_id,
            duration_minutes=template.duration_minutes,
            num_slots=template.num_appointments,
            min_interval_days=template.min_interval_days,
            preferred_days=tool_input.get('bevorzugter_tag'),
            start_date=date.today()
        )

        return {
            'patient': f'{patient.first_name} {patient.last_name}',
            'vorlage': template.name,
            'therapeut': f'{employee.user.first_name} {employee.user.last_name}' if employee.user else '-',
            'anzahl_gesucht': template.num_appointments,
            'anzahl_gefunden': len(slots),
            'terminvorschlaege': [{
                'nummer': idx + 1,
                'datum': s['datum'],
                'uhrzeit': f'{s["start_zeit"]} - {s["end_zeit"]}',
                'bewertung': s['score']
            } for idx, s in enumerate(slots)]
        }

    elif tool_name == 'termine_patient':
        patient = Patient.query.get(tool_input.get('patient_id'))
        if not patient:
            return {'error': 'Patient nicht gefunden.'}

        termine = Appointment.query.filter_by(patient_id=patient.id) \
            .order_by(Appointment.start_time.desc()).limit(20).all()

        return {
            'patient': f'{patient.first_name} {patient.last_name}',
            'anzahl': len(termine),
            'termine': [{
                'id': t.id,
                'datum': t.start_time.strftime('%d.%m.%Y'),
                'uhrzeit': f'{t.start_time.strftime("%H:%M")} - {t.end_time.strftime("%H:%M")}',
                'therapeut': f'{t.employee.user.first_name} {t.employee.user.last_name}' if t.employee and t.employee.user else '-',
                'typ': t.title or t.appointment_type,
                'status': t.status
            } for t in termine]
        }

    elif tool_name == 'warteliste_hinzufuegen':
        patient = Patient.query.get(tool_input.get('patient_id'))
        if not patient:
            return {'error': 'Patient nicht gefunden.'}

        entry = WaitingList(
            patient_id=patient.id,
            template_id=tool_input.get('template_id'),
            preferred_times_json=json.dumps(tool_input.get('bevorzugte_zeiten', [])),
            status='waiting'
        )
        db.session.add(entry)
        db.session.commit()

        return {
            'erfolg': True,
            'nachricht': f'{patient.first_name} {patient.last_name} wurde auf die Warteliste gesetzt.'
        }

    elif tool_name == 'luecken_finden':
        from ai.constraint_solver import find_gaps

        datum_str = tool_input.get('datum', date.today().isoformat())
        min_dauer = tool_input.get('min_dauer', 15)
        standort_id = tool_input.get('standort_id')

        gaps = find_gaps(datum_str, standort_id, min_dauer)

        return {
            'datum': datum_str,
            'anzahl_luecken': len(gaps),
            'luecken': gaps
        }

    return {'error': f'Unbekanntes Tool: {tool_name}'}
