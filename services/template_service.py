"""
Mehrsprachiges E-Mail/SMS Template-System nach Cenplex-Vorbild.
Unterstuetzt Platzhalter, automatische Trigger und 4 Sprachen.
"""
import json
from datetime import datetime
from models import db, Patient, Employee, Appointment, TreatmentSeries, Invoice


# Sprach-Mapping (Cenplex: 0=DE, 1=FR, 2=IT, 3=EN)
LANGUAGES = {0: 'de', 1: 'fr', 2: 'it', 3: 'en'}
LANGUAGE_LABELS = {0: 'Deutsch', 1: 'Franzoesisch', 2: 'Italienisch', 3: 'Englisch'}


# Template-Quellen (Cenplex: EmailTemplateSourceTypes)
TEMPLATE_SOURCES = {
    'appointment_reminder': 'Termin-Erinnerung',
    'appointment_confirmation': 'Terminbestaetigung',
    'appointment_cancellation': 'Terminabsage',
    'invoice_send': 'Rechnungsversand',
    'invoice_reminder': 'Zahlungserinnerung',
    'kostengutsprache': 'Kostengutsprache',
    'doctor_report': 'Arztbericht',
    'series_completion': 'Serienabschluss',
    'birthday': 'Geburtstagsgruss',
    'welcome': 'Willkommen',
    'custom': 'Benutzerdefiniert'
}


# Standard-Platzhalter (Cenplex: EmailContentItems)
PLACEHOLDERS = {
    # Patient
    '%PatientVorname%': 'Vorname des Patienten',
    '%PatientNachname%': 'Nachname des Patienten',
    '%PatientAnrede%': 'Anrede des Patienten',
    '%PatientGeburtsdatum%': 'Geburtsdatum',
    '%PatientEmail%': 'E-Mail des Patienten',
    '%PatientTelefon%': 'Telefon des Patienten',
    # Termin
    '%TerminDatum%': 'Datum des Termins',
    '%TerminZeit%': 'Uhrzeit des Termins',
    '%TerminEnde%': 'Ende des Termins',
    '%TerminDauer%': 'Dauer in Minuten',
    '%TerminTyp%': 'Termintyp',
    '%Termine%': 'Alle Termine (mehrzeilig)',
    # Therapeut
    '%TherapeutVorname%': 'Vorname des Therapeuten',
    '%TherapeutNachname%': 'Nachname des Therapeuten',
    '%TherapeutTitel%': 'Titel/Grad des Therapeuten',
    # Praxis
    '%PraxisName%': 'Name der Praxis',
    '%PraxisAdresse%': 'Adresse der Praxis',
    '%PraxisTelefon%': 'Telefon der Praxis',
    '%PraxisEmail%': 'E-Mail der Praxis',
    # Rechnung
    '%RechnungNummer%': 'Rechnungsnummer',
    '%RechnungBetrag%': 'Rechnungsbetrag',
    '%RechnungFaellig%': 'Faelligkeitsdatum',
    # Serie
    '%SerieTitel%': 'Serientitel',
    '%SerieDiagnose%': 'Diagnose',
}


def resolve_placeholders(template_text, context):
    """
    Ersetzt Platzhalter im Template-Text mit tatsaechlichen Werten.

    context: dict mit patient_id, appointment_id, employee_id, invoice_id, series_id, organization
    """
    if not template_text:
        return template_text

    result = template_text

    # Patient-Daten
    patient = None
    if context.get('patient_id'):
        patient = Patient.query.get(context['patient_id'])
    if patient:
        result = result.replace('%PatientVorname%', patient.first_name or '')
        result = result.replace('%PatientNachname%', patient.last_name or '')
        result = result.replace('%PatientAnrede%', patient.salutation or '')
        result = result.replace('%PatientGeburtsdatum%', patient.date_of_birth.strftime('%d.%m.%Y') if patient.date_of_birth else '')
        result = result.replace('%PatientEmail%', patient.email or '')
        result = result.replace('%PatientTelefon%', patient.phone or patient.mobile or '')

    # Therapeut-Daten
    employee = None
    if context.get('employee_id'):
        employee = Employee.query.get(context['employee_id'])
    if employee and employee.user:
        result = result.replace('%TherapeutVorname%', employee.user.first_name or '')
        result = result.replace('%TherapeutNachname%', employee.user.last_name or '')
        result = result.replace('%TherapeutTitel%', employee.degree or '')

    # Termin-Daten
    appointment = None
    if context.get('appointment_id'):
        appointment = Appointment.query.get(context['appointment_id'])
    if appointment:
        result = result.replace('%TerminDatum%', appointment.start_time.strftime('%d.%m.%Y') if appointment.start_time else '')
        result = result.replace('%TerminZeit%', appointment.start_time.strftime('%H:%M') if appointment.start_time else '')
        result = result.replace('%TerminEnde%', appointment.end_time.strftime('%H:%M') if appointment.end_time else '')
        result = result.replace('%TerminDauer%', str(appointment.duration_minutes or 30))
        result = result.replace('%TerminTyp%', appointment.appointment_type or '')

    # Alle Termine einer Serie (fuer Serienmail)
    if context.get('series_id') and '%Termine%' in result:
        appointments = Appointment.query.filter_by(
            series_id=context['series_id']
        ).filter(
            Appointment.status.notin_(['cancelled', 'deleted']),
            Appointment.start_time >= datetime.now()
        ).order_by(Appointment.start_time).all()

        lines = []
        for appt in appointments:
            line = f"{appt.start_time.strftime('%a %d.%m.%Y %H:%M')}"
            if appt.end_time:
                line += f" - {appt.end_time.strftime('%H:%M')}"
            if appt.employee and appt.employee.user:
                line += f" ({appt.employee.user.first_name} {appt.employee.user.last_name})"
            lines.append(line)
        result = result.replace('%Termine%', '\n'.join(lines))

    # Rechnungs-Daten
    invoice = None
    if context.get('invoice_id'):
        invoice = Invoice.query.get(context['invoice_id'])
    if invoice:
        result = result.replace('%RechnungNummer%', invoice.invoice_number or '')
        result = result.replace('%RechnungBetrag%', f"CHF {float(invoice.amount_total or 0):.2f}")
        result = result.replace('%RechnungFaellig%', invoice.due_date.strftime('%d.%m.%Y') if invoice.due_date else '')

    # Serien-Daten
    series = None
    if context.get('series_id'):
        series = TreatmentSeries.query.get(context['series_id'])
    if series:
        result = result.replace('%SerieTitel%', series.title or '')
        result = result.replace('%SerieDiagnose%', series.diagnosis_text or '')

    # Praxis-Daten
    org = context.get('organization')
    if org:
        result = result.replace('%PraxisName%', org.name or '')
        result = result.replace('%PraxisAdresse%', f"{org.address or ''}, {org.zip_code or ''} {org.city or ''}")
        result = result.replace('%PraxisTelefon%', org.phone or '')
        result = result.replace('%PraxisEmail%', org.email or '')

    return result


def get_template_content(template, language=0):
    """
    Laedt Template-Inhalt fuer eine bestimmte Sprache.
    template: EmailTemplate Objekt
    language: 0=DE, 1=FR, 2=IT, 3=EN
    """
    if not template or not template.content_json:
        return {'subject': '', 'message': '', 'appointment_line': ''}

    try:
        contents = json.loads(template.content_json)
        if isinstance(contents, list):
            for content in contents:
                if content.get('language') == language:
                    return content
            # Fallback auf Deutsch
            for content in contents:
                if content.get('language') == 0:
                    return content
            return contents[0] if contents else {'subject': '', 'message': '', 'appointment_line': ''}
        return contents
    except (json.JSONDecodeError, TypeError):
        return {'subject': '', 'message': '', 'appointment_line': ''}


def save_template_content(template, language, subject, message, appointment_line=''):
    """Speichert Template-Inhalt fuer eine Sprache"""
    try:
        contents = json.loads(template.content_json) if template.content_json else []
    except (json.JSONDecodeError, TypeError):
        contents = []

    if not isinstance(contents, list):
        contents = []

    # Bestehenden Eintrag aktualisieren oder neuen hinzufuegen
    found = False
    for content in contents:
        if content.get('language') == language:
            content['subject'] = subject
            content['message'] = message
            content['appointment_line'] = appointment_line
            found = True
            break

    if not found:
        contents.append({
            'language': language,
            'subject': subject,
            'message': message,
            'appointment_line': appointment_line
        })

    template.content_json = json.dumps(contents, ensure_ascii=False)
    db.session.commit()


def get_sms_clean_text(text):
    """Bereinigt Text fuer SMS (GSM-7 Zeichensatz, Cenplex: SmsCharacterChecker)"""
    if not text:
        return ''

    # GSM-7 erlaubte Zeichen
    gsm_chars = set(
        '@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ !"#¤%&\'()*+,-./0123456789:;<=>?'
        '¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜabcdefghijklmnopqrstuvwxyzäöñüà'
    )

    # Umlaute und Sonderzeichen ersetzen
    replacements = {
        'ë': 'e', 'ê': 'e', 'î': 'i', 'ï': 'i', 'ô': 'o', 'û': 'u',
        'ç': 'c', 'â': 'a', '\u2014': '-', '\u2013': '-', '\u201c': '"', '\u201d': '"',
        '\u2018': "'", '\u2019': "'", '\u2026': '...', '\u2022': '-'
    }

    result = []
    for char in text:
        if char in gsm_chars:
            result.append(char)
        elif char in replacements:
            result.append(replacements[char])
        else:
            result.append('?')

    return ''.join(result)
