"""KI-Tools fuer den Kommunikations-Bereich (E-Mail und Mailing)"""
import json
from datetime import datetime
from models import (db, Email, EmailTemplate, EmailFolder, Patient,
                     Organization, SystemSetting, Appointment, TreatmentSeries, Invoice)


MAILING_TOOLS = [
    {
        'name': 'email_senden',
        'description': 'Sendet eine E-Mail (Demo-Modus: wird gespeichert aber nicht versendet). Kann an Patienten, Aerzte oder Versicherungen gesendet werden.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'empfaenger': {'type': 'string', 'description': 'E-Mail-Adresse des Empfaengers'},
                'betreff': {'type': 'string', 'description': 'Betreff der E-Mail'},
                'text': {'type': 'string', 'description': 'Text der E-Mail (HTML erlaubt)'},
                'patient_id': {'type': 'integer', 'description': 'ID des verknuepften Patienten (optional)'}
            },
            'required': ['empfaenger', 'betreff', 'text']
        }
    },
    {
        'name': 'email_entwurf_erstellen',
        'description': 'Erstellt einen E-Mail-Entwurf, der spaeter bearbeitet und gesendet werden kann.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'empfaenger': {'type': 'string', 'description': 'E-Mail-Adresse des Empfaengers (optional)'},
                'betreff': {'type': 'string', 'description': 'Betreff der E-Mail'},
                'text': {'type': 'string', 'description': 'Text der E-Mail (HTML erlaubt)'}
            },
            'required': ['betreff', 'text']
        }
    },
    {
        'name': 'emails_auflisten',
        'description': 'Listet E-Mails auf, optional gefiltert nach Ordner und Suchbegriff.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'ordner': {'type': 'string', 'description': 'Ordner: inbox, drafts, sent, archive, trash. Standard: inbox'},
                'suchbegriff': {'type': 'string', 'description': 'Suchbegriff fuer Betreff, Absender oder Empfaenger'},
                'limit': {'type': 'integer', 'description': 'Maximale Anzahl (Standard: 10)'}
            },
            'required': []
        }
    },
    {
        'name': 'email_details',
        'description': 'Zeigt Details einer E-Mail an: Absender, Empfaenger, Betreff, Text, Verknuepfungen.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'email_id': {'type': 'integer', 'description': 'ID der E-Mail'}
            },
            'required': ['email_id']
        }
    },
    {
        'name': 'ungelesene_emails',
        'description': 'Zeigt die Anzahl ungelesener E-Mails im Posteingang an.',
        'input_schema': {
            'type': 'object',
            'properties': {},
            'required': []
        }
    },
    {
        'name': 'email_an_patient',
        'description': 'Erstellt eine E-Mail an einen Patienten mit einer passenden Vorlage. Platzhalter werden automatisch ersetzt.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'patient_id': {'type': 'integer', 'description': 'ID des Patienten'},
                'vorlage_typ': {'type': 'string', 'description': 'Typ der Vorlage: reminder, confirmation, cancellation, recall, welcome'}
            },
            'required': ['patient_id', 'vorlage_typ']
        }
    },
    {
        'name': 'email_vorlagen_auflisten',
        'description': 'Listet alle verfuegbaren E-Mail-Vorlagen auf.',
        'input_schema': {
            'type': 'object',
            'properties': {},
            'required': []
        }
    }
]


def _get_org_id():
    """Ermittelt die Organisation-ID des aktuellen Benutzers"""
    from flask_login import current_user
    return current_user.organization_id


def _get_sender_address(org_id):
    """Ermittelt die konfigurierte Absender-Adresse"""
    setting = SystemSetting.query.filter_by(organization_id=org_id, key='email_sender_address').first()
    if setting:
        return setting.value
    org = Organization.query.get(org_id)
    return org.email if org else 'info@omnia-health.ch'


def _replace_placeholders(text, patient, org, series_id=None, invoice_id=None):
    """Ersetzt Platzhalter in einem Text"""
    replacements = {
        '{patient_name}': f'{patient.first_name} {patient.last_name}' if patient else '',
        '{patient_vorname}': patient.first_name if patient else '',
        '{patient_nachname}': patient.last_name if patient else '',
        '{praxis_name}': org.name if org else '',
        '{praxis_telefon}': org.phone if org else '',
        '{praxis_email}': org.email if org else '',
        '{datum}': datetime.now().strftime('%d.%m.%Y'),
    }

    if patient:
        next_appt = Appointment.query.filter(
            Appointment.patient_id == patient.id,
            Appointment.start_time >= datetime.now(),
            Appointment.status.in_(['scheduled', 'confirmed'])
        ).order_by(Appointment.start_time).first()
        if next_appt:
            replacements['{termin_datum}'] = next_appt.start_time.strftime('%d.%m.%Y')
            replacements['{termin_zeit}'] = next_appt.start_time.strftime('%H:%M')

    if series_id:
        series = TreatmentSeries.query.get(series_id)
        if series:
            replacements['{serie_name}'] = series.diagnosis or ''

    if invoice_id:
        invoice = Invoice.query.get(invoice_id)
        if invoice:
            replacements['{rechnungs_nummer}'] = invoice.invoice_number or ''
            replacements['{rechnungs_betrag}'] = f'CHF {invoice.total_amount:.2f}' if invoice.total_amount else ''

    for key, val in replacements.items():
        text = text.replace(key, val)

    return text


def mailing_tool_executor(tool_name, tool_input):
    """Fuehrt ein Mailing-Tool aus und gibt das Ergebnis zurueck"""
    org_id = _get_org_id()

    if tool_name == 'email_senden':
        empfaenger = tool_input.get('empfaenger')
        betreff = tool_input.get('betreff')
        text = tool_input.get('text')
        patient_id = tool_input.get('patient_id')

        email = Email(
            organization_id=org_id,
            from_address=_get_sender_address(org_id),
            to_address=empfaenger,
            subject=betreff,
            body_html=text,
            body_text=text,
            status='sent',
            folder='sent',
            linked_patient_id=patient_id,
            sent_at=datetime.utcnow()
        )
        db.session.add(email)
        db.session.commit()

        return {
            'erfolg': True,
            'nachricht': f'E-Mail an {empfaenger} wurde gespeichert (Demo-Modus, nicht versendet).',
            'email_id': email.id
        }

    elif tool_name == 'email_entwurf_erstellen':
        empfaenger = tool_input.get('empfaenger', '')
        betreff = tool_input.get('betreff')
        text = tool_input.get('text')

        email = Email(
            organization_id=org_id,
            to_address=empfaenger,
            subject=betreff,
            body_html=text,
            body_text=text,
            status='draft',
            folder='drafts'
        )
        db.session.add(email)
        db.session.commit()

        return {
            'erfolg': True,
            'nachricht': f'Entwurf "{betreff}" wurde gespeichert.',
            'email_id': email.id
        }

    elif tool_name == 'emails_auflisten':
        ordner = tool_input.get('ordner', 'inbox')
        suchbegriff = tool_input.get('suchbegriff', '')
        limit = tool_input.get('limit', 10)

        query = Email.query.filter_by(organization_id=org_id, folder=ordner)

        if suchbegriff:
            query = query.filter(
                db.or_(
                    Email.subject.ilike(f'%{suchbegriff}%'),
                    Email.from_address.ilike(f'%{suchbegriff}%'),
                    Email.to_address.ilike(f'%{suchbegriff}%')
                )
            )

        emails = query.order_by(Email.created_at.desc()).limit(limit).all()

        return {
            'anzahl': len(emails),
            'ordner': ordner,
            'emails': [{
                'id': e.id,
                'von': e.from_address,
                'an': e.to_address,
                'betreff': e.subject,
                'datum': e.created_at.strftime('%d.%m.%Y %H:%M'),
                'gelesen': e.read_at is not None,
                'status': e.status
            } for e in emails]
        }

    elif tool_name == 'email_details':
        email_id = tool_input.get('email_id')
        email = Email.query.get(email_id)

        if not email or email.organization_id != org_id:
            return {'fehler': f'E-Mail mit ID {email_id} nicht gefunden.'}

        result = {
            'id': email.id,
            'von': email.from_address,
            'an': email.to_address,
            'cc': email.cc,
            'betreff': email.subject,
            'text': email.body_text or '',
            'datum': email.created_at.strftime('%d.%m.%Y %H:%M'),
            'status': email.status,
            'ordner': email.folder,
            'gelesen': email.read_at is not None
        }

        if email.linked_patient_id:
            patient = Patient.query.get(email.linked_patient_id)
            if patient:
                result['patient'] = f'{patient.first_name} {patient.last_name}'

        return result

    elif tool_name == 'ungelesene_emails':
        count = Email.query.filter_by(
            organization_id=org_id, folder='inbox'
        ).filter(Email.read_at.is_(None)).count()

        return {
            'anzahl_ungelesen': count,
            'nachricht': f'Sie haben {count} ungelesene E-Mail(s) im Posteingang.'
        }

    elif tool_name == 'email_an_patient':
        patient_id = tool_input.get('patient_id')
        vorlage_typ = tool_input.get('vorlage_typ')

        patient = Patient.query.get(patient_id)
        if not patient:
            return {'fehler': f'Patient mit ID {patient_id} nicht gefunden.'}

        if not patient.email:
            return {'fehler': f'Patient {patient.first_name} {patient.last_name} hat keine E-Mail-Adresse hinterlegt.'}

        template = EmailTemplate.query.filter_by(
            organization_id=org_id,
            template_type=vorlage_typ,
            is_active=True
        ).first()

        if not template:
            return {'fehler': f'Keine aktive Vorlage vom Typ "{vorlage_typ}" gefunden.'}

        org = Organization.query.get(org_id)
        subject = _replace_placeholders(template.subject or '', patient, org)
        body = _replace_placeholders(template.body_html or '', patient, org)

        email = Email(
            organization_id=org_id,
            from_address=_get_sender_address(org_id),
            to_address=patient.email,
            subject=subject,
            body_html=body,
            body_text=body,
            status='sent',
            folder='sent',
            linked_patient_id=patient_id,
            sent_at=datetime.utcnow()
        )
        db.session.add(email)
        db.session.commit()

        return {
            'erfolg': True,
            'nachricht': f'E-Mail "{subject}" an {patient.first_name} {patient.last_name} ({patient.email}) wurde gespeichert (Demo-Modus).',
            'email_id': email.id
        }

    elif tool_name == 'email_vorlagen_auflisten':
        templates = EmailTemplate.query.filter_by(
            organization_id=org_id,
            is_active=True
        ).order_by(EmailTemplate.name).all()

        return {
            'anzahl': len(templates),
            'vorlagen': [{
                'id': t.id,
                'name': t.name,
                'typ': t.template_type,
                'betreff': t.subject
            } for t in templates]
        }

    return {'fehler': f'Unbekanntes Tool: {tool_name}'}
