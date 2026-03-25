"""
Service fuer die automatische Generierung von Arztberichten.
Sammelt SOAP-Notes, Diagnosen, Therapieziele und Messungen aus einer Behandlungsserie.
"""
import json
from datetime import datetime
from models import db, TreatmentSeries, Appointment, TherapyGoal, Measurement, Patient


def generate_report_data(series_id):
    """Sammelt alle Daten fuer einen Arztbericht.

    Returns:
        tuple: (dict mit Berichtsdaten, None) oder (None, Fehlermeldung)
    """
    series = TreatmentSeries.query.get(series_id)
    if not series:
        return None, 'Serie nicht gefunden'

    patient = series.patient

    # Alle Termine der Serie
    appointments = Appointment.query.filter_by(
        series_id=series_id
    ).order_by(Appointment.start_time).all()

    # Therapieziele
    goals = TherapyGoal.query.filter_by(patient_id=patient.id).all()

    # Messungen (letzte 20)
    measurements = Measurement.query.filter_by(patient_id=patient.id).order_by(
        Measurement.measured_at.desc()
    ).limit(20).all()

    # SOAP-Zusammenfassung (letzter Termin mit SOAP)
    last_soap = None
    for appt in reversed(appointments):
        if appt.soap_subjective or appt.soap_objective or appt.soap_assessment or appt.soap_plan:
            last_soap = {
                'date': appt.start_time.strftime('%d.%m.%Y') if appt.start_time else '',
                'subjective': appt.soap_subjective or '',
                'objective': appt.soap_objective or '',
                'assessment': appt.soap_assessment or '',
                'plan': appt.soap_plan or '',
            }
            break

    # Zuweisender Arzt
    doctor = series.prescribing_doctor

    report_data = {
        'patient': {
            'name': f'{patient.first_name} {patient.last_name}',
            'date_of_birth': patient.date_of_birth.strftime('%d.%m.%Y') if patient.date_of_birth else '',
            'patient_number': patient.patient_number or '',
        },
        'series': {
            'diagnosis_code': series.diagnosis_code or '',
            'diagnosis_text': series.diagnosis_text or '',
            'insurance_type': series.insurance_type or '',
            'prescription_date': series.prescription_date.strftime('%d.%m.%Y') if hasattr(series, 'prescription_date') and series.prescription_date else '',
            'status': series.status,
            'total_appointments': len(appointments),
            'completed_appointments': len([a for a in appointments if a.status in ('completed', 'appeared')]),
        },
        'doctor': {
            'name': f'{doctor.salutation or ""} {doctor.first_name} {doctor.last_name}'.strip() if doctor else '',
            'specialty': doctor.specialty if doctor else '',
        } if doctor else None,
        'goals': [{
            'description': g.description,
            'status': g.status,
            'achievement_percent': g.achievement_percent or 0,
        } for g in goals],
        'measurements': [{
            'type': m.measurement_type,
            'name': m.name or m.measurement_type.upper(),
            'values': json.loads(m.value_json) if m.value_json else {},
            'unit': m.unit or '',
            'date': m.measured_at.strftime('%d.%m.%Y') if m.measured_at else '',
        } for m in measurements],
        'last_soap': last_soap,
        'appointment_summary': [{
            'date': a.start_time.strftime('%d.%m.%Y') if a.start_time else '',
            'status': a.status,
            'duration': a.duration_minutes,
            'therapist': f'{a.employee.user.first_name} {a.employee.user.last_name}' if a.employee and a.employee.user else '',
        } for a in appointments],
        'generated_at': datetime.utcnow().strftime('%d.%m.%Y %H:%M'),
    }

    return report_data, None


def generate_report_pdf(series_id):
    """Generiert einen Arztbericht als PDF.

    Returns:
        tuple: (Pfad zur PDF-Datei, None) oder (None, Fehlermeldung)
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors
    import os

    data, error = generate_report_data(series_id)
    if error:
        return None, error

    # PDF erstellen
    series = TreatmentSeries.query.get(series_id)
    upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads', 'reports')
    os.makedirs(upload_dir, exist_ok=True)

    filename = f'arztbericht_{series_id}_{datetime.utcnow().strftime("%Y%m%d%H%M%S")}.pdf'
    filepath = os.path.join(upload_dir, filename)

    doc = SimpleDocTemplate(filepath, pagesize=A4,
                           leftMargin=2*cm, rightMargin=2*cm,
                           topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    elements = []

    # Titel
    elements.append(Paragraph('Arztbericht', styles['Title']))
    elements.append(Spacer(1, 0.5*cm))

    # Patientendaten
    elements.append(Paragraph(f"<b>Patient:</b> {data['patient']['name']}", styles['Normal']))
    elements.append(Paragraph(f"<b>Geburtsdatum:</b> {data['patient']['date_of_birth']}", styles['Normal']))
    elements.append(Paragraph(f"<b>Patienten-Nr.:</b> {data['patient']['patient_number']}", styles['Normal']))
    elements.append(Spacer(1, 0.3*cm))

    # Zuweisender Arzt
    if data['doctor']:
        elements.append(Paragraph(f"<b>Zuweisender Arzt:</b> {data['doctor']['name']}", styles['Normal']))
        if data['doctor']['specialty']:
            elements.append(Paragraph(f"<b>Fachgebiet:</b> {data['doctor']['specialty']}", styles['Normal']))
        elements.append(Spacer(1, 0.3*cm))

    # Diagnose
    elements.append(Paragraph('<b>Diagnose</b>', styles['Heading2']))
    elements.append(Paragraph(f"{data['series']['diagnosis_code']} {data['series']['diagnosis_text']}", styles['Normal']))
    elements.append(Spacer(1, 0.3*cm))

    # Behandlungsverlauf
    elements.append(Paragraph('<b>Behandlungsverlauf</b>', styles['Heading2']))
    verordnung_text = f"Verordnung vom {data['series']['prescription_date']}, " if data['series']['prescription_date'] else ''
    elements.append(Paragraph(
        f"{verordnung_text}"
        f"Versicherungstyp: {data['series']['insurance_type']}, "
        f"{data['series']['completed_appointments']}/{data['series']['total_appointments']} Termine durchgefuehrt.",
        styles['Normal']
    ))
    elements.append(Spacer(1, 0.3*cm))

    # Aktueller Befund (letzter SOAP)
    if data['last_soap']:
        elements.append(Paragraph('<b>Aktueller Befund</b>', styles['Heading2']))
        elements.append(Paragraph(f"<b>Datum:</b> {data['last_soap']['date']}", styles['Normal']))
        elements.append(Paragraph(f"<b>S:</b> {data['last_soap']['subjective']}", styles['Normal']))
        elements.append(Paragraph(f"<b>O:</b> {data['last_soap']['objective']}", styles['Normal']))
        elements.append(Paragraph(f"<b>A:</b> {data['last_soap']['assessment']}", styles['Normal']))
        elements.append(Paragraph(f"<b>P:</b> {data['last_soap']['plan']}", styles['Normal']))
        elements.append(Spacer(1, 0.3*cm))

    # Therapieziele
    if data['goals']:
        elements.append(Paragraph('<b>Therapieziele</b>', styles['Heading2']))
        status_labels = {'open': 'Offen', 'in_progress': 'In Bearbeitung', 'achieved': 'Erreicht'}
        for goal in data['goals']:
            status_text = status_labels.get(goal['status'], goal['status'])
            elements.append(Paragraph(
                f"- {goal['description']} (Status: {status_text}, Erreichung: {goal['achievement_percent']}%)",
                styles['Normal']
            ))
        elements.append(Spacer(1, 0.3*cm))

    # Messungen
    if data['measurements']:
        elements.append(Paragraph('<b>Messungen</b>', styles['Heading2']))
        for m in data['measurements'][:10]:
            wert_str = str(m['values']) if m['values'] else '-'
            elements.append(Paragraph(
                f"- {m['name']} ({m['date']}): {wert_str} {m['unit']}",
                styles['Normal']
            ))
        elements.append(Spacer(1, 0.3*cm))

    # Fusszeile
    elements.append(Spacer(1, 1*cm))
    elements.append(Paragraph(f"Erstellt am {data['generated_at']}", styles['Normal']))

    doc.build(elements)
    return filepath, None
