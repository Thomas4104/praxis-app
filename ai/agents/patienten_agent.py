# Patienten-Agent: Spezialist für Patientendaten, Behandlungsserien, Befunde

from datetime import datetime, date
from sqlalchemy import or_
from models import db, Patient, TreatmentSeries, Appointment, Employee
from ai.base_agent import BaseAgent

SYSTEM_PROMPT = """Du bist der Patienten-Spezialist der OMNIA Praxissoftware. Du verwaltest alle Patientendaten, Behandlungsserien und Befunde.

Du achtest auf Vollständigkeit der Daten und weist auf fehlende Pflichtfelder hin (Versicherungsnummer, Arzt-Zuweisung, etc.).

Regeln:
- Antworte immer auf Deutsch, kurz und professionell
- Nenne bei Patienten immer den vollständigen Namen
- Bei der Suche: zeige die wichtigsten Daten (Name, Geburtsdatum, Telefon)
- Weise auf fehlende Daten hin (z.B. fehlende Versicherungsnummer)
- Datenschutz beachten: Nur relevante Daten anzeigen"""

TOOLS = [
    {
        "name": "patient_suchen",
        "description": "Sucht Patienten nach Name, Geburtsdatum oder Telefonnummer. Gibt eine Liste passender Patienten zurück.",
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
                "patient_id": {"type": "integer", "description": "ID des Patienten"},
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
                "patient_id": {"type": "integer", "description": "ID des Patienten"},
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
]


def execute_tool(tool_name, tool_input):
    """Führt ein Patienten-Tool aus."""

    if tool_name == 'patient_suchen':
        suchbegriff = tool_input['suchbegriff'].strip()

        # Nach Geburtsdatum suchen
        try:
            geb_datum = datetime.strptime(suchbegriff, '%Y-%m-%d').date()
            patienten = Patient.query.filter_by(date_of_birth=geb_datum, is_active=True).all()
        except ValueError:
            # Nach Name oder Telefon suchen
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

        result = []
        for p in patienten[:20]:
            result.append({
                'id': p.id,
                'name': p.full_name,
                'geburtsdatum': p.date_of_birth.strftime('%d.%m.%Y') if p.date_of_birth else '',
                'telefon': p.phone or p.mobile or '',
                'email': p.email or '',
            })

        return {'message': f'{len(result)} Patient(en) gefunden', 'patienten': result}

    elif tool_name == 'patient_erstellen':
        # Organisation des aktuellen Benutzers ermitteln
        from flask_login import current_user
        org_id = 1  # Fallback
        if current_user and current_user.is_authenticated and current_user.employee:
            org_id = current_user.employee.organization_id

        patient = Patient(
            organization_id=org_id,
            first_name=tool_input['vorname'],
            last_name=tool_input['nachname'],
        )

        if tool_input.get('geburtsdatum'):
            patient.date_of_birth = datetime.strptime(tool_input['geburtsdatum'], '%Y-%m-%d').date()
        if tool_input.get('geschlecht'):
            patient.gender = tool_input['geschlecht']
        if tool_input.get('telefon'):
            patient.phone = tool_input['telefon']
        if tool_input.get('mobile'):
            patient.mobile = tool_input['mobile']
        if tool_input.get('email'):
            patient.email = tool_input['email']
        if tool_input.get('adresse'):
            patient.address = tool_input['adresse']
        if tool_input.get('versicherungsnummer'):
            patient.insurance_number = tool_input['versicherungsnummer']
        if tool_input.get('ahv_nummer'):
            patient.ahv_number = tool_input['ahv_nummer']

        db.session.add(patient)
        db.session.commit()

        fehlende = []
        if not patient.date_of_birth:
            fehlende.append('Geburtsdatum')
        if not patient.insurance_number:
            fehlende.append('Versicherungsnummer')
        if not patient.phone and not patient.mobile:
            fehlende.append('Telefonnummer')

        msg = f'Patient erstellt: {patient.full_name} (ID: {patient.id})'
        if fehlende:
            msg += f'\n⚠️ Fehlende Daten: {", ".join(fehlende)}'

        return {'message': msg, 'patient_id': patient.id}

    elif tool_name == 'patient_bearbeiten':
        patient = Patient.query.get(tool_input['patient_id'])
        if not patient:
            return {'error': 'Patient nicht gefunden'}

        aenderungen = []
        for feld, attr in [
            ('vorname', 'first_name'), ('nachname', 'last_name'),
            ('telefon', 'phone'), ('mobile', 'mobile'),
            ('email', 'email'), ('adresse', 'address'),
            ('versicherungsnummer', 'insurance_number'),
            ('ahv_nummer', 'ahv_number'), ('notizen', 'notes'),
        ]:
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

        # Zukünftige Termine
        termine = Appointment.query.filter(
            Appointment.patient_id == patient.id,
            Appointment.start_time >= datetime.now(),
            Appointment.status != 'cancelled'
        ).order_by(Appointment.start_time).limit(10).all()

        # Aktive Serien
        serien = TreatmentSeries.query.filter_by(
            patient_id=patient.id, status='active'
        ).all()

        return {
            'patient': {
                'id': patient.id,
                'name': patient.full_name,
                'geburtsdatum': patient.date_of_birth.strftime('%d.%m.%Y') if patient.date_of_birth else '',
                'alter': patient.age,
                'geschlecht': patient.gender or '',
                'telefon': patient.phone or '',
                'mobile': patient.mobile or '',
                'email': patient.email or '',
                'adresse': patient.address or '',
                'versicherungsnummer': patient.insurance_number or '',
                'ahv_nummer': patient.ahv_number or '',
                'notizen': patient.notes or '',
                'blacklisted': patient.blacklisted,
            },
            'naechste_termine': [{
                'id': t.id,
                'datum': t.start_time.strftime('%d.%m.%Y %H:%M'),
                'therapeut': t.employee.display_name,
            } for t in termine],
            'aktive_serien': [{
                'id': s.id,
                'diagnose': s.diagnosis or '',
                'therapeut': s.therapist.display_name if s.therapist else '',
            } for s in serien],
        }

    elif tool_name == 'patienten_auflisten':
        limit = tool_input.get('limit', 20)
        patienten = Patient.query.filter_by(is_active=True).order_by(
            Patient.last_name, Patient.first_name
        ).limit(limit).all()

        return {
            'message': f'{len(patienten)} Patienten',
            'patienten': [{
                'id': p.id,
                'name': p.full_name,
                'geburtsdatum': p.date_of_birth.strftime('%d.%m.%Y') if p.date_of_birth else '',
                'telefon': p.phone or p.mobile or '',
            } for p in patienten]
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
