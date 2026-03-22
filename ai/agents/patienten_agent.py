# Patienten-Agent: Spezialist für Patientendaten, Behandlungsserien, Befunde, Behandlungsplan

from datetime import datetime, date
from sqlalchemy import or_
from models import (db, Patient, TreatmentSeries, TreatmentSeriesTemplate,
                    Appointment, Employee, Doctor, TreatmentGoal, TreatmentMeasurement)
from ai.base_agent import BaseAgent

SYSTEM_PROMPT = """Du bist der Patienten-Spezialist der OMNIA Praxissoftware. Du verwaltest alle Patientendaten, Behandlungsserien, Behandlungspläne und Befunde.

Du achtest auf Vollständigkeit der Daten und weist auf fehlende Pflichtfelder hin (Versicherungsnummer, Arzt-Zuweisung, etc.).

Du kannst:
- Patienten suchen, erstellen, bearbeiten und Details anzeigen
- Behandlungsserien starten, anzeigen und verwalten
- Behandlungspläne mit Zielen und Messungen verwalten
- Behandlungsserien-Templates auflisten

Regeln:
- Antworte immer auf Deutsch, kurz und professionell
- Nenne bei Patienten immer den vollständigen Namen
- Bei der Suche: zeige die wichtigsten Daten (Name, Geburtsdatum, Telefon)
- Weise auf fehlende Daten hin (z.B. fehlende Versicherungsnummer)
- Datenschutz beachten: Nur relevante Daten anzeigen
- Bei Behandlungsserien: nenne immer Patient, Therapeut, Template und Status"""

TOOLS = [
    {
        "name": "patient_suchen",
        "description": "Sucht Patienten nach Name, Geburtsdatum oder Telefonnummer.",
        "input_schema": {
            "type": "object",
            "properties": {
                "suchbegriff": {"type": "string", "description": "Name, Geburtsdatum (YYYY-MM-DD) oder Telefonnummer"},
            },
            "required": ["suchbegriff"]
        }
    },
    {
        "name": "patient_erstellen",
        "description": "Erstellt einen neuen Patienten.",
        "input_schema": {
            "type": "object",
            "properties": {
                "vorname": {"type": "string"},
                "nachname": {"type": "string"},
                "geburtsdatum": {"type": "string", "description": "Format: YYYY-MM-DD"},
                "geschlecht": {"type": "string", "description": "m/f/d"},
                "telefon": {"type": "string"},
                "mobile": {"type": "string"},
                "email": {"type": "string"},
                "adresse": {"type": "string"},
                "versicherungsnummer": {"type": "string"},
                "ahv_nummer": {"type": "string"},
            },
            "required": ["vorname", "nachname"]
        }
    },
    {
        "name": "patient_bearbeiten",
        "description": "Bearbeitet die Daten eines bestehenden Patienten.",
        "input_schema": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "integer"},
                "vorname": {"type": "string"},
                "nachname": {"type": "string"},
                "geburtsdatum": {"type": "string"},
                "geschlecht": {"type": "string"},
                "telefon": {"type": "string"},
                "mobile": {"type": "string"},
                "email": {"type": "string"},
                "adresse": {"type": "string"},
                "versicherungsnummer": {"type": "string"},
                "ahv_nummer": {"type": "string"},
                "notizen": {"type": "string"},
            },
            "required": ["patient_id"]
        }
    },
    {
        "name": "patient_details",
        "description": "Zeigt alle Details eines Patienten an, inklusive Termine und Serien.",
        "input_schema": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "integer"},
            },
            "required": ["patient_id"]
        }
    },
    {
        "name": "patienten_auflisten",
        "description": "Listet alle aktiven Patienten auf.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Maximale Anzahl (Standard: 20)"},
            },
            "required": []
        }
    },
    # --- Phase 2: Behandlungsserien ---
    {
        "name": "behandlungsserie_starten",
        "description": "Startet eine neue Behandlungsserie für einen Patienten. Benötigt Patient, Therapeut und optional ein Template.",
        "input_schema": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "integer", "description": "ID des Patienten"},
                "therapeut_id": {"type": "integer", "description": "ID des Therapeuten"},
                "template_id": {"type": "integer", "description": "Optional: ID des Serien-Templates"},
                "diagnose": {"type": "string", "description": "Diagnose"},
                "versicherungstyp": {"type": "string", "description": "KVG/UVG/MVG/IVG/private/self"},
                "abrechnungsmodell": {"type": "string", "description": "tiers_garant/tiers_payant"},
                "verordnungstyp": {"type": "string", "description": "initial/followup"},
            },
            "required": ["patient_id", "therapeut_id"]
        }
    },
    {
        "name": "behandlungsserie_anzeigen",
        "description": "Zeigt Details einer Behandlungsserie inkl. Termine, Ziele und Messungen.",
        "input_schema": {
            "type": "object",
            "properties": {
                "serie_id": {"type": "integer", "description": "ID der Serie"},
            },
            "required": ["serie_id"]
        }
    },
    {
        "name": "behandlungsserien_patient",
        "description": "Zeigt alle Behandlungsserien eines Patienten.",
        "input_schema": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "integer", "description": "ID des Patienten"},
                "nur_aktive": {"type": "boolean", "description": "Nur aktive Serien (Standard: false)"},
            },
            "required": ["patient_id"]
        }
    },
    {
        "name": "behandlungsserie_status",
        "description": "Ändert den Status einer Serie (abschliessen oder abbrechen).",
        "input_schema": {
            "type": "object",
            "properties": {
                "serie_id": {"type": "integer"},
                "neuer_status": {"type": "string", "description": "completed oder cancelled"},
            },
            "required": ["serie_id", "neuer_status"]
        }
    },
    {
        "name": "behandlungsplan_anzeigen",
        "description": "Zeigt den Behandlungsplan einer Serie: Ziele, Messungen, Heilungsphase, Fortschritt.",
        "input_schema": {
            "type": "object",
            "properties": {
                "serie_id": {"type": "integer"},
            },
            "required": ["serie_id"]
        }
    },
    {
        "name": "templates_auflisten",
        "description": "Listet alle verfügbaren Behandlungsserien-Templates auf.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
]


def execute_tool(tool_name, tool_input):
    """Führt ein Patienten-Tool aus."""

    if tool_name == 'patient_suchen':
        suchbegriff = tool_input['suchbegriff'].strip()
        try:
            geb_datum = datetime.strptime(suchbegriff, '%Y-%m-%d').date()
            patienten = Patient.query.filter_by(date_of_birth=geb_datum, is_active=True).all()
        except ValueError:
            search = f'%{suchbegriff}%'
            patienten = Patient.query.filter(
                Patient.is_active == True,
                or_(
                    Patient.first_name.ilike(search),
                    Patient.last_name.ilike(search),
                    Patient.phone.ilike(search),
                    Patient.mobile.ilike(search),
                    (Patient.first_name + ' ' + Patient.last_name).ilike(search),
                    (Patient.last_name + ' ' + Patient.first_name).ilike(search),
                )
            ).all()

        if not patienten:
            return {'message': f'Keine Patienten gefunden für "{suchbegriff}"', 'patienten': []}

        return {
            'message': f'{len(patienten[:20])} Patient(en) gefunden',
            'patienten': [{
                'id': p.id, 'name': p.full_name,
                'geburtsdatum': p.date_of_birth.strftime('%d.%m.%Y') if p.date_of_birth else '',
                'telefon': p.phone or p.mobile or '', 'email': p.email or '',
            } for p in patienten[:20]]
        }

    elif tool_name == 'patient_erstellen':
        from flask_login import current_user
        org_id = 1
        if current_user and current_user.is_authenticated and current_user.employee:
            org_id = current_user.employee.organization_id

        patient = Patient(
            organization_id=org_id,
            first_name=tool_input['vorname'],
            last_name=tool_input['nachname'],
        )
        if tool_input.get('geburtsdatum'):
            patient.date_of_birth = datetime.strptime(tool_input['geburtsdatum'], '%Y-%m-%d').date()
        for feld, attr in [('geschlecht', 'gender'), ('telefon', 'phone'), ('mobile', 'mobile'),
                           ('email', 'email'), ('adresse', 'address'),
                           ('versicherungsnummer', 'insurance_number'), ('ahv_nummer', 'ahv_number')]:
            if tool_input.get(feld):
                setattr(patient, attr, tool_input[feld])

        db.session.add(patient)
        db.session.commit()

        fehlende = []
        if not patient.date_of_birth: fehlende.append('Geburtsdatum')
        if not patient.insurance_number: fehlende.append('Versicherungsnummer')
        if not patient.phone and not patient.mobile: fehlende.append('Telefonnummer')

        msg = f'Patient erstellt: {patient.full_name} (ID: {patient.id})'
        if fehlende:
            msg += f'\nFehlende Daten: {", ".join(fehlende)}'
        return {'message': msg, 'patient_id': patient.id}

    elif tool_name == 'patient_bearbeiten':
        patient = Patient.query.get(tool_input['patient_id'])
        if not patient:
            return {'error': 'Patient nicht gefunden'}

        aenderungen = []
        for feld, attr in [('vorname', 'first_name'), ('nachname', 'last_name'),
                           ('telefon', 'phone'), ('mobile', 'mobile'), ('email', 'email'),
                           ('adresse', 'address'), ('versicherungsnummer', 'insurance_number'),
                           ('ahv_nummer', 'ahv_number'), ('notizen', 'notes')]:
            if feld in tool_input and tool_input[feld] is not None:
                setattr(patient, attr, tool_input[feld])
                aenderungen.append(feld)

        if tool_input.get('geburtsdatum'):
            patient.date_of_birth = datetime.strptime(tool_input['geburtsdatum'], '%Y-%m-%d').date()
            aenderungen.append('geburtsdatum')
        if tool_input.get('geschlecht'):
            patient.gender = tool_input['geschlecht']
            aenderungen.append('geschlecht')

        db.session.commit()
        return {'message': f'{patient.full_name} aktualisiert: {", ".join(aenderungen)}'}

    elif tool_name == 'patient_details':
        patient = Patient.query.get(tool_input['patient_id'])
        if not patient:
            return {'error': 'Patient nicht gefunden'}

        termine = Appointment.query.filter(
            Appointment.patient_id == patient.id,
            Appointment.start_time >= datetime.now(),
            Appointment.status != 'cancelled'
        ).order_by(Appointment.start_time).limit(10).all()

        serien = TreatmentSeries.query.filter_by(patient_id=patient.id, status='active').all()

        return {
            'patient': {
                'id': patient.id, 'name': patient.full_name,
                'geburtsdatum': patient.date_of_birth.strftime('%d.%m.%Y') if patient.date_of_birth else '',
                'alter': patient.age, 'geschlecht': patient.gender or '',
                'telefon': patient.phone or '', 'mobile': patient.mobile or '',
                'email': patient.email or '', 'adresse': patient.address or '',
                'versicherungsnummer': patient.insurance_number or '',
                'ahv_nummer': patient.ahv_number or '', 'notizen': patient.notes or '',
            },
            'naechste_termine': [{
                'id': t.id, 'datum': t.start_time.strftime('%d.%m.%Y %H:%M'),
                'therapeut': t.employee.display_name,
            } for t in termine],
            'aktive_serien': [{
                'id': s.id, 'diagnose': s.diagnosis or '',
                'therapeut': s.therapist.display_name if s.therapist else '',
                'template': s.template.name if s.template else 'Individuell',
                'phase': TreatmentSeries.PHASE_NAMES.get(s.healing_phase, s.healing_phase),
                'fortschritt': f'{s.num_completed}/{s.num_total}',
            } for s in serien],
        }

    elif tool_name == 'patienten_auflisten':
        limit = tool_input.get('limit', 20)
        patienten = Patient.query.filter_by(is_active=True).order_by(
            Patient.last_name, Patient.first_name).limit(limit).all()
        return {
            'message': f'{len(patienten)} Patienten',
            'patienten': [{
                'id': p.id, 'name': p.full_name,
                'geburtsdatum': p.date_of_birth.strftime('%d.%m.%Y') if p.date_of_birth else '',
                'telefon': p.phone or p.mobile or '',
            } for p in patienten]
        }

    # === Phase 2: Behandlungsserien ===

    elif tool_name == 'behandlungsserie_starten':
        patient = Patient.query.get(tool_input['patient_id'])
        if not patient:
            return {'error': 'Patient nicht gefunden'}

        employee = Employee.query.get(tool_input['therapeut_id'])
        if not employee:
            return {'error': 'Therapeut nicht gefunden'}

        template = None
        if tool_input.get('template_id'):
            template = TreatmentSeriesTemplate.query.get(tool_input['template_id'])

        serie = TreatmentSeries(
            patient_id=patient.id,
            therapist_id=employee.id,
            template_id=template.id if template else None,
            diagnosis=tool_input.get('diagnose', ''),
            prescription_type=tool_input.get('verordnungstyp', 'initial'),
            prescription_date=date.today(),
            insurance_type=tool_input.get('versicherungstyp', 'KVG'),
            billing_model=tool_input.get('abrechnungsmodell', 'tiers_garant'),
            status='active',
        )
        db.session.add(serie)
        db.session.commit()

        template_info = f' (Template: {template.name}, {template.num_appointments}x{template.duration_minutes}min)' if template else ''
        return {
            'message': f'Behandlungsserie gestartet für {patient.full_name} bei {employee.display_name}{template_info}',
            'serie_id': serie.id,
            'hinweis': 'Nutze den Termin-Agenten mit "serie_planen" um die Termine zu planen.',
        }

    elif tool_name == 'behandlungsserie_anzeigen':
        serie = TreatmentSeries.query.get(tool_input['serie_id'])
        if not serie:
            return {'error': 'Serie nicht gefunden'}

        termine = serie.appointments.order_by(Appointment.start_time).all()
        ziele = serie.goals.all()

        return {
            'serie': {
                'id': serie.id,
                'patient': serie.patient.full_name,
                'therapeut': serie.therapist.display_name if serie.therapist else '-',
                'template': serie.template.name if serie.template else 'Individuell',
                'diagnose': serie.diagnosis or '-',
                'status': serie.status,
                'phase': TreatmentSeries.PHASE_NAMES.get(serie.healing_phase, serie.healing_phase),
                'fortschritt': f'{serie.num_completed}/{serie.num_total}',
                'versicherung': serie.insurance_type or '-',
                'abrechnung': serie.billing_model or '-',
                'verordnung': serie.prescription_type,
                'erstellt': serie.created_at.strftime('%d.%m.%Y'),
            },
            'termine': [{
                'id': t.id,
                'datum': t.start_time.strftime('%d.%m.%Y'),
                'uhrzeit': f'{t.start_time.strftime("%H:%M")}-{t.end_time.strftime("%H:%M")}',
                'status': t.status,
            } for t in termine],
            'ziele': [{
                'id': z.id, 'titel': z.title, 'status': z.status,
                'zielwert': z.target_value or '', 'aktuell': z.current_value or '',
            } for z in ziele],
        }

    elif tool_name == 'behandlungsserien_patient':
        patient = Patient.query.get(tool_input['patient_id'])
        if not patient:
            return {'error': 'Patient nicht gefunden'}

        query = TreatmentSeries.query.filter_by(patient_id=patient.id)
        if tool_input.get('nur_aktive'):
            query = query.filter_by(status='active')

        serien = query.order_by(TreatmentSeries.created_at.desc()).all()
        return {
            'message': f'{len(serien)} Behandlungsserie(n) für {patient.full_name}',
            'serien': [{
                'id': s.id,
                'template': s.template.name if s.template else 'Individuell',
                'therapeut': s.therapist.display_name if s.therapist else '-',
                'diagnose': s.diagnosis or '-',
                'status': s.status,
                'phase': TreatmentSeries.PHASE_NAMES.get(s.healing_phase, s.healing_phase),
                'fortschritt': f'{s.num_completed}/{s.num_total}',
                'erstellt': s.created_at.strftime('%d.%m.%Y'),
            } for s in serien]
        }

    elif tool_name == 'behandlungsserie_status':
        serie = TreatmentSeries.query.get(tool_input['serie_id'])
        if not serie:
            return {'error': 'Serie nicht gefunden'}

        neuer_status = tool_input['neuer_status']
        if neuer_status not in ('completed', 'cancelled'):
            return {'error': 'Ungültiger Status. Erlaubt: completed, cancelled'}

        serie.status = neuer_status

        if neuer_status == 'cancelled':
            # Zukünftige Termine absagen
            future = serie.appointments.filter(
                Appointment.start_time >= datetime.now(),
                Appointment.status == 'scheduled'
            ).all()
            for apt in future:
                apt.status = 'cancelled'
                apt.cancellation_reason = 'Serie abgebrochen'
            db.session.commit()
            return {'message': f'Serie für {serie.patient.full_name} abgebrochen, {len(future)} Termine abgesagt'}
        else:
            db.session.commit()
            return {'message': f'Serie für {serie.patient.full_name} abgeschlossen'}

    elif tool_name == 'behandlungsplan_anzeigen':
        serie = TreatmentSeries.query.get(tool_input['serie_id'])
        if not serie:
            return {'error': 'Serie nicht gefunden'}

        ziele = serie.goals.order_by(TreatmentGoal.created_at).all()
        messungen = serie.measurements.order_by(TreatmentMeasurement.measured_at.desc()).limit(20).all()
        termine = serie.appointments.filter(Appointment.status != 'cancelled').order_by(Appointment.start_time).all()

        # Timeline erstellen
        timeline = []
        for t in termine:
            entry = {
                'datum': t.start_time.strftime('%d.%m.%Y'),
                'typ': 'termin',
                'beschreibung': f'Termin {t.start_time.strftime("%H:%M")} ({t.status})',
            }
            # Messungen zu diesem Termin
            t_messungen = [m for m in messungen if m.appointment_id == t.id]
            if t_messungen:
                entry['messungen'] = [{
                    'label': m.label, 'wert': m.value or f'L:{m.value_pair_left}/R:{m.value_pair_right}',
                    'einheit': m.unit or '',
                } for m in t_messungen]
            timeline.append(entry)

        return {
            'serie': {
                'id': serie.id,
                'patient': serie.patient.full_name,
                'diagnose': serie.diagnosis or '-',
                'phase': TreatmentSeries.PHASE_NAMES.get(serie.healing_phase, serie.healing_phase),
                'fortschritt': f'{serie.num_completed}/{serie.num_total}',
            },
            'ziele': [{
                'titel': z.title, 'status': z.status,
                'zielwert': z.target_value or '', 'aktuell': z.current_value or '',
                'phase': z.phase,
            } for z in ziele],
            'letzte_messungen': [{
                'datum': m.measured_at.strftime('%d.%m.%Y'),
                'label': m.label,
                'wert': m.value or f'L:{m.value_pair_left}/R:{m.value_pair_right}',
                'einheit': m.unit or '',
            } for m in messungen[:10]],
            'timeline': timeline,
        }

    elif tool_name == 'templates_auflisten':
        templates = TreatmentSeriesTemplate.query.order_by(TreatmentSeriesTemplate.name).all()
        return {
            'message': f'{len(templates)} Templates verfügbar',
            'templates': [{
                'id': t.id, 'name': t.name, 'tarif': t.tariff_type,
                'termine': t.num_appointments, 'dauer': t.duration_minutes,
                'mindestabstand': t.min_interval_days,
                'gruppentherapie': t.group_therapy,
            } for t in templates]
        }

    return {'error': f'Unbekanntes Tool: {tool_name}'}


def create_patienten_agent():
    """Erstellt eine Instanz des Patienten-Agenten."""
    return BaseAgent(
        name='patienten_agent',
        system_prompt=SYSTEM_PROMPT,
        tools=TOOLS,
        tool_executor=execute_tool,
    )
