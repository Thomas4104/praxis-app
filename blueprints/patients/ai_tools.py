"""KI-Tools fuer den Patienten-Bereich"""
import json
from datetime import datetime, date, timedelta
from flask_login import current_user
from models import db, Patient, InsuranceProvider, Doctor, TreatmentSeries, \
    Appointment, PatientDocument, Employee


PATIENT_TOOLS = [
    {
        'name': 'patient_suchen',
        'description': 'Sucht Patienten nach Name, Geburtsdatum, Telefon oder Patientennummer.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'suchbegriff': {
                    'type': 'string',
                    'description': 'Suchbegriff (Name, Geburtsdatum im Format TT.MM.JJJJ, Telefonnummer oder Patientennummer)'
                }
            },
            'required': ['suchbegriff']
        }
    },
    {
        'name': 'patient_erstellen',
        'description': 'Erstellt einen neuen Patienten mit den angegebenen Daten.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'vorname': {'type': 'string', 'description': 'Vorname des Patienten'},
                'nachname': {'type': 'string', 'description': 'Nachname des Patienten'},
                'geburtsdatum': {'type': 'string', 'description': 'Geburtsdatum im Format YYYY-MM-DD'},
                'geschlecht': {'type': 'string', 'description': 'maennlich, weiblich oder divers'},
                'telefon': {'type': 'string', 'description': 'Mobiltelefonnummer'},
                'email': {'type': 'string', 'description': 'E-Mail-Adresse'},
                'versicherung_id': {'type': 'integer', 'description': 'ID der Versicherung'},
                'versicherungsnummer': {'type': 'string', 'description': 'Versicherungsnummer'}
            },
            'required': ['vorname', 'nachname', 'geburtsdatum']
        }
    },
    {
        'name': 'patient_details',
        'description': 'Zeigt alle Details eines Patienten (Personalien, Versicherung, Kontakt, Termine).',
        'input_schema': {
            'type': 'object',
            'properties': {
                'patient_id': {'type': 'integer', 'description': 'ID des Patienten'}
            },
            'required': ['patient_id']
        }
    },
    {
        'name': 'patient_bearbeiten',
        'description': 'Aktualisiert bestimmte Felder eines Patienten.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'patient_id': {'type': 'integer', 'description': 'ID des Patienten'},
                'felder': {
                    'type': 'object',
                    'description': 'Zu aktualisierende Felder als Key-Value-Paare (z.B. {"telefon": "+41 79...", "email": "..."})'
                }
            },
            'required': ['patient_id', 'felder']
        }
    },
    {
        'name': 'patient_termine',
        'description': 'Zeigt alle Termine eines Patienten (vergangene und zukuenftige).',
        'input_schema': {
            'type': 'object',
            'properties': {
                'patient_id': {'type': 'integer', 'description': 'ID des Patienten'},
                'nur_zukuenftige': {'type': 'boolean', 'description': 'Nur zukuenftige Termine anzeigen (Standard: false)'}
            },
            'required': ['patient_id']
        }
    },
    {
        'name': 'patient_serien',
        'description': 'Zeigt alle Behandlungsserien eines Patienten.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'patient_id': {'type': 'integer', 'description': 'ID des Patienten'}
            },
            'required': ['patient_id']
        }
    },
    {
        'name': 'patient_deaktivieren',
        'description': 'Deaktiviert einen Patienten (Soft-Delete).',
        'input_schema': {
            'type': 'object',
            'properties': {
                'patient_id': {'type': 'integer', 'description': 'ID des Patienten'}
            },
            'required': ['patient_id']
        }
    },
    {
        'name': 'naechster_termin',
        'description': 'Zeigt den naechsten geplanten Termin eines Patienten.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'patient_id': {'type': 'integer', 'description': 'ID des Patienten'}
            },
            'required': ['patient_id']
        }
    },
    {
        'name': 'patienten_ohne_folgetermin',
        'description': 'Findet Patienten die seit X Tagen keinen Termin haben (Recall-Liste).',
        'input_schema': {
            'type': 'object',
            'properties': {
                'tage': {'type': 'integer', 'description': 'Anzahl Tage seit letztem Termin (Standard: 30)'}
            },
            'required': []
        }
    },
    {
        'name': 'geburtstage_heute',
        'description': 'Zeigt alle Patienten die heute Geburtstag haben.',
        'input_schema': {
            'type': 'object',
            'properties': {},
            'required': []
        }
    },
    {
        'name': 'arzt_suchen',
        'description': 'Sucht Aerzte nach Name oder Fachrichtung.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'suchbegriff': {'type': 'string', 'description': 'Name oder Fachrichtung'}
            },
            'required': ['suchbegriff']
        }
    },
    {
        'name': 'versicherung_suchen',
        'description': 'Sucht Versicherungen nach Name.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'name': {'type': 'string', 'description': 'Name der Versicherung'}
            },
            'required': ['name']
        }
    }
]


def patient_tool_executor(tool_name, tool_input):
    """Fuehrt Patienten-Tools aus"""
    org_id = current_user.organization_id

    if tool_name == 'patient_suchen':
        suchbegriff = tool_input.get('suchbegriff', '').strip()
        if not suchbegriff:
            return {'error': 'Bitte einen Suchbegriff angeben.'}

        # Datum-Suche
        import re
        date_match = re.match(r'^(\d{1,2})\.(\d{1,2})\.(\d{4})$', suchbegriff)
        if date_match:
            try:
                search_date = date(int(date_match.group(3)),
                                   int(date_match.group(2)),
                                   int(date_match.group(1)))
                patients = Patient.query.filter_by(
                    organization_id=org_id, date_of_birth=search_date, is_active=True
                ).all()
            except ValueError:
                patients = []
        else:
            patients = Patient.query.filter(
                Patient.organization_id == org_id,
                Patient.is_active == True,
                db.or_(
                    Patient.first_name.ilike(f'%{suchbegriff}%'),
                    Patient.last_name.ilike(f'%{suchbegriff}%'),
                    Patient.patient_number.ilike(f'%{suchbegriff}%'),
                    Patient.mobile.ilike(f'%{suchbegriff}%'),
                    Patient.phone.ilike(f'%{suchbegriff}%'),
                    (Patient.first_name + ' ' + Patient.last_name).ilike(f'%{suchbegriff}%')
                )
            ).limit(20).all()

        if not patients:
            return {'ergebnis': 'Keine Patienten gefunden.', 'anzahl': 0}

        return {
            'anzahl': len(patients),
            'patienten': [{
                'id': p.id,
                'patient_number': p.patient_number,
                'name': f'{p.first_name} {p.last_name}',
                'geburtsdatum': p.date_of_birth.strftime('%d.%m.%Y') if p.date_of_birth else None,
                'telefon': p.mobile or p.phone,
                'versicherung': p.insurance_provider.name if p.insurance_provider else None
            } for p in patients]
        }

    elif tool_name == 'patient_erstellen':
        vorname = tool_input.get('vorname', '').strip()
        nachname = tool_input.get('nachname', '').strip()
        geb_str = tool_input.get('geburtsdatum', '')

        if not vorname or not nachname:
            return {'error': 'Vorname und Nachname sind Pflichtfelder.'}

        try:
            dob = datetime.strptime(geb_str, '%Y-%m-%d').date()
        except ValueError:
            return {'error': 'Ungültiges Datumsformat. Bitte YYYY-MM-DD verwenden.'}

        # Patientennummer generieren
        last_p = Patient.query.filter_by(organization_id=org_id) \
            .order_by(Patient.id.desc()).first()
        if last_p and last_p.patient_number:
            try:
                num = int(last_p.patient_number[1:]) + 1
            except (ValueError, IndexError):
                num = Patient.query.count() + 1
        else:
            num = 1

        patient = Patient(
            organization_id=org_id,
            patient_number=f'P{num:05d}',
            first_name=vorname,
            last_name=nachname,
            date_of_birth=dob,
            gender=tool_input.get('geschlecht', ''),
            mobile=tool_input.get('telefon', ''),
            email=tool_input.get('email', ''),
            insurance_provider_id=tool_input.get('versicherung_id'),
            insurance_number=tool_input.get('versicherungsnummer', '')
        )
        db.session.add(patient)
        db.session.commit()

        return {
            'erfolg': True,
            'patient_id': patient.id,
            'patient_number': patient.patient_number,
            'nachricht': f'Patient {vorname} {nachname} ({patient.patient_number}) wurde erfolgreich erstellt.'
        }

    elif tool_name == 'patient_details':
        patient = Patient.query.get(tool_input.get('patient_id'))
        if not patient or patient.organization_id != org_id:
            return {'error': 'Patient nicht gefunden.'}

        # Alter berechnen
        age = None
        if patient.date_of_birth:
            today = date.today()
            age = today.year - patient.date_of_birth.year - (
                (today.month, today.day) < (patient.date_of_birth.month, patient.date_of_birth.day)
            )

        # Naechster Termin
        next_appt = Appointment.query.filter_by(patient_id=patient.id) \
            .filter(Appointment.start_time > datetime.now()) \
            .order_by(Appointment.start_time.asc()).first()

        # Aktive Serien
        active_series = TreatmentSeries.query.filter_by(
            patient_id=patient.id, status='active').count()

        return {
            'id': patient.id,
            'patient_number': patient.patient_number,
            'anrede': patient.salutation,
            'vorname': patient.first_name,
            'nachname': patient.last_name,
            'geburtsdatum': patient.date_of_birth.strftime('%d.%m.%Y') if patient.date_of_birth else None,
            'alter': age,
            'geschlecht': patient.gender,
            'ahv_nummer': patient.ahv_number,
            'telefon_festnetz': patient.phone,
            'mobiltelefon': patient.mobile,
            'email': patient.email,
            'adresse': f'{patient.address or ""}, {patient.zip_code or ""} {patient.city or ""}'.strip(', '),
            'versicherung': patient.insurance_provider.name if patient.insurance_provider else None,
            'versicherungsnummer': patient.insurance_number,
            'versicherungsart': patient.insurance_type,
            'bevorzugter_kontakt': patient.preferred_contact_method,
            'blacklist': patient.blacklisted,
            'blacklist_grund': patient.blacklist_reason,
            'arbeitgeber': patient.employer_name,
            'notizen': patient.notes,
            'aktive_serien': active_series,
            'naechster_termin': next_appt.start_time.strftime('%d.%m.%Y %H:%M') if next_appt else None,
            'aktiv': patient.is_active
        }

    elif tool_name == 'patient_bearbeiten':
        patient = Patient.query.get(tool_input.get('patient_id'))
        if not patient or patient.organization_id != org_id:
            return {'error': 'Patient nicht gefunden.'}

        felder = tool_input.get('felder', {})
        field_map = {
            'vorname': 'first_name', 'nachname': 'last_name',
            'telefon': 'mobile', 'telefon_festnetz': 'phone',
            'email': 'email', 'adresse': 'address', 'plz': 'zip_code',
            'ort': 'city', 'notizen': 'notes',
            'versicherungsnummer': 'insurance_number',
            'versicherungsart': 'insurance_type',
            'ahv_nummer': 'ahv_number',
            'arbeitgeber': 'employer_name'
        }

        updated = []
        for key, value in felder.items():
            db_field = field_map.get(key, key)
            if hasattr(patient, db_field):
                setattr(patient, db_field, value)
                updated.append(key)

        db.session.commit()
        return {
            'erfolg': True,
            'aktualisierte_felder': updated,
            'nachricht': f'Patient {patient.first_name} {patient.last_name} wurde aktualisiert.'
        }

    elif tool_name == 'patient_termine':
        patient = Patient.query.get(tool_input.get('patient_id'))
        if not patient or patient.organization_id != org_id:
            return {'error': 'Patient nicht gefunden.'}

        query = Appointment.query.filter_by(patient_id=patient.id)
        if tool_input.get('nur_zukuenftige'):
            query = query.filter(Appointment.start_time > datetime.now())
        termine = query.order_by(Appointment.start_time.desc()).limit(20).all()

        return {
            'patient': f'{patient.first_name} {patient.last_name}',
            'anzahl': len(termine),
            'termine': [{
                'datum': t.start_time.strftime('%d.%m.%Y'),
                'uhrzeit': f'{t.start_time.strftime("%H:%M")} - {t.end_time.strftime("%H:%M")}',
                'therapeut': f'{t.employee.user.first_name} {t.employee.user.last_name}' if t.employee and t.employee.user else None,
                'typ': t.title or t.appointment_type,
                'status': t.status
            } for t in termine]
        }

    elif tool_name == 'patient_serien':
        patient = Patient.query.get(tool_input.get('patient_id'))
        if not patient or patient.organization_id != org_id:
            return {'error': 'Patient nicht gefunden.'}

        serien = TreatmentSeries.query.filter_by(patient_id=patient.id) \
            .order_by(TreatmentSeries.created_at.desc()).all()

        return {
            'patient': f'{patient.first_name} {patient.last_name}',
            'anzahl': len(serien),
            'serien': [{
                'id': s.id,
                'vorlage': s.template.name if s.template else '-',
                'therapeut': f'{s.therapist.user.first_name} {s.therapist.user.last_name}' if s.therapist and s.therapist.user else None,
                'diagnose': f'{s.diagnosis_code}: {s.diagnosis_text}' if s.diagnosis_text else None,
                'status': s.status,
                'termine_durchgefuehrt': Appointment.query.filter_by(series_id=s.id).count(),
                'termine_gesamt': s.template.num_appointments if s.template else 0,
                'erstellt_am': s.created_at.strftime('%d.%m.%Y')
            } for s in serien]
        }

    elif tool_name == 'patient_deaktivieren':
        patient = Patient.query.get(tool_input.get('patient_id'))
        if not patient or patient.organization_id != org_id:
            return {'error': 'Patient nicht gefunden.'}

        patient.is_active = False
        db.session.commit()
        return {
            'erfolg': True,
            'nachricht': f'Patient {patient.first_name} {patient.last_name} wurde deaktiviert.'
        }

    elif tool_name == 'naechster_termin':
        patient = Patient.query.get(tool_input.get('patient_id'))
        if not patient or patient.organization_id != org_id:
            return {'error': 'Patient nicht gefunden.'}

        next_appt = Appointment.query.filter_by(patient_id=patient.id) \
            .filter(Appointment.start_time > datetime.now()) \
            .order_by(Appointment.start_time.asc()).first()

        if not next_appt:
            return {
                'patient': f'{patient.first_name} {patient.last_name}',
                'naechster_termin': None,
                'nachricht': 'Kein zukuenftiger Termin geplant.'
            }

        return {
            'patient': f'{patient.first_name} {patient.last_name}',
            'datum': next_appt.start_time.strftime('%d.%m.%Y'),
            'uhrzeit': f'{next_appt.start_time.strftime("%H:%M")} - {next_appt.end_time.strftime("%H:%M")}',
            'therapeut': f'{next_appt.employee.user.first_name} {next_appt.employee.user.last_name}' if next_appt.employee and next_appt.employee.user else None,
            'typ': next_appt.title or next_appt.appointment_type
        }

    elif tool_name == 'patienten_ohne_folgetermin':
        tage = tool_input.get('tage', 30)
        grenze = datetime.now() - timedelta(days=tage)

        # Alle aktiven Patienten mit letztem Termin vor X Tagen
        patienten_mit_termin = db.session.query(
            Patient.id,
            Patient.first_name,
            Patient.last_name,
            Patient.patient_number,
            Patient.mobile,
            db.func.max(Appointment.start_time).label('letzter_termin')
        ).join(Appointment, Patient.id == Appointment.patient_id) \
            .filter(Patient.organization_id == org_id, Patient.is_active == True) \
            .group_by(Patient.id) \
            .having(db.func.max(Appointment.start_time) < grenze) \
            .having(~db.exists(
                db.select(Appointment.id).where(
                    db.and_(
                        Appointment.patient_id == Patient.id,
                        Appointment.start_time > datetime.now()
                    )
                )
            )) \
            .all()

        return {
            'tage': tage,
            'anzahl': len(patienten_mit_termin),
            'patienten': [{
                'id': p.id,
                'patient_number': p.patient_number,
                'name': f'{p.first_name} {p.last_name}',
                'telefon': p.mobile,
                'letzter_termin': p.letzter_termin.strftime('%d.%m.%Y') if p.letzter_termin else None
            } for p in patienten_mit_termin]
        }

    elif tool_name == 'geburtstage_heute':
        today = date.today()
        patienten = Patient.query.filter(
            Patient.organization_id == org_id,
            Patient.is_active == True,
            db.extract('month', Patient.date_of_birth) == today.month,
            db.extract('day', Patient.date_of_birth) == today.day
        ).all()

        return {
            'datum': today.strftime('%d.%m.%Y'),
            'anzahl': len(patienten),
            'patienten': [{
                'id': p.id,
                'name': f'{p.first_name} {p.last_name}',
                'patient_number': p.patient_number,
                'alter': today.year - p.date_of_birth.year if p.date_of_birth else None,
                'telefon': p.mobile or p.phone
            } for p in patienten]
        }

    elif tool_name == 'arzt_suchen':
        suchbegriff = tool_input.get('suchbegriff', '').strip()
        doctors = Doctor.query.filter(
            Doctor.organization_id == org_id,
            Doctor.is_active == True,
            db.or_(
                Doctor.first_name.ilike(f'%{suchbegriff}%'),
                Doctor.last_name.ilike(f'%{suchbegriff}%'),
                Doctor.specialty.ilike(f'%{suchbegriff}%'),
                Doctor.gln_number.ilike(f'%{suchbegriff}%')
            )
        ).all()

        return {
            'anzahl': len(doctors),
            'aerzte': [{
                'id': d.id,
                'name': f'{d.salutation} {d.first_name} {d.last_name}',
                'fachrichtung': d.specialty,
                'gln': d.gln_number,
                'zsr': d.zsr_number,
                'telefon': d.phone,
                'email': d.email
            } for d in doctors]
        }

    elif tool_name == 'versicherung_suchen':
        name = tool_input.get('name', '').strip()
        insurances = InsuranceProvider.query.filter(
            InsuranceProvider.organization_id == org_id,
            InsuranceProvider.is_active == True,
            InsuranceProvider.name.ilike(f'%{name}%')
        ).all()

        return {
            'anzahl': len(insurances),
            'versicherungen': [{
                'id': i.id,
                'name': i.name,
                'gln': i.gln_number,
                'telefon': i.phone,
                'e_billing': i.supports_electronic_billing
            } for i in insurances]
        }

    return {'error': f'Unbekanntes Tool: {tool_name}'}
