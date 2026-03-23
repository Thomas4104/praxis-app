"""Adressen-Blueprint: Verwaltung von Versicherungen, Aerzten und allgemeinen Kontakten"""
import json
from datetime import datetime
from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from blueprints.addresses import addresses_bp
from models import db, InsuranceProvider, Doctor, Contact, Patient, TreatmentSeries, Organization
from utils.auth import check_org


# ============================================================
# Adressuebersicht (Tabs: Versicherungen | Aerzte | Kontakte)
# ============================================================

@addresses_bp.route('/')
@login_required
def index():
    """Adressuebersicht mit Tabs"""
    tab = request.args.get('tab', 'insurances')
    search = request.args.get('search', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 25

    insurances = []
    doctors = []
    contacts = []
    total_pages = 1

    org_id = current_user.organization_id

    if tab == 'insurances':
        query = InsuranceProvider.query.filter_by(organization_id=org_id, is_active=True)
        if search:
            query = query.filter(
                db.or_(
                    InsuranceProvider.name.ilike(f'%{search}%'),
                    InsuranceProvider.gln_number.ilike(f'%{search}%')
                )
            )
        total = query.count()
        total_pages = (total + per_page - 1) // per_page
        insurances = query.order_by(InsuranceProvider.name).offset((page - 1) * per_page).limit(per_page).all()

    elif tab == 'doctors':
        query = Doctor.query.filter_by(organization_id=org_id, is_active=True)
        if search:
            query = query.filter(
                db.or_(
                    Doctor.first_name.ilike(f'%{search}%'),
                    Doctor.last_name.ilike(f'%{search}%'),
                    Doctor.specialty.ilike(f'%{search}%'),
                    Doctor.gln_number.ilike(f'%{search}%')
                )
            )
        total = query.count()
        total_pages = (total + per_page - 1) // per_page
        doctors = query.order_by(Doctor.last_name, Doctor.first_name).offset((page - 1) * per_page).limit(per_page).all()

        # Zuweiserstatistik (Batch-Query statt N+1)
        doctor_stats = {}
        if doctors:
            from sqlalchemy import func
            doctor_ids = [doc.id for doc in doctors]
            stats = db.session.query(
                TreatmentSeries.prescribing_doctor_id,
                func.count(TreatmentSeries.id)
            ).filter(
                TreatmentSeries.prescribing_doctor_id.in_(doctor_ids)
            ).group_by(TreatmentSeries.prescribing_doctor_id).all()
            doctor_stats = dict(stats)

    elif tab == 'contacts':
        query = Contact.query.filter_by(
            organization_id=current_user.organization_id, is_active=True)
        if search:
            query = query.filter(
                db.or_(
                    Contact.company_name.ilike(f'%{search}%'),
                    Contact.first_name.ilike(f'%{search}%'),
                    Contact.last_name.ilike(f'%{search}%'),
                    Contact.category.ilike(f'%{search}%')
                )
            )
        total = query.count()
        total_pages = (total + per_page - 1) // per_page
        contacts = query.order_by(Contact.company_name, Contact.last_name).offset((page - 1) * per_page).limit(per_page).all()

    return render_template('addresses/index.html',
                           tab=tab,
                           search=search,
                           page=page,
                           total_pages=total_pages,
                           insurances=insurances,
                           doctors=doctors,
                           doctor_stats=doctor_stats if tab == 'doctors' else {},
                           contacts=contacts)


# ============================================================
# Versicherungen
# ============================================================

@addresses_bp.route('/insurances/new', methods=['GET', 'POST'])
@login_required
def create_insurance():
    """Neue Versicherung erstellen"""
    if request.method == 'POST':
        return _save_insurance(None)
    return render_template('addresses/insurance_form.html', insurance=None)


@addresses_bp.route('/insurances/<int:insurance_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_insurance(insurance_id):
    """Versicherung bearbeiten"""
    insurance = InsuranceProvider.query.get_or_404(insurance_id)
    check_org(insurance)
    if request.method == 'POST':
        return _save_insurance(insurance)
    return render_template('addresses/insurance_form.html', insurance=insurance)


def _save_insurance(insurance):
    """Speichert eine Versicherung"""
    name = request.form.get('name', '').strip()
    if not name:
        flash('Name ist ein Pflichtfeld.', 'error')
        return render_template('addresses/insurance_form.html', insurance=insurance)

    is_new = insurance is None
    if is_new:
        insurance = InsuranceProvider(organization_id=current_user.organization_id)

    insurance.name = name
    insurance.gln_number = request.form.get('gln_number', '').strip()
    insurance.address = request.form.get('address', '').strip()
    insurance.city = request.form.get('city', '').strip()
    insurance.zip_code = request.form.get('zip_code', '').strip()
    insurance.phone = request.form.get('phone', '').strip()
    insurance.email = request.form.get('email', '').strip()
    insurance.fax = request.form.get('fax', '').strip()
    insurance.supports_electronic_billing = request.form.get('supports_electronic_billing') == 'on'

    # Tiers Payant Tariftypen
    tiers_payant = request.form.getlist('tiers_payant')
    insurance.supports_tiers_payant_json = json.dumps(tiers_payant) if tiers_payant else None

    if is_new:
        db.session.add(insurance)

    db.session.commit()
    flash('Versicherung erfolgreich gespeichert.', 'success')
    return redirect(url_for('addresses.index', tab='insurances'))


@addresses_bp.route('/insurances/<int:insurance_id>/toggle', methods=['POST'])
@login_required
def toggle_insurance(insurance_id):
    """Versicherung aktivieren/deaktivieren"""
    insurance = InsuranceProvider.query.get_or_404(insurance_id)
    check_org(insurance)
    insurance.is_active = not insurance.is_active
    db.session.commit()
    flash(f'Versicherung wurde {"aktiviert" if insurance.is_active else "deaktiviert"}.', 'success')
    return redirect(url_for('addresses.index', tab='insurances'))


# ============================================================
# Aerzte
# ============================================================

@addresses_bp.route('/doctors/new', methods=['GET', 'POST'])
@login_required
def create_doctor():
    """Neuen Arzt erstellen"""
    if request.method == 'POST':
        return _save_doctor(None)
    return render_template('addresses/doctor_form.html', doctor=None)


@addresses_bp.route('/doctors/<int:doctor_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_doctor(doctor_id):
    """Arzt bearbeiten"""
    doctor = Doctor.query.get_or_404(doctor_id)
    check_org(doctor)
    if request.method == 'POST':
        return _save_doctor(doctor)
    return render_template('addresses/doctor_form.html', doctor=doctor)


@addresses_bp.route('/doctors/<int:doctor_id>')
@login_required
def doctor_detail(doctor_id):
    """Arzt-Details mit Zuweiserstatistik"""
    doctor = Doctor.query.get_or_404(doctor_id)
    check_org(doctor)
    patient_count = TreatmentSeries.query.filter_by(prescribing_doctor_id=doctor.id) \
        .with_entities(TreatmentSeries.patient_id).distinct().count()
    series_count = TreatmentSeries.query.filter_by(prescribing_doctor_id=doctor.id).count()
    recent_series = TreatmentSeries.query.filter_by(prescribing_doctor_id=doctor.id) \
        .order_by(TreatmentSeries.created_at.desc()).limit(10).all()

    return render_template('addresses/doctor_detail.html',
                           doctor=doctor,
                           patient_count=patient_count,
                           series_count=series_count,
                           recent_series=recent_series)


def _save_doctor(doctor):
    """Speichert einen Arzt"""
    last_name = request.form.get('last_name', '').strip()
    if not last_name:
        flash('Nachname ist ein Pflichtfeld.', 'error')
        return render_template('addresses/doctor_form.html', doctor=doctor)

    is_new = doctor is None
    if is_new:
        doctor = Doctor(organization_id=current_user.organization_id)

    doctor.salutation = request.form.get('salutation', '').strip()
    doctor.first_name = request.form.get('first_name', '').strip()
    doctor.last_name = last_name
    doctor.specialty = request.form.get('specialty', '')
    doctor.gln_number = request.form.get('gln_number', '').strip()
    doctor.zsr_number = request.form.get('zsr_number', '').strip()
    doctor.address = request.form.get('address', '').strip()
    doctor.city = request.form.get('city', '').strip()
    doctor.zip_code = request.form.get('zip_code', '').strip()
    doctor.phone = request.form.get('phone', '').strip()
    doctor.email = request.form.get('email', '').strip()
    doctor.fax = request.form.get('fax', '').strip()

    if is_new:
        db.session.add(doctor)

    db.session.commit()
    flash('Arzt erfolgreich gespeichert.', 'success')
    return redirect(url_for('addresses.index', tab='doctors'))


@addresses_bp.route('/doctors/<int:doctor_id>/toggle', methods=['POST'])
@login_required
def toggle_doctor(doctor_id):
    """Arzt aktivieren/deaktivieren"""
    doctor = Doctor.query.get_or_404(doctor_id)
    check_org(doctor)
    doctor.is_active = not doctor.is_active
    db.session.commit()
    flash(f'Arzt wurde {"aktiviert" if doctor.is_active else "deaktiviert"}.', 'success')
    return redirect(url_for('addresses.index', tab='doctors'))


# ============================================================
# Kontakte
# ============================================================

@addresses_bp.route('/contacts/new', methods=['GET', 'POST'])
@login_required
def create_contact():
    """Neuen Kontakt erstellen"""
    if request.method == 'POST':
        return _save_contact(None)
    return render_template('addresses/contact_form.html', contact=None)


@addresses_bp.route('/contacts/<int:contact_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_contact(contact_id):
    """Kontakt bearbeiten"""
    contact = Contact.query.get_or_404(contact_id)
    check_org(contact)
    if request.method == 'POST':
        return _save_contact(contact)
    return render_template('addresses/contact_form.html', contact=contact)


def _save_contact(contact):
    """Speichert einen Kontakt"""
    company_name = request.form.get('company_name', '').strip()
    last_name = request.form.get('last_name', '').strip()

    if not company_name and not last_name:
        flash('Firmenname oder Nachname ist ein Pflichtfeld.', 'error')
        return render_template('addresses/contact_form.html', contact=contact)

    is_new = contact is None
    if is_new:
        contact = Contact(organization_id=current_user.organization_id)

    contact.company_name = company_name
    contact.first_name = request.form.get('first_name', '').strip()
    contact.last_name = last_name
    contact.category = request.form.get('category', '').strip()
    contact.address = request.form.get('address', '').strip()
    contact.city = request.form.get('city', '').strip()
    contact.zip_code = request.form.get('zip_code', '').strip()
    contact.phone = request.form.get('phone', '').strip()
    contact.email = request.form.get('email', '').strip()
    contact.notes = request.form.get('notes', '').strip()

    if is_new:
        db.session.add(contact)

    db.session.commit()
    flash('Kontakt erfolgreich gespeichert.', 'success')
    return redirect(url_for('addresses.index', tab='contacts'))


@addresses_bp.route('/contacts/<int:contact_id>/toggle', methods=['POST'])
@login_required
def toggle_contact(contact_id):
    """Kontakt aktivieren/deaktivieren"""
    contact = Contact.query.get_or_404(contact_id)
    check_org(contact)
    contact.is_active = not contact.is_active
    db.session.commit()
    flash(f'Kontakt wurde {"aktiviert" if contact.is_active else "deaktiviert"}.', 'success')
    return redirect(url_for('addresses.index', tab='contacts'))
