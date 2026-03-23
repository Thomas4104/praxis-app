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


# ============================================================
# Patientenuebersicht
# ============================================================

@patients_bp.route('/')
@login_required
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

    # Letzte Behandlung pro Patient laden
    last_appointments = {}
    for p in patients:
        last_appt = Appointment.query.filter_by(patient_id=p.id) \
            .filter(Appointment.start_time <= datetime.now()) \
            .order_by(Appointment.start_time.desc()).first()
        if last_appt:
            last_appointments[p.id] = last_appt

    # Filter-Daten
    insurances = InsuranceProvider.query.filter_by(is_active=True) \
        .order_by(InsuranceProvider.name).all()
    locations = Location.query.filter_by(is_active=True) \
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
def create():
    """Neuen Patienten erstellen"""
    if request.method == 'POST':
        return _save_patient(None)

    insurances = InsuranceProvider.query.filter_by(is_active=True) \
        .order_by(InsuranceProvider.name).all()
    doctors = Doctor.query.filter_by(is_active=True) \
        .order_by(Doctor.last_name).all()
    therapists = Employee.query.filter_by(is_active=True).all()
    therapists = [t for t in therapists if t.user and t.user.role == 'therapist']

    return render_template('patients/form.html',
                           patient=None,
                           insurances=insurances,
                           doctors=doctors,
                           therapists=therapists)


@patients_bp.route('/<int:patient_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(patient_id):
    """Patient bearbeiten"""
    patient = Patient.query.get_or_404(patient_id)

    if request.method == 'POST':
        return _save_patient(patient)

    insurances = InsuranceProvider.query.filter_by(is_active=True) \
        .order_by(InsuranceProvider.name).all()
    doctors = Doctor.query.filter_by(is_active=True) \
        .order_by(Doctor.last_name).all()
    therapists = Employee.query.filter_by(is_active=True).all()
    therapists = [t for t in therapists if t.user and t.user.role == 'therapist']

    return render_template('patients/form.html',
                           patient=patient,
                           insurances=insurances,
                           doctors=doctors,
                           therapists=therapists)


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
        insurances = InsuranceProvider.query.filter_by(is_active=True) \
            .order_by(InsuranceProvider.name).all()
        doctors = Doctor.query.filter_by(is_active=True) \
            .order_by(Doctor.last_name).all()
        therapists = Employee.query.filter_by(is_active=True).all()
        therapists = [t for t in therapists if t.user and t.user.role == 'therapist']
        return render_template('patients/form.html',
                               patient=patient,
                               insurances=insurances,
                               doctors=doctors,
                               therapists=therapists)

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

    if is_new:
        db.session.add(patient)

    db.session.commit()
    flash('Patient erfolgreich gespeichert.' if not is_new else 'Patient erfolgreich erstellt.', 'success')
    return redirect(url_for('patients.detail', patient_id=patient.id))


# ============================================================
# Patientendetail
# ============================================================

@patients_bp.route('/<int:patient_id>')
@login_required
def detail(patient_id):
    """Patientendetail mit Tabs"""
    patient = Patient.query.get_or_404(patient_id)
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

    # Serien-Fortschritt berechnen
    series_progress = {}
    for s in all_series:
        appt_count = Appointment.query.filter_by(series_id=s.id).count()
        total = s.template.num_appointments if s.template else 0
        series_progress[s.id] = {'done': appt_count, 'total': total}

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
def toggle_active(patient_id):
    """Patient aktivieren/deaktivieren (Soft-Delete)"""
    patient = Patient.query.get_or_404(patient_id)
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
    directory = os.path.dirname(doc.file_path)
    return send_from_directory(directory, doc.filename,
                               download_name=doc.original_filename,
                               as_attachment=True)


@patients_bp.route('/documents/<int:doc_id>/delete', methods=['POST'])
@login_required
def delete_document(doc_id):
    """Dokument loeschen"""
    doc = PatientDocument.query.get_or_404(doc_id)
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
def merge():
    """Zwei Patienten zusammenfuehren (nur Admin)"""
    if current_user.role != 'admin':
        flash('Nur Administratoren können Patienten zusammenführen.', 'error')
        return redirect(url_for('patients.index'))

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
