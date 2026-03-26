"""Patienten-Blueprint: Verwaltung von Patienten, Dokumenten und Patientenakten"""
import os
import json
import uuid
import re
from datetime import datetime, date, timedelta
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

    # Suche (Name, Geburtsdatum, Telefon, Patientennummer)
    if search:
        search_lower = search.lower()
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
            query = query.filter(
                db.or_(
                    Patient.first_name.ilike(f'%{search}%'),
                    Patient.last_name.ilike(f'%{search}%'),
                    Patient.patient_number.ilike(f'%{search}%'),
                    Patient.phone.ilike(f'%{search}%'),
                    Patient.mobile.ilike(f'%{search}%'),
                    (Patient.first_name + ' ' + Patient.last_name).ilike(f'%{search}%')
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

    # AHV-Nummer Validierung
    ahv = request.form.get('ahv_number', '').strip()
    if ahv and not re.match(r'^756\.\d{4}\.\d{4}\.\d{2}$', ahv):
        errors.append('AHV-Nummer muss im Format 756.XXXX.XXXX.XX sein.')

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

    # Kontakt
    patient.phone = request.form.get('phone', '').strip()
    patient.mobile = request.form.get('mobile', '').strip()
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
    patient.kvg_model = int(request.form.get('kvg_model', 0))
    patient.kvg_accident_coverage = int(request.form.get('kvg_accident_coverage', 0))
    patient.card_id = request.form.get('card_id', '')
    patient.card_expiry = parse_date(request.form.get('card_expiry'))

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
