"""Patienten-Blueprint: Verwaltung von Patienten, Dokumenten und Patientenakten"""
import os
import json
import uuid
import re
from datetime import datetime, date, timedelta, timezone
from flask import render_template, request, redirect, url_for, flash, jsonify, \
    send_from_directory, current_app
from flask_login import login_required, current_user
from blueprints.patients import patients_bp
from models import db, Patient, InsuranceProvider, Doctor, Employee, \
    TreatmentSeries, TreatmentSeriesTemplate, Appointment, PatientDocument, \
    Location, Email, Organization
from sqlalchemy import func
from utils.auth import check_org
from utils.permissions import require_permission, has_permission
from services.audit_service import log_action


def parse_date(date_str):
    """Hilfsfunktion: Datumsstring (YYYY-MM-DD) in date-Objekt umwandeln"""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None


# ============================================================
# Patientenuebersicht
# ============================================================

@patients_bp.route('/')
@login_required
@require_permission('patients.view_list')
def index():
    """Patientenuebersicht mit Suche, Filter, Sortierung und Pagination"""
    search = request.args.get('search', '').strip()
    insurance_filter = request.args.get('insurance', '')
    location_filter = request.args.get('location', '')
    status = request.args.get('status', 'active')
    blacklist_filter = request.args.get('blacklist', '')
    sort_by = request.args.get('sort', 'name')
    page = request.args.get('page', 1, type=int)
    per_page = 25

    query = Patient.query.filter_by(organization_id=current_user.organization_id)

    # Status-Filter
    if status == 'active':
        query = query.filter_by(is_active=True)
    elif status == 'inactive':
        query = query.filter_by(is_active=False)

    # Blacklist-Filter
    if blacklist_filter == 'yes':
        query = query.filter_by(blacklisted=True)
    elif blacklist_filter == 'no':
        query = query.filter_by(blacklisted=False)

    # Versicherungs-Filter
    if insurance_filter:
        try:
            query = query.filter_by(insurance_provider_id=int(insurance_filter))
        except ValueError:
            pass

    # Suche (Cenplex-Logik: Alle Begriffe muessen matchen, AND-Verknuepfung)
    if search:
        # Pruefen ob Datum-Suche (Format dd.mm.yyyy)
        date_match = re.match(r'^(\d{1,2})\.(\d{1,2})\.(\d{4})$', search)
        if date_match:
            try:
                search_date = date(int(date_match.group(3)),
                                   int(date_match.group(2)),
                                   int(date_match.group(1)))
                query = query.filter(Patient.date_of_birth == search_date)
            except ValueError:
                pass
        else:
            # Cenplex: Aufteilen nach Leerzeichen, jeder Begriff muss in mind. einem Feld matchen
            terms = search.split()
            for term in terms:
                query = query.filter(
                    db.or_(
                        Patient.first_name.ilike(f'%{term}%'),
                        Patient.last_name.ilike(f'%{term}%'),
                        Patient.patient_number.ilike(f'%{term}%'),
                        Patient.phone.ilike(f'%{term}%'),
                        Patient.mobile.ilike(f'%{term}%'),
                        Patient.card_id.ilike(f'%{term}%'),
                        (Patient.first_name + ' ' + Patient.last_name).ilike(f'%{term}%')
                    )
                )

    # Sortierung
    if sort_by == 'name':
        query = query.order_by(Patient.last_name, Patient.first_name)
    elif sort_by == 'birthday':
        query = query.order_by(Patient.date_of_birth.desc())
    elif sort_by == 'number':
        query = query.order_by(Patient.patient_number)
    elif sort_by == 'created':
        query = query.order_by(Patient.created_at.desc())
    else:
        query = query.order_by(Patient.last_name, Patient.first_name)

    # Pagination
    total = query.count()
    patients = query.offset((page - 1) * per_page).limit(per_page).all()
    total_pages = (total + per_page - 1) // per_page

    # Letzte Behandlung pro Patient laden (Batch-Query statt N+1)
    last_appointments = {}
    if patients:
        patient_ids = [p.id for p in patients]
        last_appt_dates = dict(
            db.session.query(
                Appointment.patient_id,
                func.max(Appointment.start_time)
            ).filter(
                Appointment.patient_id.in_(patient_ids),
                Appointment.start_time <= datetime.now()
            ).group_by(Appointment.patient_id).all()
        )
        if last_appt_dates:
            for pid, max_time in last_appt_dates.items():
                appt = Appointment.query.filter_by(patient_id=pid, start_time=max_time).first()
                if appt:
                    last_appointments[pid] = appt

    # Filter-Daten
    org_id = current_user.organization_id
    insurances = InsuranceProvider.query.filter_by(organization_id=org_id, is_active=True) \
        .order_by(InsuranceProvider.name).all()
    locations = Location.query.filter_by(organization_id=org_id, is_active=True) \
        .order_by(Location.name).all()

    return render_template('patients/index.html',
                           patients=patients,
                           insurances=insurances,
                           locations=locations,
                           last_appointments=last_appointments,
                           search=search,
                           insurance_filter=insurance_filter,
                           location_filter=location_filter,
                           status=status,
                           blacklist_filter=blacklist_filter,
                           sort_by=sort_by,
                           page=page,
                           total_pages=total_pages,
                           total=total)


# ============================================================
# Patient erstellen / bearbeiten
# ============================================================

@patients_bp.route('/new', methods=['GET', 'POST'])
@login_required
@require_permission('patients.edit')
def create():
    """Neuen Patienten erstellen"""
    if request.method == 'POST':
        return _save_patient(None)

    org_id = current_user.organization_id
    insurances = InsuranceProvider.query.filter_by(organization_id=org_id, is_active=True) \
        .order_by(InsuranceProvider.name).all()
    doctors = Doctor.query.filter_by(organization_id=org_id, is_active=True) \
        .order_by(Doctor.last_name).all()
    therapists = Employee.query.filter_by(organization_id=org_id, is_active=True).all()
    therapists = [t for t in therapists if t.user and t.user.role == 'therapist']
    locations = Location.query.filter_by(organization_id=org_id, is_active=True) \
        .order_by(Location.name).all()

    return render_template('patients/form.html',
                           patient=None,
                           insurances=insurances,
                           doctors=doctors,
                           therapists=therapists,
                           locations=locations)


@patients_bp.route('/<int:patient_id>/edit', methods=['GET', 'POST'])
@login_required
@require_permission('patients.edit')
def edit(patient_id):
    """Patient bearbeiten"""
    patient = Patient.query.get_or_404(patient_id)
    check_org(patient)

    if request.method == 'POST':
        return _save_patient(patient)

    org_id = current_user.organization_id
    insurances = InsuranceProvider.query.filter_by(organization_id=org_id, is_active=True) \
        .order_by(InsuranceProvider.name).all()
    doctors = Doctor.query.filter_by(organization_id=org_id, is_active=True) \
        .order_by(Doctor.last_name).all()
    therapists = Employee.query.filter_by(organization_id=org_id, is_active=True).all()
    therapists = [t for t in therapists if t.user and t.user.role == 'therapist']
    locations = Location.query.filter_by(organization_id=org_id, is_active=True) \
        .order_by(Location.name).all()

    return render_template('patients/form.html',
                           patient=patient,
                           insurances=insurances,
                           doctors=doctors,
                           therapists=therapists,
                           locations=locations)


def _save_patient(patient):
    """Speichert einen Patienten (neu oder bestehend)"""
    first_name = request.form.get('first_name', '').strip()
    last_name = request.form.get('last_name', '').strip()
    dob_str = request.form.get('date_of_birth', '').strip()

    # Validierung
    errors = []
    if not first_name:
        errors.append('Vorname ist ein Pflichtfeld.')
    if not last_name:
        errors.append('Nachname ist ein Pflichtfeld.')
    if not dob_str:
        errors.append('Geburtsdatum ist ein Pflichtfeld.')

    dob = None
    if dob_str:
        try:
            dob = datetime.strptime(dob_str, '%Y-%m-%d').date()
        except ValueError:
            errors.append('Ungültiges Datumsformat für Geburtsdatum.')

    # AHV-Nummer Validierung (Cenplex: Format + Pruefsumme)
    ahv = request.form.get('ahv_number', '').strip()
    if ahv:
        if not re.match(r'^756\.\d{4}\.\d{4}\.\d{2}$', ahv):
            errors.append('AHV-Nummer muss im Format 756.XXXX.XXXX.XX sein.')
        else:
            # Cenplex: Pruefsummenvalidierung (Modulo 10, EAN-13)
            digits = ahv.replace('.', '')
            if len(digits) == 13:
                checksum = 0
                for i, d in enumerate(digits[:12]):
                    checksum += int(d) * (1 if i % 2 == 0 else 3)
                expected = (10 - (checksum % 10)) % 10
                if int(digits[12]) != expected:
                    errors.append('AHV-Nummer: Pruefsumme ungueltig.')

    # Versichertenkarten-Nr. Validierung (Cenplex: genau 20 Ziffern)
    card_id = request.form.get('card_id', '').strip()
    if card_id and not re.match(r'^\d{20}$', card_id):
        errors.append('Versichertenkarten-Nr. muss genau 20 Ziffern enthalten.')

    # Telefon-Validierung (Cenplex: mind. Mobil oder Festnetz)
    phone_val = request.form.get('phone', '').strip()
    mobile_val = request.form.get('mobile', '').strip()
    if not phone_val and not mobile_val:
        errors.append('Mindestens eine Telefonnummer (Festnetz oder Mobil) ist erforderlich.')

    if errors:
        for e in errors:
            flash(e, 'error')
        org_id = current_user.organization_id
        insurances = InsuranceProvider.query.filter_by(organization_id=org_id, is_active=True) \
            .order_by(InsuranceProvider.name).all()
        doctors = Doctor.query.filter_by(organization_id=org_id, is_active=True) \
            .order_by(Doctor.last_name).all()
        therapists = Employee.query.filter_by(organization_id=org_id, is_active=True).all()
        therapists = [t for t in therapists if t.user and t.user.role == 'therapist']
        locations = Location.query.filter_by(organization_id=org_id, is_active=True) \
            .order_by(Location.name).all()
        return render_template('patients/form.html',
                               patient=patient,
                               insurances=insurances,
                               doctors=doctors,
                               therapists=therapists,
                               locations=locations)

    is_new = patient is None
    if is_new:
        patient = Patient(organization_id=current_user.organization_id)
        # Auto-generierte Patientennummer
        last_p = Patient.query.filter_by(organization_id=current_user.organization_id) \
            .order_by(Patient.id.desc()).first()
        if last_p and last_p.patient_number:
            try:
                num = int(last_p.patient_number[1:]) + 1
            except (ValueError, IndexError):
                num = Patient.query.count() + 1
        else:
            num = 1
        patient.patient_number = f'P{num:05d}'

    # Personalien
    patient.salutation = request.form.get('salutation', '')
    patient.first_name = first_name
    patient.last_name = last_name
    patient.date_of_birth = dob
    patient.gender = request.form.get('gender', '')
    patient.ahv_number = ahv
    patient.preferred_language = request.form.get('preferred_language', 'Deutsch')

    # Versicherung
    ins_id = request.form.get('insurance_provider_id', '')
    patient.insurance_provider_id = int(ins_id) if ins_id else None
    patient.insurance_number = request.form.get('insurance_number', '').strip()
    patient.insurance_type = request.form.get('insurance_type', 'KVG')
    patient.case_number = request.form.get('case_number', '').strip()
    accident_str = request.form.get('accident_date', '').strip()
    if accident_str:
        try:
            patient.accident_date = datetime.strptime(accident_str, '%Y-%m-%d').date()
        except ValueError:
            pass
    else:
        patient.accident_date = None
    patient.supplementary_insurance_name = request.form.get('supplementary_insurance_name', '').strip()
    patient.supplementary_insurance_number = request.form.get('supplementary_insurance_number', '').strip()

    # Personalien erweitert (Cenplex)
    patient.addressing = request.form.get('addressing', '').strip()
    patient.is_special = request.form.get('is_special') == 'on'
    patient.special_notes = request.form.get('special_notes', '').strip()

    # Kontakt
    patient.phone = request.form.get('phone', '').strip()
    patient.mobile = request.form.get('mobile', '').strip()
    patient.phone_office = request.form.get('phone_office', '').strip()
    patient.email = request.form.get('email', '').strip()
    patient.address = request.form.get('address', '').strip()
    patient.zip_code = request.form.get('zip_code', '').strip()
    patient.city = request.form.get('city', '').strip()
    patient.country = request.form.get('country', 'CH').strip()
    patient.preferred_contact_method = request.form.get('preferred_contact_method', 'phone')

    # Bevorzugte Terminzeiten
    pref_times = request.form.getlist('preferred_times')
    pref_days = request.form.getlist('preferred_days')
    patient.preferred_appointment_times_json = json.dumps({
        'times': pref_times,
        'days': pref_days
    })

    # Arbeitgeber
    patient.employer_name = request.form.get('employer_name', '').strip()
    patient.employer_address = request.form.get('employer_address', '').strip()
    patient.employer_contact = request.form.get('employer_contact', '').strip()
    patient.employer_phone = request.form.get('employer_phone', '').strip()

    # Sonstiges
    patient.notes = request.form.get('notes', '').strip()
    patient.blacklisted = request.form.get('blacklisted') == 'on'
    patient.blacklist_reason = request.form.get('blacklist_reason', '').strip()
    pref_ther = request.form.get('preferred_therapist_id', '')
    patient.preferred_therapist_id = int(pref_ther) if pref_ther else None

    # Cenplex: Erweiterte Versicherung
    patient.kanton = request.form.get('kanton', '')
    patient.is_kvg_base = request.form.get('is_kvg_base') == 'on'
    patient.kvg_model = int(request.form.get('kvg_model', 1))
    patient.kvg_accident_coverage = int(request.form.get('kvg_accident_coverage', 99))
    patient.card_id = request.form.get('card_id', '')
    patient.card_expiry = parse_date(request.form.get('card_expiry'))
    patient.insured_id = request.form.get('insured_id', '')
    costunit_kvg = request.form.get('costunit_id', '')
    patient.costunit_id = int(costunit_kvg) if costunit_kvg else None
    patient.medical_service_coverage_restriction = int(request.form.get('medical_service_coverage_restriction', 0)) or None

    # Cenplex: UVG/VVG Kostentraeger
    costunit_uvg = request.form.get('costunit_uvg_id', '')
    patient.costunit_uvg_id = int(costunit_uvg) if costunit_uvg else None
    costunit_vvg = request.form.get('costunit_vvg_id', '')
    patient.costunit_vvg_id = int(costunit_vvg) if costunit_vvg else None
    patient.insured_id_vvg = request.form.get('insured_id_vvg', '')
    patient.card_id_vvg = request.form.get('card_id_vvg', '')
    patient.card_vvg_expiry = parse_date(request.form.get('card_vvg_expiry'))

    # Cenplex: Premium-Zahler (Rechnungsempfaenger)
    patient.premium_payer_firstname = request.form.get('premium_payer_firstname', '')
    patient.premium_payer_lastname = request.form.get('premium_payer_lastname', '')
    patient.premium_payer_company = request.form.get('premium_payer_company', '')
    patient.premium_payer_address = request.form.get('premium_payer_address', '')
    patient.premium_payer_zipcode = request.form.get('premium_payer_zipcode', '')
    patient.premium_payer_town = request.form.get('premium_payer_town', '')
    patient.premium_payer_kanton = request.form.get('premium_payer_kanton', '')
    patient.premium_payer_country = request.form.get('premium_payer_country', 'CH')
    patient.premium_payer_address2 = request.form.get('premium_payer_address2', '')
    patient.premium_payer_email = request.form.get('premium_payer_email', '')

    # Cenplex: Beruf, Hobbies, Zuweiser
    patient.hobbies = request.form.get('hobbies', '')
    patient.profession = request.form.get('profession', '')
    doctor_id = request.form.get('doctor_id', '')
    patient.doctor_id = int(doctor_id) if doctor_id else None
    referenced_by = request.form.get('referenced_by_id', '')
    patient.referenced_by_id = int(referenced_by) if referenced_by else None

    # Cenplex: Externe Systeme
    patient.egym_id = request.form.get('egym_id', '')
    patient.vald_id = request.form.get('vald_id', '')
    patient.dividat_id = request.form.get('dividat_id', '')
    patient.mywellness_id = request.form.get('mywellness_id', '')
    patient.milon_id = request.form.get('milon_id', '')
    patient.mywellness_device_type = request.form.get('mywellness_device_type', '')

    # Cenplex: Kaution
    deposit_str = request.form.get('deposit_amount', '')
    patient.deposit_amount = float(deposit_str) if deposit_str else None
    patient.deposit_payed_date = parse_date(request.form.get('deposit_payed_date'))
    patient.deposit_receipt_date = parse_date(request.form.get('deposit_receipt_date'))
    patient.deposit_payed_back_date = parse_date(request.form.get('deposit_payed_back_date'))

    # Cenplex: Standort
    loc_id = request.form.get('location_id', '')
    patient.location_id = int(loc_id) if loc_id else None

    if is_new:
        db.session.add(patient)
        db.session.flush()
        log_action('create', 'patient', patient.id)
    else:
        log_action('update', 'patient', patient.id)

    db.session.commit()
    flash('Patient erfolgreich gespeichert.' if not is_new else 'Patient erfolgreich erstellt.', 'success')
    return redirect(url_for('patients.detail', patient_id=patient.id))


# ============================================================
# Patientendetail
# ============================================================

@patients_bp.route('/<int:patient_id>')
@login_required
@require_permission('patients.view_detail')
def detail(patient_id):
    """Patientendetail mit Tabs"""
    patient = Patient.query.get_or_404(patient_id)
    check_org(patient)
    log_action('read', 'patient', patient.id)
    tab = request.args.get('tab', 'overview')

    # Uebersicht-Daten
    last_appointment = Appointment.query.filter_by(patient_id=patient.id) \
        .filter(Appointment.start_time <= datetime.now()) \
        .order_by(Appointment.start_time.desc()).first()

    next_appointment = Appointment.query.filter_by(patient_id=patient.id) \
        .filter(Appointment.start_time > datetime.now()) \
        .order_by(Appointment.start_time.asc()).first()

    # Behandlungsserien
    active_series = TreatmentSeries.query.filter_by(
        patient_id=patient.id, status='active').all()
    completed_series = TreatmentSeries.query.filter_by(
        patient_id=patient.id, status='completed').all()
    all_series = TreatmentSeries.query.filter_by(patient_id=patient.id) \
        .order_by(TreatmentSeries.created_at.desc()).all()

    # Termine
    appointments = Appointment.query.filter_by(patient_id=patient.id) \
        .order_by(Appointment.start_time.desc()).all()

    # Dokumente
    documents = PatientDocument.query.filter_by(patient_id=patient.id) \
        .order_by(PatientDocument.created_at.desc()).all()

    # Kommunikation (E-Mails)
    emails = Email.query.filter_by(linked_patient_id=patient.id) \
        .order_by(Email.created_at.desc()).all()

    # Serien-Fortschritt berechnen (Batch-Query statt N+1)
    series_progress = {}
    if all_series:
        series_ids = [s.id for s in all_series]
        appt_counts = dict(
            db.session.query(
                Appointment.series_id,
                func.count(Appointment.id)
            ).filter(
                Appointment.series_id.in_(series_ids)
            ).group_by(Appointment.series_id).all()
        )
        for s in all_series:
            total = s.template.num_appointments if s.template else 0
            series_progress[s.id] = {'done': appt_counts.get(s.id, 0), 'total': total}

    # Bevorzugte Terminzeiten parsen
    pref_times = {}
    if patient.preferred_appointment_times_json:
        try:
            pref_times = json.loads(patient.preferred_appointment_times_json)
        except (json.JSONDecodeError, TypeError):
            pass

    # Alter berechnen
    age = None
    if patient.date_of_birth:
        today = date.today()
        age = today.year - patient.date_of_birth.year - (
            (today.month, today.day) < (patient.date_of_birth.month, patient.date_of_birth.day)
        )

    return render_template('patients/detail.html',
                           patient=patient,
                           tab=tab,
                           age=age,
                           last_appointment=last_appointment,
                           next_appointment=next_appointment,
                           active_series=active_series,
                           completed_series=completed_series,
                           all_series=all_series,
                           series_progress=series_progress,
                           appointments=appointments,
                           documents=documents,
                           emails=emails,
                           pref_times=pref_times,
                           now=datetime.now())


# ============================================================
# Patient deaktivieren / aktivieren
# ============================================================

@patients_bp.route('/<int:patient_id>/toggle', methods=['POST'])
@login_required
@require_permission('patients.delete')
def toggle_active(patient_id):
    """Patient aktivieren/deaktivieren (Soft-Delete)"""
    patient = Patient.query.get_or_404(patient_id)
    check_org(patient)
    patient.is_active = not patient.is_active
    db.session.commit()
    status = 'aktiviert' if patient.is_active else 'deaktiviert'
    flash(f'Patient wurde {status}.', 'success')
    return redirect(url_for('patients.detail', patient_id=patient.id))


# ============================================================
# Dokumenten-Upload
# ============================================================

ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png', 'docx'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


def _allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@patients_bp.route('/<int:patient_id>/documents', methods=['POST'])
@login_required
def upload_document(patient_id):
    """Dokument fuer einen Patienten hochladen"""
    patient = Patient.query.get_or_404(patient_id)
    check_org(patient)

    if 'file' not in request.files:
        flash('Keine Datei ausgewählt.', 'error')
        return redirect(url_for('patients.detail', patient_id=patient.id, tab='documents'))

    file = request.files['file']
    if file.filename == '':
        flash('Keine Datei ausgewählt.', 'error')
        return redirect(url_for('patients.detail', patient_id=patient.id, tab='documents'))

    if not _allowed_file(file.filename):
        flash('Dateityp nicht erlaubt. Erlaubt: PDF, JPG, PNG, DOCX.', 'error')
        return redirect(url_for('patients.detail', patient_id=patient.id, tab='documents'))

    # Dateigroesse pruefen
    file.seek(0, 2)
    file_size = file.tell()
    file.seek(0)
    if file_size > MAX_FILE_SIZE:
        flash('Datei ist zu gross. Maximum: 10 MB.', 'error')
        return redirect(url_for('patients.detail', patient_id=patient.id, tab='documents'))

    # Speicherverzeichnis
    upload_dir = os.path.join(current_app.root_path, 'uploads', 'patients', str(patient.id))
    os.makedirs(upload_dir, exist_ok=True)

    # Sicheren Dateinamen generieren
    ext = file.filename.rsplit('.', 1)[1].lower()
    safe_filename = f'{uuid.uuid4().hex}.{ext}'
    file_path = os.path.join(upload_dir, safe_filename)
    file.save(file_path)

    # Datenbank-Eintrag
    doc = PatientDocument(
        patient_id=patient.id,
        filename=safe_filename,
        original_filename=file.filename,
        file_path=file_path,
        file_size=file_size,
        file_type=ext,
        document_type=request.form.get('document_type', 'sonstiges'),
        notes=request.form.get('doc_notes', '').strip(),
        uploaded_by_id=current_user.id
    )
    db.session.add(doc)
    db.session.commit()

    flash('Dokument erfolgreich hochgeladen.', 'success')
    return redirect(url_for('patients.detail', patient_id=patient.id, tab='documents'))


@patients_bp.route('/documents/<int:doc_id>/download')
@login_required
def download_document(doc_id):
    """Dokument herunterladen"""
    doc = PatientDocument.query.get_or_404(doc_id)
    # IDOR-Schutz: Patient des Dokuments muss zur Organisation gehoeren
    patient = Patient.query.get_or_404(doc.patient_id)
    check_org(patient)
    log_action('download', 'document', doc.id)
    db.session.commit()
    directory = os.path.dirname(doc.file_path)
    return send_from_directory(directory, doc.filename,
                               download_name=doc.original_filename,
                               as_attachment=True)


@patients_bp.route('/documents/<int:doc_id>/delete', methods=['POST'])
@login_required
def delete_document(doc_id):
    """Dokument loeschen"""
    doc = PatientDocument.query.get_or_404(doc_id)
    # IDOR-Schutz: Patient des Dokuments muss zur Organisation gehoeren
    patient = Patient.query.get_or_404(doc.patient_id)
    check_org(patient)
    patient_id = doc.patient_id

    # Datei loeschen
    if os.path.exists(doc.file_path):
        os.remove(doc.file_path)

    db.session.delete(doc)
    db.session.commit()
    flash('Dokument gelöscht.', 'success')
    return redirect(url_for('patients.detail', patient_id=patient_id, tab='documents'))


# ============================================================
# Patienten-Merge
# ============================================================

@patients_bp.route('/merge', methods=['GET', 'POST'])
@login_required
@require_permission('patients.merge')
def merge():
    """Zwei Patienten zusammenfuehren (nur Admin)"""

    if request.method == 'POST':
        source_id = request.form.get('source_id', type=int)
        target_id = request.form.get('target_id', type=int)

        if not source_id or not target_id:
            flash('Bitte wählen Sie Quell- und Zielpatient.', 'error')
            return redirect(url_for('patients.merge'))

        if source_id == target_id:
            flash('Quell- und Zielpatient dürfen nicht identisch sein.', 'error')
            return redirect(url_for('patients.merge'))

        source = Patient.query.get_or_404(source_id)
        target = Patient.query.get_or_404(target_id)
        check_org(source)
        check_org(target)

        # Serien uebertragen
        TreatmentSeries.query.filter_by(patient_id=source.id) \
            .update({'patient_id': target.id})

        # Termine uebertragen
        Appointment.query.filter_by(patient_id=source.id) \
            .update({'patient_id': target.id})

        # Dokumente uebertragen
        PatientDocument.query.filter_by(patient_id=source.id) \
            .update({'patient_id': target.id})

        # E-Mails uebertragen
        Email.query.filter_by(linked_patient_id=source.id) \
            .update({'linked_patient_id': target.id})

        # Quell-Patient deaktivieren
        source.is_active = False
        source.notes = (source.notes or '') + \
            f'\n[Zusammengeführt mit Patient {target.patient_number} am {date.today().strftime("%d.%m.%Y")}]'

        log_action('merge', 'patient', target.id, changes={
            'source_patient_id': {'old': source.id, 'new': None},
            'target_patient_id': {'new': target.id},
            'merged_records': {'new': 'treatment_series, appointments, documents, emails'}
        })
        db.session.commit()
        flash(f'Patient {source.first_name} {source.last_name} wurde mit '
              f'{target.first_name} {target.last_name} zusammengeführt.', 'success')
        return redirect(url_for('patients.detail', patient_id=target.id))

    patients = Patient.query.filter_by(
        organization_id=current_user.organization_id, is_active=True
    ).order_by(Patient.last_name, Patient.first_name).all()

    return render_template('patients/merge.html', patients=patients)


# ============================================================
# API-Endpunkte
# ============================================================

@patients_bp.route('/api/search')
@login_required
def api_search():
    """Patient suchen (fuer AJAX)"""
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify([])

    patients = Patient.query.filter_by(
        organization_id=current_user.organization_id, is_active=True
    ).filter(
        db.or_(
            Patient.first_name.ilike(f'%{q}%'),
            Patient.last_name.ilike(f'%{q}%'),
            Patient.patient_number.ilike(f'%{q}%'),
            (Patient.first_name + ' ' + Patient.last_name).ilike(f'%{q}%')
        )
    ).limit(10).all()

    return jsonify([{
        'id': p.id,
        'text': f'{p.last_name}, {p.first_name} ({p.patient_number})',
        'patient_number': p.patient_number,
        'name': f'{p.first_name} {p.last_name}'
    } for p in patients])


# ============================================================
# Cenplex Phase 2: Duplikat-Erkennung
# ============================================================

@patients_bp.route('/api/check-duplicates')
@login_required
def api_check_duplicates():
    """Duplikat-Erkennung: Sucht Patienten mit gleichem Geschlecht und Geburtsdatum,
    AHV-Nummer oder Versichertenkarten-Nr. (Cenplex: GetPatientsBySexAndBirthday)"""
    gender = request.args.get('gender', '').strip()
    dob_str = request.args.get('date_of_birth', '').strip()
    first_name = request.args.get('first_name', '').strip()
    last_name = request.args.get('last_name', '').strip()
    ahv_number = request.args.get('ahv_number', '').strip()
    card_id_val = request.args.get('card_id', '').strip()
    exclude_id = request.args.get('exclude_id', type=int)

    org_id = current_user.organization_id
    duplicates = []

    # Cenplex: AHV und Kartennummer sind natuerliche Schluessel - exakter Match
    if ahv_number:
        q = Patient.query.filter_by(organization_id=org_id, is_active=True) \
            .filter(Patient.ahv_number == ahv_number)
        if exclude_id:
            q = q.filter(Patient.id != exclude_id)
        duplicates = q.limit(10).all()

    if not duplicates and card_id_val:
        q = Patient.query.filter_by(organization_id=org_id, is_active=True) \
            .filter(Patient.card_id == card_id_val)
        if exclude_id:
            q = q.filter(Patient.id != exclude_id)
        duplicates = q.limit(10).all()

    # Primaer: Geschlecht + Geburtsdatum (Cenplex-Logik)
    if not duplicates and dob_str:
        dob = parse_date(dob_str)
        if dob:
            query = Patient.query.filter_by(
                organization_id=org_id, is_active=True, date_of_birth=dob
            )
            if gender:
                query = query.filter_by(gender=gender)
            if exclude_id:
                query = query.filter(Patient.id != exclude_id)
            duplicates = query.limit(10).all()

    # Sekundaer: Name-Match (erweiterte Erkennung)
    if not duplicates and first_name and last_name:
        query2 = Patient.query.filter_by(
            organization_id=org_id, is_active=True
        ).filter(
            Patient.first_name.ilike(first_name),
            Patient.last_name.ilike(last_name)
        )
        if exclude_id:
            query2 = query2.filter(Patient.id != exclude_id)
        duplicates = query2.limit(10).all()

    return jsonify([{
        'id': p.id,
        'patient_number': p.patient_number,
        'first_name': p.first_name,
        'last_name': p.last_name,
        'date_of_birth': p.date_of_birth.strftime('%d.%m.%Y') if p.date_of_birth else '',
        'gender': p.gender or '',
        'city': p.city or '',
        'insurance': p.insurance_provider.name if p.insurance_provider else ''
    } for p in duplicates])


# ============================================================
# Cenplex Phase 2: Patienten-Sperrzeiten (Planning Breaks)
# ============================================================

@patients_bp.route('/<int:patient_id>/block-times')
@login_required
def block_times(patient_id):
    """Patienten-Sperrzeiten anzeigen"""
    from models import PatientBlockTime
    patient = Patient.query.get_or_404(patient_id)
    check_org(patient)

    blocks = PatientBlockTime.query.filter_by(patient_id=patient.id) \
        .order_by(PatientBlockTime.start_date.desc()).all()
    return jsonify([{
        'id': b.id,
        'start_date': b.start_date.isoformat() if b.start_date else '',
        'end_date': b.end_date.isoformat() if b.end_date else '',
        'reason': b.reason or ''
    } for b in blocks])


@patients_bp.route('/<int:patient_id>/block-times', methods=['POST'])
@login_required
def save_block_time(patient_id):
    """Patienten-Sperrzeit erstellen/aktualisieren"""
    from models import PatientBlockTime
    patient = Patient.query.get_or_404(patient_id)
    check_org(patient)

    data = request.get_json() if request.is_json else request.form
    block_id = data.get('id')

    if block_id:
        block = PatientBlockTime.query.get_or_404(int(block_id))
    else:
        block = PatientBlockTime(patient_id=patient.id)

    start_str = data.get('start_date', '')
    end_str = data.get('end_date', '')

    if not start_str or not end_str:
        return jsonify({'error': 'Start- und Enddatum sind Pflicht'}), 400

    try:
        block.start_date = datetime.fromisoformat(start_str)
        block.end_date = datetime.fromisoformat(end_str)
    except (ValueError, TypeError):
        return jsonify({'error': 'Ungültiges Datumsformat'}), 400

    if block.start_date >= block.end_date:
        return jsonify({'error': 'Startdatum muss vor Enddatum liegen'}), 400

    block.reason = data.get('reason', '')

    if not block_id:
        db.session.add(block)
    db.session.commit()

    return jsonify({'success': True, 'id': block.id})


@patients_bp.route('/<int:patient_id>/block-times/<int:block_id>', methods=['DELETE'])
@login_required
def delete_block_time(patient_id, block_id):
    """Patienten-Sperrzeit löschen"""
    from models import PatientBlockTime
    patient = Patient.query.get_or_404(patient_id)
    check_org(patient)

    block = PatientBlockTime.query.get_or_404(block_id)
    if block.patient_id != patient.id:
        return jsonify({'error': 'Nicht gefunden'}), 404

    db.session.delete(block)
    db.session.commit()
    return jsonify({'success': True})


# ============================================================
# Cenplex Phase 2: Patientenziele (Goals)
# ============================================================

@patients_bp.route('/<int:patient_id>/goals')
@login_required
def goals(patient_id):
    """Patientenziele anzeigen (mit Hierarchie wie Cenplex PatientGoalModel)"""
    from models import TherapyGoal
    patient = Patient.query.get_or_404(patient_id)
    check_org(patient)

    # Cenplex: Nur Top-Level-Ziele laden (parent_id IS NULL), Kinder werden verschachtelt
    goals = TherapyGoal.query.filter_by(patient_id=patient.id, parent_id=None) \
        .order_by(TherapyGoal.created_at.desc()).all()

    def goal_to_dict(g):
        result = {
            'id': g.id,
            'description': g.description,
            'target_value': g.target_value,
            'current_value': g.current_value,
            'achievement_percent': g.achievement_percent,
            'status': g.status,
            'series_id': g.series_id,
            'due_date': g.due_date.isoformat() if g.due_date else '',
            'finished_date': g.finished_date.isoformat() if g.finished_date else '',
            'created_at': g.created_at.isoformat() if g.created_at else '',
            'children': [goal_to_dict(c) for c in g.children.order_by(TherapyGoal.created_at).all()]
        }
        return result

    return jsonify([goal_to_dict(g) for g in goals])


@patients_bp.route('/<int:patient_id>/goals', methods=['POST'])
@login_required
def save_goal(patient_id):
    """Patientenziel erstellen/aktualisieren"""
    from models import TherapyGoal
    patient = Patient.query.get_or_404(patient_id)
    check_org(patient)

    data = request.get_json() if request.is_json else request.form
    goal_id = data.get('id')

    if goal_id:
        goal = TherapyGoal.query.get_or_404(int(goal_id))
    else:
        goal = TherapyGoal(
            organization_id=current_user.organization_id,
            patient_id=patient.id
        )

    goal.description = data.get('description', '')
    goal.target_value = data.get('target_value', '')
    goal.current_value = data.get('current_value', '')
    goal.status = data.get('status', 'open')

    series_id = data.get('series_id')
    goal.series_id = int(series_id) if series_id else None

    parent_id = data.get('parent_id')
    goal.parent_id = int(parent_id) if parent_id else None

    due_date_str = data.get('due_date', '')
    if due_date_str:
        try:
            goal.due_date = datetime.fromisoformat(due_date_str).date() if 'T' in due_date_str else datetime.strptime(due_date_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            pass

    try:
        goal.achievement_percent = int(data.get('achievement_percent', 0))
    except (ValueError, TypeError):
        goal.achievement_percent = 0

    if not goal_id:
        db.session.add(goal)
    db.session.commit()

    return jsonify({'success': True, 'id': goal.id})


@patients_bp.route('/<int:patient_id>/goals/<int:goal_id>/finish', methods=['POST'])
@login_required
def finish_goal(patient_id, goal_id):
    """Patientenziel als erreicht markieren"""
    from models import TherapyGoal
    patient = Patient.query.get_or_404(patient_id)
    check_org(patient)

    goal = TherapyGoal.query.get_or_404(goal_id)
    if goal.patient_id != patient.id:
        return jsonify({'error': 'Nicht gefunden'}), 404

    goal.status = 'achieved'
    goal.achievement_percent = 100
    goal.finished_date = datetime.now(timezone.utc)
    # Cenplex: Alle Unterziele ebenfalls abschliessen
    for child in goal.children.all():
        if child.status != 'achieved':
            child.status = 'achieved'
            child.achievement_percent = 100
            child.finished_date = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify({'success': True})


# ============================================================
# Cenplex Phase 2: Guthaben/Credits
# ============================================================

@patients_bp.route('/<int:patient_id>/credits')
@login_required
def credits(patient_id):
    """Patientenguthaben anzeigen"""
    from models import Credit
    patient = Patient.query.get_or_404(patient_id)
    check_org(patient)

    credits_list = Credit.query.filter_by(
        patient_id=patient.id, is_deleted=False
    ).order_by(Credit.created_at.desc()).all()

    return jsonify([{
        'id': c.id,
        'original_amount': float(c.original_amount) if c.original_amount else 0,
        'remaining_amount': float(c.remaining_amount) if c.remaining_amount else 0,
        'from_invoice_id': c.from_invoice_id,
        'created_at': c.created_at.isoformat() if c.created_at else ''
    } for c in credits_list])


# ============================================================
# Cenplex Phase 2: Arztberichte (Doctor Reports)
# ============================================================

@patients_bp.route('/<int:patient_id>/doctor-reports')
@login_required
def doctor_reports(patient_id):
    """Arztberichte eines Patienten anzeigen"""
    from models import DoctorReport
    patient = Patient.query.get_or_404(patient_id)
    check_org(patient)

    reports = DoctorReport.query.filter_by(patient_id=patient.id) \
        .order_by(DoctorReport.created_at.desc()).all()
    return jsonify([{
        'id': r.id,
        'headline': r.headline or '',
        'therapist_name': f'{r.therapist.user.first_name} {r.therapist.user.last_name}' if r.therapist and r.therapist.user else '',
        'doctor_name': f'{r.doctor.first_name} {r.doctor.last_name}' if r.doctor else '',
        'last_sent': r.last_sent.isoformat() if r.last_sent else '',
        'created_at': r.created_at.isoformat() if r.created_at else ''
    } for r in reports])


@patients_bp.route('/<int:patient_id>/doctor-reports', methods=['POST'])
@login_required
def save_doctor_report(patient_id):
    """Arztbericht erstellen/aktualisieren"""
    from models import DoctorReport, Contact
    patient = Patient.query.get_or_404(patient_id)
    check_org(patient)

    data = request.get_json() if request.is_json else request.form
    report_id = data.get('id')

    if report_id:
        report = DoctorReport.query.get_or_404(int(report_id))
    else:
        report = DoctorReport(
            organization_id=current_user.organization_id,
            patient_id=patient.id
        )

    report.headline = data.get('headline', '')
    report.content_text = data.get('content_text', '')

    therapist_id = data.get('therapist_id')
    report.therapist_id = int(therapist_id) if therapist_id else None

    doctor_id = data.get('doctor_id')
    report.doctor_id = int(doctor_id) if doctor_id else None

    cost_unit_id = data.get('cost_unit_id')
    report.cost_unit_id = int(cost_unit_id) if cost_unit_id else None

    if not report_id:
        db.session.add(report)
    db.session.commit()

    log_action('create' if not report_id else 'update', 'doctor_report', report.id)
    return jsonify({'success': True, 'id': report.id})


# ============================================================
# Cenplex Phase 2: Hilfsmittel-Bestellungen (Supplement Orders)
# ============================================================

@patients_bp.route('/<int:patient_id>/supplement-orders')
@login_required
def supplement_orders(patient_id):
    """Hilfsmittel-Bestellungen eines Patienten"""
    from models import SupplementOrder
    patient = Patient.query.get_or_404(patient_id)
    check_org(patient)

    orders = SupplementOrder.query.filter_by(patient_id=patient.id) \
        .order_by(SupplementOrder.created_at.desc()).all()
    return jsonify([{
        'id': o.id,
        'supplier_name': o.supplier.company_name if o.supplier else '',
        'employee_name': f'{o.employee.user.first_name} {o.employee.user.last_name}' if o.employee and o.employee.user else '',
        'print_date': o.print_date.isoformat() if o.print_date else '',
        'send_date': o.send_date.isoformat() if o.send_date else '',
        'items_count': len(o.items) if hasattr(o, 'items') else 0,
        'created_at': o.created_at.isoformat() if o.created_at else ''
    } for o in orders])


@patients_bp.route('/<int:patient_id>/supplement-orders', methods=['POST'])
@login_required
def save_supplement_order(patient_id):
    """Hilfsmittel-Bestellung erstellen"""
    from models import SupplementOrder, SupplementOrderItem
    patient = Patient.query.get_or_404(patient_id)
    check_org(patient)

    data = request.get_json()
    if not data:
        return jsonify({'error': 'Keine Daten'}), 400

    supplier_id = data.get('supplier_id')
    if not supplier_id:
        return jsonify({'error': 'Lieferant ist Pflicht'}), 400

    order = SupplementOrder(
        organization_id=current_user.organization_id,
        patient_id=patient.id,
        supplier_id=int(supplier_id),
        employee_id=current_user.employee.id if current_user.employee else None
    )
    db.session.add(order)
    db.session.flush()

    items = data.get('items', [])
    for item_data in items:
        item = SupplementOrderItem(
            order_id=order.id,
            product_id=item_data.get('product_id'),
            quantity=item_data.get('quantity', 1),
            note=item_data.get('note', '')
        )
        db.session.add(item)

    db.session.commit()
    log_action('create', 'supplement_order', order.id)
    return jsonify({'success': True, 'id': order.id})


# ============================================================
# Cenplex Phase 2: Erweiterte Suche
# ============================================================

@patients_bp.route('/api/search-extended')
@login_required
def api_search_extended():
    """Erweiterte Patientensuche (Cenplex: inkl. E-Mail, Kartennummer, AHV)"""
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify([])

    org_id = current_user.organization_id
    query = Patient.query.filter_by(organization_id=org_id, is_active=True)

    # Datum-Suche (dd.mm.yyyy)
    date_match = re.match(r'^(\d{1,2})\.(\d{1,2})\.(\d{4})$', q)
    if date_match:
        try:
            search_date = date(int(date_match.group(3)),
                               int(date_match.group(2)),
                               int(date_match.group(1)))
            query = query.filter(Patient.date_of_birth == search_date)
        except ValueError:
            return jsonify([])
    else:
        query = query.filter(
            db.or_(
                Patient.first_name.ilike(f'%{q}%'),
                Patient.last_name.ilike(f'%{q}%'),
                Patient.patient_number.ilike(f'%{q}%'),
                Patient.phone.ilike(f'%{q}%'),
                Patient.mobile.ilike(f'%{q}%'),
                Patient.email.ilike(f'%{q}%'),
                Patient.card_id.ilike(f'%{q}%'),
                Patient.ahv_number.ilike(f'%{q}%'),
                (Patient.first_name + ' ' + Patient.last_name).ilike(f'%{q}%')
            )
        )

    patients = query.limit(20).all()
    return jsonify([{
        'id': p.id,
        'patient_number': p.patient_number,
        'first_name': p.first_name,
        'last_name': p.last_name,
        'date_of_birth': p.date_of_birth.strftime('%d.%m.%Y') if p.date_of_birth else '',
        'city': p.city or '',
        'phone': p.phone or p.mobile or '',
        'email': p.email or '',
        'insurance': p.insurance_provider.name if p.insurance_provider else ''
    } for p in patients])


# ============================================================
# Cenplex Phase 2: Patienten-Behandlungshistorie
# ============================================================

@patients_bp.route('/<int:patient_id>/history')
@login_required
def appointment_history(patient_id):
    """Detaillierte Behandlungshistorie mit Seriengruppierung
    (Cenplex: PatientHistoryDialogViewModel)"""
    patient = Patient.query.get_or_404(patient_id)
    check_org(patient)

    series_filter = request.args.get('series_id', type=int)

    query = Appointment.query.filter_by(patient_id=patient.id) \
        .order_by(Appointment.start_time.desc())

    if series_filter:
        query = query.filter_by(series_id=series_filter)

    appointments = query.all()

    # Nach Serien gruppieren
    series_groups = {}
    ungrouped = []
    for appt in appointments:
        if appt.series_id:
            if appt.series_id not in series_groups:
                series_groups[appt.series_id] = {
                    'series': appt.series,
                    'appointments': []
                }
            series_groups[appt.series_id]['appointments'].append(appt)
        else:
            ungrouped.append(appt)

    # Serien fuer Filter-Dropdown
    all_series = TreatmentSeries.query.filter_by(patient_id=patient.id) \
        .order_by(TreatmentSeries.created_at.desc()).all()

    result = {
        'series_groups': [{
            'series_id': sid,
            'series_title': g['series'].title or (g['series'].template.name if g['series'].template else f'Serie {sid}'),
            'series_status': g['series'].status,
            'appointments': [{
                'id': a.id,
                'start_time': a.start_time.isoformat(),
                'end_time': a.end_time.isoformat(),
                'status': a.status,
                'therapist': f'{a.employee.user.first_name} {a.employee.user.last_name}' if a.employee and a.employee.user else '',
                'position_in_series': a.position_in_series or a.series_number,
                'soap_subjective': a.soap_subjective or '',
                'soap_objective': a.soap_objective or '',
                'therapy': a.therapy or ''
            } for a in g['appointments']]
        } for sid, g in series_groups.items()],
        'ungrouped': [{
            'id': a.id,
            'start_time': a.start_time.isoformat(),
            'end_time': a.end_time.isoformat(),
            'status': a.status,
            'title': a.title or '',
            'therapist': f'{a.employee.user.first_name} {a.employee.user.last_name}' if a.employee and a.employee.user else ''
        } for a in ungrouped],
        'available_series': [{
            'id': s.id,
            'title': s.title or (s.template.name if s.template else f'Serie {s.id}'),
            'status': s.status
        } for s in all_series]
    }
    return jsonify(result)
