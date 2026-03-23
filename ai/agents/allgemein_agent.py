import json
from datetime import datetime, timedelta
from flask import current_app
from ai.base_agent import BaseAgent
from models import db, Patient, Appointment, Employee, User, Location


# Tool-Definitionen
TOOLS = [
    {
        'name': 'patient_suchen',
        'description': 'Sucht Patienten nach Name, Vorname, Geburtsdatum oder Patientennummer. Gibt eine Liste passender Patienten zurueck.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'suchbegriff': {
                    'type': 'string',
                    'description': 'Suchbegriff (Name, Vorname, Patientennummer)'
                }
            },
            'required': ['suchbegriff']
        }
    },
    {
        'name': 'patient_erstellen',
        'description': 'Erstellt einen neuen Patienten in der Datenbank.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'vorname': {'type': 'string', 'description': 'Vorname des Patienten'},
                'nachname': {'type': 'string', 'description': 'Nachname des Patienten'},
                'geburtsdatum': {'type': 'string', 'description': 'Geburtsdatum (TT.MM.JJJJ)'},
                'telefon': {'type': 'string', 'description': 'Telefonnummer'},
                'email': {'type': 'string', 'description': 'E-Mail-Adresse'},
                'geschlecht': {'type': 'string', 'description': 'Geschlecht (maennlich/weiblich/divers)'}
            },
            'required': ['vorname', 'nachname']
        }
    },
    {
        'name': 'termine_anzeigen',
        'description': 'Zeigt Termine fuer einen bestimmten Zeitraum an. Kann nach Therapeut, Patient oder Datum gefiltert werden.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'datum': {
                    'type': 'string',
                    'description': 'Datum (TT.MM.JJJJ) oder "heute", "morgen", "diese_woche"'
                },
                'therapeut_name': {
                    'type': 'string',
                    'description': 'Name des Therapeuten (optional)'
                },
                'patient_name': {
                    'type': 'string',
                    'description': 'Name des Patienten (optional)'
                }
            },
            'required': ['datum']
        }
    },
    {
        'name': 'termin_erstellen',
        'description': 'Erstellt einen neuen Termin.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'patient_id': {'type': 'integer', 'description': 'ID des Patienten'},
                'therapeut_id': {'type': 'integer', 'description': 'ID des Therapeuten (Employee)'},
                'datum': {'type': 'string', 'description': 'Datum (TT.MM.JJJJ)'},
                'uhrzeit': {'type': 'string', 'description': 'Uhrzeit (HH:MM)'},
                'dauer': {'type': 'integer', 'description': 'Dauer in Minuten (Standard: 30)'},
                'titel': {'type': 'string', 'description': 'Titel des Termins (optional)'}
            },
            'required': ['patient_id', 'therapeut_id', 'datum', 'uhrzeit']
        }
    },
    {
        'name': 'mitarbeiter_auflisten',
        'description': 'Listet alle aktiven Mitarbeiter/Therapeuten auf.',
        'input_schema': {
            'type': 'object',
            'properties': {},
            'required': []
        }
    }
]


def tool_executor(tool_name, tool_input):
    """Fuehrt die Tools des Allgemein-Agenten aus"""

    if tool_name == 'patient_suchen':
        suchbegriff = tool_input['suchbegriff'].strip()
        patienten = Patient.query.filter(
            db.or_(
                Patient.first_name.ilike(f'%{suchbegriff}%'),
                Patient.last_name.ilike(f'%{suchbegriff}%'),
                Patient.patient_number.ilike(f'%{suchbegriff}%'),
                (Patient.first_name + ' ' + Patient.last_name).ilike(f'%{suchbegriff}%')
            ),
            Patient.is_active == True
        ).limit(20).all()

        if not patienten:
            return {'ergebnis': 'Keine Patienten gefunden.', 'anzahl': 0}

        ergebnisse = []
        for p in patienten:
            ergebnisse.append({
                'id': p.id,
                'patient_number': p.patient_number,
                'name': f'{p.first_name} {p.last_name}',
                'geburtsdatum': p.date_of_birth.strftime('%d.%m.%Y') if p.date_of_birth else None,
                'telefon': p.phone or p.mobile,
                'email': p.email,
                'versicherung': p.insurance_provider.name if p.insurance_provider else None
            })

        return {'ergebnis': ergebnisse, 'anzahl': len(ergebnisse)}

    elif tool_name == 'patient_erstellen':
        from flask_login import current_user
        patient = Patient(
            organization_id=current_user.organization_id,
            first_name=tool_input['vorname'],
            last_name=tool_input['nachname'],
            gender=tool_input.get('geschlecht'),
            phone=tool_input.get('telefon'),
            email=tool_input.get('email'),
            patient_number=f'P{Patient.query.count() + 1:05d}'
        )
        if tool_input.get('geburtsdatum'):
            try:
                patient.date_of_birth = datetime.strptime(tool_input['geburtsdatum'], '%d.%m.%Y').date()
            except ValueError:
                pass

        db.session.add(patient)
        db.session.commit()

        return {
            'ergebnis': 'Patient erfolgreich erstellt.',
            'patient': {
                'id': patient.id,
                'patient_number': patient.patient_number,
                'name': f'{patient.first_name} {patient.last_name}'
            }
        }

    elif tool_name == 'termine_anzeigen':
        datum_str = tool_input['datum'].strip().lower()
        now = datetime.now()

        if datum_str == 'heute':
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = now.replace(hour=23, minute=59, second=59)
        elif datum_str == 'morgen':
            morgen = now + timedelta(days=1)
            start = morgen.replace(hour=0, minute=0, second=0, microsecond=0)
            end = morgen.replace(hour=23, minute=59, second=59)
        elif datum_str == 'diese_woche':
            start = now - timedelta(days=now.weekday())
            start = start.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=6, hours=23, minutes=59, seconds=59)
        else:
            try:
                tag = datetime.strptime(datum_str, '%d.%m.%Y')
                start = tag.replace(hour=0, minute=0, second=0, microsecond=0)
                end = tag.replace(hour=23, minute=59, second=59)
            except ValueError:
                return {'error': 'Ungueltiges Datum. Verwende TT.MM.JJJJ, "heute", "morgen" oder "diese_woche".'}

        query = Appointment.query.filter(
            Appointment.start_time >= start,
            Appointment.start_time <= end,
            Appointment.status.in_(['scheduled', 'confirmed', 'completed'])
        )

        if tool_input.get('therapeut_name'):
            therapeut_name = tool_input['therapeut_name']
            query = query.join(Employee).join(User).filter(
                db.or_(
                    User.first_name.ilike(f'%{therapeut_name}%'),
                    User.last_name.ilike(f'%{therapeut_name}%')
                )
            )

        if tool_input.get('patient_name'):
            patient_name = tool_input['patient_name']
            query = query.join(Patient).filter(
                db.or_(
                    Patient.first_name.ilike(f'%{patient_name}%'),
                    Patient.last_name.ilike(f'%{patient_name}%')
                )
            )

        termine = query.order_by(Appointment.start_time).all()

        ergebnisse = []
        for t in termine:
            ergebnisse.append({
                'id': t.id,
                'zeit': t.start_time.strftime('%d.%m.%Y %H:%M'),
                'ende': t.end_time.strftime('%H:%M'),
                'dauer': t.duration_minutes,
                'patient': f'{t.patient.first_name} {t.patient.last_name}',
                'therapeut': f'{t.employee.user.first_name} {t.employee.user.last_name}' if t.employee and t.employee.user else 'Unbekannt',
                'status': t.status,
                'titel': t.title or t.appointment_type
            })

        return {'ergebnis': ergebnisse, 'anzahl': len(ergebnisse)}

    elif tool_name == 'termin_erstellen':
        try:
            datum = datetime.strptime(tool_input['datum'], '%d.%m.%Y')
            uhrzeit = datetime.strptime(tool_input['uhrzeit'], '%H:%M')
            start_time = datum.replace(hour=uhrzeit.hour, minute=uhrzeit.minute)
            dauer = tool_input.get('dauer', 30)
            end_time = start_time + timedelta(minutes=dauer)

            # Patient und Therapeut pruefen
            patient = Patient.query.get(tool_input['patient_id'])
            if not patient:
                return {'error': 'Patient nicht gefunden.'}

            employee = Employee.query.get(tool_input['therapeut_id'])
            if not employee:
                return {'error': 'Therapeut nicht gefunden.'}

            termin = Appointment(
                patient_id=patient.id,
                employee_id=employee.id,
                location_id=employee.default_location_id,
                start_time=start_time,
                end_time=end_time,
                duration_minutes=dauer,
                title=tool_input.get('titel', 'Behandlung'),
                status='scheduled'
            )
            db.session.add(termin)
            db.session.commit()

            return {
                'ergebnis': 'Termin erfolgreich erstellt.',
                'termin': {
                    'id': termin.id,
                    'zeit': start_time.strftime('%d.%m.%Y %H:%M'),
                    'patient': f'{patient.first_name} {patient.last_name}',
                    'therapeut': f'{employee.user.first_name} {employee.user.last_name}'
                }
            }
        except ValueError as e:
            return {'error': f'Fehler beim Erstellen des Termins: {str(e)}'}

    elif tool_name == 'mitarbeiter_auflisten':
        mitarbeiter = Employee.query.filter_by(is_active=True).all()
        ergebnisse = []
        for m in mitarbeiter:
            ergebnisse.append({
                'id': m.id,
                'name': f'{m.user.first_name} {m.user.last_name}' if m.user else 'Unbekannt',
                'rolle': m.user.role if m.user else None,
                'pensum': m.pensum_percent,
                'standort': m.default_location.name if m.default_location else None,
                'farbe': m.color_code
            })
        return {'ergebnis': ergebnisse, 'anzahl': len(ergebnisse)}

    return {'error': f'Unbekanntes Tool: {tool_name}'}


class AllgemeinAgent(BaseAgent):
    """Allgemeiner Agent fuer grundlegende Praxis-Aufgaben"""

    def __init__(self):
        system_prompt = """Du bist der allgemeine Assistent der OMNIA Praxissoftware.
Du hilfst bei grundlegenden Aufgaben rund um Patienten, Termine und Mitarbeiter.

Deine Faehigkeiten:
- Patienten suchen und neue Patienten erfassen
- Termine anzeigen und neue Termine erstellen
- Mitarbeiter auflisten

Wichtige Regeln:
- Antworte immer auf Deutsch
- Sei freundlich und professionell
- Verwende die verfuegbaren Tools, um Daten abzufragen oder zu aendern
- Wenn du eine Aufgabe nicht ausfuehren kannst, sage es ehrlich
- Formatiere Ergebnisse uebersichtlich
- Verwende Aufzaehlungen und Tabellen wo sinnvoll"""

        super().__init__(
            name='allgemein',
            system_prompt=system_prompt,
            tools=TOOLS,
            tool_executor=tool_executor
        )
