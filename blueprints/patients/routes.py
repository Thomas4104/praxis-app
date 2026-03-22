# Patienten-Routen: CRUD, Suche, Details

from datetime import datetime
from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from blueprints.patients import patients_bp
from models import db, Patient, Appointment, TreatmentSeries
from sqlalchemy import or_


@patients_bp.route('/')
@login_required
def index():
    """Patientenliste mit Suche."""
    search = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)

    query = Patient.query.filter_by(is_active=True)

    if search:
        s = f'%{search}%'
        query = query.filter(or_(
            Patient.first_name.ilike(s),
            Patient.last_name.ilike(s),
            Patient.phone.ilike(s),
            Patient.mobile.ilike(s),
            Patient.email.ilike(s),
        ))

    patienten = query.order_by(Patient.last_name, Patient.first_name).paginate(
        page=page, per_page=20, error_out=False
    )
    return render_template('patients/index.html', patienten=patienten, search=search)


@patients_bp.route('/neu', methods=['GET', 'POST'])
@login_required
def create():
    """Neuen Patienten erstellen."""
    if request.method == 'POST':
        org_id = 1
        if current_user.employee:
            org_id = current_user.employee.organization_id

        patient = Patient(
            organization_id=org_id,
            first_name=request.form.get('first_name', '').strip(),
            last_name=request.form.get('last_name', '').strip(),
            gender=request.form.get('gender', ''),
            phone=request.form.get('phone', '').strip(),
            mobile=request.form.get('mobile', '').strip(),
            email=request.form.get('email', '').strip(),
            address=request.form.get('address', '').strip(),
            insurance_number=request.form.get('insurance_number', '').strip(),
            ahv_number=request.form.get('ahv_number', '').strip(),
            notes=request.form.get('notes', '').strip(),
        )

        dob = request.form.get('date_of_birth', '').strip()
        if dob:
            patient.date_of_birth = datetime.strptime(dob, '%Y-%m-%d').date()

        db.session.add(patient)
        db.session.commit()
        flash(f'Patient {patient.full_name} erstellt', 'success')
        return redirect(url_for('patients.detail', id=patient.id))

    return render_template('patients/form.html', patient=None)


@patients_bp.route('/<int:id>')
@login_required
def detail(id):
    """Patientendetails anzeigen."""
    patient = Patient.query.get_or_404(id)

    # Nächste Termine
    naechste_termine = Appointment.query.filter(
        Appointment.patient_id == patient.id,
        Appointment.start_time >= datetime.now(),
        Appointment.status != 'cancelled'
    ).order_by(Appointment.start_time).limit(10).all()

    # Letzte Termine
    letzte_termine = Appointment.query.filter(
        Appointment.patient_id == patient.id,
        Appointment.start_time < datetime.now(),
    ).order_by(Appointment.start_time.desc()).limit(10).all()

    return render_template('patients/detail.html',
                           patient=patient,
                           naechste_termine=naechste_termine,
                           letzte_termine=letzte_termine)


@patients_bp.route('/<int:id>/bearbeiten', methods=['GET', 'POST'])
@login_required
def edit(id):
    """Patient bearbeiten."""
    patient = Patient.query.get_or_404(id)

    if request.method == 'POST':
        patient.first_name = request.form.get('first_name', '').strip()
        patient.last_name = request.form.get('last_name', '').strip()
        patient.gender = request.form.get('gender', '')
        patient.phone = request.form.get('phone', '').strip()
        patient.mobile = request.form.get('mobile', '').strip()
        patient.email = request.form.get('email', '').strip()
        patient.address = request.form.get('address', '').strip()
        patient.insurance_number = request.form.get('insurance_number', '').strip()
        patient.ahv_number = request.form.get('ahv_number', '').strip()
        patient.notes = request.form.get('notes', '').strip()

        dob = request.form.get('date_of_birth', '').strip()
        if dob:
            patient.date_of_birth = datetime.strptime(dob, '%Y-%m-%d').date()

        db.session.commit()
        flash(f'Patient {patient.full_name} aktualisiert', 'success')
        return redirect(url_for('patients.detail', id=patient.id))

    return render_template('patients/form.html', patient=patient)


@patients_bp.route('/api/search')
@login_required
def api_search():
    """API-Endpoint für Patienten-Suche (z.B. für Autocomplete)."""
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify([])

    s = f'%{q}%'
    patienten = Patient.query.filter(
        Patient.is_active == True,
        or_(
            Patient.first_name.ilike(s),
            Patient.last_name.ilike(s),
            (Patient.first_name + ' ' + Patient.last_name).ilike(s),
        )
    ).limit(10).all()

    return jsonify([{
        'id': p.id,
        'name': p.full_name,
        'geburtsdatum': p.date_of_birth.strftime('%d.%m.%Y') if p.date_of_birth else '',
    } for p in patienten])
