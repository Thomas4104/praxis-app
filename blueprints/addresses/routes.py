"""Adressen-Blueprint: Verwaltung von Versicherungen, Aerzten und allgemeinen Kontakten
Cenplex Phase9: Kontakttypen, Arztsuche, Kontaktdetails, GLN/ZSR-Validierung"""
import json
import re
from datetime import datetime
from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from blueprints.addresses import addresses_bp
from models import db, InsuranceProvider, Doctor, Contact, Patient, TreatmentSeries
from utils.auth import check_org


# ============================================================
# Hilfsfunktionen: GLN/ZSR Validierung (Cenplex: Validator.cs)
# ============================================================

def validate_gln(gln):
    """GLN-Pruefziffer nach Modulo-10 (Cenplex-Algorithmus)
    13-stellige Nummer, letzte Stelle ist Pruefsumme"""
    if not gln or not re.match(r'^\d{13}$', gln):
        return False
    digits = [int(d) for d in gln[:12]]
    total = 0
    for i, d in enumerate(digits):
        # Ungerade Positionen (0-basiert) Gewicht 1, gerade Gewicht 3
        weight = 3 if i % 2 == 1 else 1
        total += d * weight
    check = (10 - (total % 10)) % 10
    return check == int(gln[12])


def validate_zsr(zsr):
    """ZSR-Nummer: 1 Buchstabe + 6 Ziffern (Cenplex: 7 Zeichen)"""
    if not zsr:
        return False
    return bool(re.match(r'^[A-Za-z]\d{6}$', zsr.strip()))


# ============================================================
# Kontakttypen-Konstanten (Cenplex: ContactType Enum)
# ============================================================
CONTACT_TYPES = {
    1: 'Versicherung',
    2: 'Arzt',
    3: 'Lieferant',
    4: 'Bank'
}

SALUTATIONS = {
    0: 'Herr',
    1: 'Frau',
    2: 'Herr Dr.',
    3: 'Frau Dr.',
    4: 'Eltern',
    5: 'Allgemein'
}

LAW_CODES = {
    1: 'KVG',
    2: 'UVG',
    3: 'IVG',
    4: 'VVG',
    5: 'MVG'
}

KANTONE = [
    'AG', 'AI', 'AR', 'BE', 'BL', 'BS', 'FR', 'GE', 'GL', 'GR',
    'JU', 'LU', 'NE', 'NW', 'OW', 'SG', 'SH', 'SO', 'SZ', 'TG',
    'TI', 'UR', 'VD', 'VS', 'ZG', 'ZH'
]


# ============================================================
# Adressuebersicht (Tabs: Versicherungen | Aerzte | Kontakte | Lieferanten | Banken)
# ============================================================

@addresses_bp.route('/')
@login_required
def index():
    """Adressuebersicht mit Tabs"""
    tab = request.args.get('tab', 'insurances')
    search = request.args.get('search', '').strip()
    show_inactive = request.args.get('show_inactive', '') == '1'
    page = request.args.get('page', 1, type=int)
    per_page = 25

    insurances = []
    doctors = []
    contacts = []
    vendors = []
    banks = []
    doctor_stats = {}
    total_pages = 1

    org_id = current_user.organization_id

    if tab == 'insurances':
        query = InsuranceProvider.query.filter_by(organization_id=org_id)
        if not show_inactive:
            query = query.filter_by(is_active=True)
        if search:
            query = query.filter(
                db.or_(
                    InsuranceProvider.name.ilike(f'%{search}%'),
                    InsuranceProvider.gln_number.ilike(f'%{search}%'),
                    InsuranceProvider.email.ilike(f'%{search}%')
                )
            )
        total = query.count()
        total_pages = (total + per_page - 1) // per_page
        insurances = query.order_by(InsuranceProvider.name).offset((page - 1) * per_page).limit(per_page).all()

    elif tab == 'doctors':
        query = Doctor.query.filter_by(organization_id=org_id)
        if not show_inactive:
            query = query.filter_by(is_active=True)
        if search:
            search_terms = search.split()
            for term in search_terms:
                query = query.filter(
                    db.or_(
                        Doctor.first_name.ilike(f'%{term}%'),
                        Doctor.last_name.ilike(f'%{term}%'),
                        Doctor.specialty.ilike(f'%{term}%'),
                        Doctor.gln_number.ilike(f'%{term}%'),
                        Doctor.company.ilike(f'%{term}%')
                    )
                )
        total = query.count()
        total_pages = (total + per_page - 1) // per_page
        doctors = query.order_by(Doctor.last_name, Doctor.first_name).offset((page - 1) * per_page).limit(per_page).all()

        # Zuweiserstatistik (Batch-Query statt N+1)
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
        query = Contact.query.filter_by(organization_id=org_id)
        if not show_inactive:
            query = query.filter_by(is_active=True)
        # Nur allgemeine Kontakte (nicht Lieferant/Bank)
        query = query.filter(db.or_(
            Contact.contact_type == 0,
            Contact.contact_type.is_(None)
        ))
        if search:
            search_terms = search.split()
            for term in search_terms:
                query = query.filter(
                    db.or_(
                        Contact.company_name.ilike(f'%{term}%'),
                        Contact.first_name.ilike(f'%{term}%'),
                        Contact.last_name.ilike(f'%{term}%'),
                        Contact.category.ilike(f'%{term}%'),
                        Contact.gln.ilike(f'%{term}%')
                    )
                )
        total = query.count()
        total_pages = (total + per_page - 1) // per_page
        contacts = query.order_by(Contact.company_name, Contact.last_name).offset((page - 1) * per_page).limit(per_page).all()

    elif tab == 'vendors':
        query = Contact.query.filter_by(organization_id=org_id, contact_type=3)
        if not show_inactive:
            query = query.filter_by(is_active=True)
        if search:
            query = query.filter(
                db.or_(
                    Contact.company_name.ilike(f'%{search}%'),
                    Contact.last_name.ilike(f'%{search}%'),
                    Contact.first_name.ilike(f'%{search}%')
                )
            )
        total = query.count()
        total_pages = (total + per_page - 1) // per_page
        vendors = query.order_by(Contact.company_name, Contact.last_name).offset((page - 1) * per_page).limit(per_page).all()

    elif tab == 'banks':
        query = Contact.query.filter_by(organization_id=org_id, contact_type=4)
        if not show_inactive:
            query = query.filter_by(is_active=True)
        if search:
            query = query.filter(
                db.or_(
                    Contact.company_name.ilike(f'%{search}%'),
                    Contact.last_name.ilike(f'%{search}%')
                )
            )
        total = query.count()
        total_pages = (total + per_page - 1) // per_page
        banks = query.order_by(Contact.company_name).offset((page - 1) * per_page).limit(per_page).all()

    return render_template('addresses/index.html',
                           tab=tab,
                           search=search,
                           show_inactive=show_inactive,
                           page=page,
                           total_pages=total_pages,
                           insurances=insurances,
                           doctors=doctors,
                           doctor_stats=doctor_stats,
                           contacts=contacts,
                           vendors=vendors,
                           banks=banks)


# ============================================================
# Versicherungen
# ============================================================

@addresses_bp.route('/insurances/new', methods=['GET', 'POST'])
@login_required
def create_insurance():
    """Neue Versicherung erstellen"""
    if request.method == 'POST':
        return _save_insurance(None)
    return render_template('addresses/insurance_form.html', insurance=None,
                           kantone=KANTONE, law_codes=LAW_CODES)


@addresses_bp.route('/insurances/<int:insurance_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_insurance(insurance_id):
    """Versicherung bearbeiten"""
    insurance = InsuranceProvider.query.get_or_404(insurance_id)
    check_org(insurance)
    if request.method == 'POST':
        return _save_insurance(insurance)
    return render_template('addresses/insurance_form.html', insurance=insurance,
                           kantone=KANTONE, law_codes=LAW_CODES)


@addresses_bp.route('/insurances/<int:insurance_id>')
@login_required
def insurance_detail(insurance_id):
    """Versicherung-Details (Cenplex: GetInsuranceContactDetails)"""
    insurance = InsuranceProvider.query.get_or_404(insurance_id)
    check_org(insurance)

    # Patienten-Anzahl mit dieser Versicherung
    patient_count = Patient.query.filter_by(
        organization_id=current_user.organization_id,
        insurance_id=insurance.id
    ).count()

    # Tiers Payant auswerten
    tiers_payant = []
    if insurance.supports_tiers_payant_json:
        try:
            tiers_payant = json.loads(insurance.supports_tiers_payant_json)
        except (json.JSONDecodeError, TypeError):
            pass

    return render_template('addresses/insurance_detail.html',
                           insurance=insurance,
                           patient_count=patient_count,
                           tiers_payant=tiers_payant,
                           law_codes=LAW_CODES)


def _save_insurance(insurance):
    """Speichert eine Versicherung mit allen Cenplex-Feldern"""
    name = request.form.get('name', '').strip()
    if not name:
        flash('Name ist ein Pflichtfeld.', 'error')
        return render_template('addresses/insurance_form.html', insurance=insurance,
                               kantone=KANTONE, law_codes=LAW_CODES)

    # GLN-Validierung (optional, aber wenn angegeben muss korrekt sein)
    gln = request.form.get('gln_number', '').strip()
    if gln and not validate_gln(gln):
        flash('GLN-Nummer ist ungueltig (13 Ziffern mit korrekter Pruefsumme erforderlich).', 'error')
        return render_template('addresses/insurance_form.html', insurance=insurance,
                               kantone=KANTONE, law_codes=LAW_CODES)

    recipient_gln = request.form.get('recipient_gln', '').strip()
    if recipient_gln and not validate_gln(recipient_gln):
        flash('Empfaenger-GLN ist ungueltig.', 'error')
        return render_template('addresses/insurance_form.html', insurance=insurance,
                               kantone=KANTONE, law_codes=LAW_CODES)

    is_new = insurance is None
    if is_new:
        insurance = InsuranceProvider(organization_id=current_user.organization_id)

    # Basis-Felder
    insurance.name = name
    insurance.gln_number = gln
    insurance.address = request.form.get('address', '').strip()
    insurance.city = request.form.get('city', '').strip()
    insurance.zip_code = request.form.get('zip_code', '').strip()
    insurance.phone = request.form.get('phone', '').strip()
    insurance.email = request.form.get('email', '').strip()
    insurance.fax = request.form.get('fax', '').strip()
    insurance.supports_electronic_billing = request.form.get('supports_electronic_billing') == 'on'

    # Erweiterte Cenplex-Felder
    insurance.ins_department = request.form.get('ins_department', '').strip()
    insurance.ins_postbox = request.form.get('ins_postbox', '').strip()
    insurance.ins_kanton = request.form.get('ins_kanton', '').strip()
    insurance.website = request.form.get('website', '').strip()
    insurance.recipient_gln = recipient_gln
    insurance.bag_number = request.form.get('bag_number', '').strip()
    insurance.law_code = request.form.get('law_code', '').strip()
    insurance.tarif_code = request.form.get('tarif_code', type=int) or None
    insurance.accept_kostengutsprache = request.form.get('accept_kostengutsprache') == 'on'
    insurance.email_gutsprache = request.form.get('email_gutsprache', '').strip()

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
    return render_template('addresses/doctor_form.html', doctor=None, kantone=KANTONE)


@addresses_bp.route('/doctors/<int:doctor_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_doctor(doctor_id):
    """Arzt bearbeiten"""
    doctor = Doctor.query.get_or_404(doctor_id)
    check_org(doctor)
    if request.method == 'POST':
        return _save_doctor(doctor)
    return render_template('addresses/doctor_form.html', doctor=doctor, kantone=KANTONE)


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

    # Expertise auswerten
    expertise_list = []
    if doctor.expertise:
        try:
            expertise_list = json.loads(doctor.expertise)
        except (json.JSONDecodeError, TypeError):
            expertise_list = [doctor.expertise]

    return render_template('addresses/doctor_detail.html',
                           doctor=doctor,
                           patient_count=patient_count,
                           series_count=series_count,
                           recent_series=recent_series,
                           expertise_list=expertise_list)


def _save_doctor(doctor):
    """Speichert einen Arzt mit allen Cenplex-Feldern"""
    last_name = request.form.get('last_name', '').strip()
    company = request.form.get('company', '').strip()

    # Cenplex-Validierung: Entweder Firma ODER Vor+Nachname
    if not last_name and not company:
        flash('Nachname oder Firmenname ist ein Pflichtfeld.', 'error')
        return render_template('addresses/doctor_form.html', doctor=doctor, kantone=KANTONE)

    # GLN-Validierung
    gln = request.form.get('gln_number', '').strip()
    if gln and not validate_gln(gln):
        flash('GLN-Nummer ist ungueltig (13 Ziffern mit korrekter Pruefsumme erforderlich).', 'error')
        return render_template('addresses/doctor_form.html', doctor=doctor, kantone=KANTONE)

    # ZSR-Validierung
    zsr = request.form.get('zsr_number', '').strip()
    if zsr and not validate_zsr(zsr):
        flash('ZSR-Nummer ist ungueltig (Format: 1 Buchstabe + 6 Ziffern, z.B. A123456).', 'error')
        return render_template('addresses/doctor_form.html', doctor=doctor, kantone=KANTONE)

    is_new = doctor is None
    if is_new:
        doctor = Doctor(organization_id=current_user.organization_id)

    # Basis-Felder
    doctor.salutation = request.form.get('salutation', '').strip()
    doctor.first_name = request.form.get('first_name', '').strip()
    doctor.last_name = last_name
    doctor.specialty = request.form.get('specialty', '')
    doctor.gln_number = gln
    doctor.zsr_number = zsr
    doctor.address = request.form.get('address', '').strip()
    doctor.city = request.form.get('city', '').strip()
    doctor.zip_code = request.form.get('zip_code', '').strip()
    doctor.phone = request.form.get('phone', '').strip()
    doctor.email = request.form.get('email', '').strip()
    doctor.fax = request.form.get('fax', '').strip()

    # Erweiterte Cenplex-Felder
    doctor.company = company
    doctor.department = request.form.get('department', '').strip()
    doctor.kanton = request.form.get('kanton', '').strip()
    doctor.country = request.form.get('country', 'CH').strip()
    doctor.mobile = request.form.get('mobile', '').strip()
    doctor.homepage = request.form.get('homepage', '').strip()
    doctor.postbox = request.form.get('postbox', '').strip()
    doctor.addressing = request.form.get('addressing', '').strip()
    doctor.description_text = request.form.get('description_text', '').strip()

    # Geschlecht (Cenplex: Synchronisation mit Anrede)
    sex_val = request.form.get('sex', '')
    doctor.sex = int(sex_val) if sex_val.isdigit() else None

    # Geburtstag
    birthday_str = request.form.get('birthday', '').strip()
    if birthday_str:
        try:
            doctor.birthday = datetime.strptime(birthday_str, '%Y-%m-%d').date()
        except ValueError:
            pass
    else:
        doctor.birthday = None

    # Expertise als JSON
    expertise_raw = request.form.get('expertise', '').strip()
    if expertise_raw:
        tags = [t.strip() for t in expertise_raw.split(',') if t.strip()]
        doctor.expertise = json.dumps(tags) if tags else None
    else:
        doctor.expertise = None

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
# Kontakte (inkl. Lieferanten und Banken)
# ============================================================

@addresses_bp.route('/contacts/new', methods=['GET', 'POST'])
@login_required
def create_contact():
    """Neuen Kontakt erstellen"""
    contact_type = request.args.get('type', 0, type=int)
    if request.method == 'POST':
        return _save_contact(None)
    return render_template('addresses/contact_form.html', contact=None,
                           default_type=contact_type,
                           contact_types=CONTACT_TYPES,
                           salutations=SALUTATIONS,
                           kantone=KANTONE,
                           law_codes=LAW_CODES)


@addresses_bp.route('/contacts/<int:contact_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_contact(contact_id):
    """Kontakt bearbeiten"""
    contact = Contact.query.get_or_404(contact_id)
    check_org(contact)
    if request.method == 'POST':
        return _save_contact(contact)
    return render_template('addresses/contact_form.html', contact=contact,
                           default_type=contact.contact_type or 0,
                           contact_types=CONTACT_TYPES,
                           salutations=SALUTATIONS,
                           kantone=KANTONE,
                           law_codes=LAW_CODES)


@addresses_bp.route('/contacts/<int:contact_id>')
@login_required
def contact_detail(contact_id):
    """Kontakt-Details (Cenplex: GetContactDetails)"""
    contact = Contact.query.get_or_404(contact_id)
    check_org(contact)

    # Referenzkontakt laden
    ref_contact = None
    if contact.reference_contact_id:
        ref_contact = Contact.query.get(contact.reference_contact_id)

    return render_template('addresses/contact_detail.html',
                           contact=contact,
                           ref_contact=ref_contact,
                           contact_types=CONTACT_TYPES,
                           salutations=SALUTATIONS,
                           law_codes=LAW_CODES)


def _save_contact(contact):
    """Speichert einen Kontakt mit allen Cenplex-Feldern"""
    company_name = request.form.get('company_name', '').strip()
    last_name = request.form.get('last_name', '').strip()
    first_name = request.form.get('first_name', '').strip()

    # Cenplex-Validierung: Firmenname ODER (Vorname + Nachname)
    if not company_name and not last_name:
        flash('Firmenname oder Nachname ist ein Pflichtfeld.', 'error')
        return render_template('addresses/contact_form.html', contact=contact,
                               default_type=request.form.get('contact_type', 0, type=int),
                               contact_types=CONTACT_TYPES,
                               salutations=SALUTATIONS,
                               kantone=KANTONE,
                               law_codes=LAW_CODES)

    # GLN-Validierung
    gln = request.form.get('gln', '').strip()
    if gln and not validate_gln(gln):
        flash('GLN-Nummer ist ungueltig.', 'error')
        return render_template('addresses/contact_form.html', contact=contact,
                               default_type=request.form.get('contact_type', 0, type=int),
                               contact_types=CONTACT_TYPES,
                               salutations=SALUTATIONS,
                               kantone=KANTONE,
                               law_codes=LAW_CODES)

    is_new = contact is None
    if is_new:
        contact = Contact(organization_id=current_user.organization_id)

    # Kontakttyp
    contact.contact_type = request.form.get('contact_type', 0, type=int)

    # Name-Felder
    contact.company_name = company_name
    contact.first_name = first_name
    contact.last_name = last_name
    contact.department = request.form.get('department', '').strip()
    contact.category = request.form.get('category', '').strip()

    # Anrede/Person
    sal_val = request.form.get('salutation', '')
    contact.salutation = int(sal_val) if sal_val.isdigit() else None
    sex_val = request.form.get('sex', '')
    contact.sex = int(sex_val) if sex_val.isdigit() else None
    birthday_str = request.form.get('birthday', '').strip()
    if birthday_str:
        try:
            contact.birthday = datetime.strptime(birthday_str, '%Y-%m-%d').date()
        except ValueError:
            pass
    else:
        contact.birthday = None

    # Adresse
    contact.address = request.form.get('address', '').strip()
    contact.postbox = request.form.get('postbox', '').strip()
    contact.zip_code = request.form.get('zip_code', '').strip()
    contact.city = request.form.get('city', '').strip()
    contact.contact_kanton = request.form.get('contact_kanton', '').strip()
    contact.contact_country = request.form.get('contact_country', 'CH').strip()

    # Kommunikation
    contact.phone = request.form.get('phone', '').strip()
    contact.contact_mobile = request.form.get('contact_mobile', '').strip()
    contact.fax = request.form.get('fax', '').strip()
    contact.email = request.form.get('email', '').strip()
    contact.homepage = request.form.get('homepage', '').strip()

    # Professionelle IDs
    contact.gln = gln
    contact.gln_receiver = request.form.get('gln_receiver', '').strip()
    contact.zsr = request.form.get('zsr', '').strip()

    # Versicherungs-/Fach-Felder
    law_val = request.form.get('law_code', '')
    contact.law_code = int(law_val) if law_val.isdigit() else None
    contact.accept_kostengutsprache = request.form.get('accept_kostengutsprache') == 'on'
    contact.email_gutsprache = request.form.get('email_gutsprache', '').strip()
    tarif_val = request.form.get('tarif_code', '')
    contact.tarif_code = int(tarif_val) if tarif_val.isdigit() else None

    # Sonstige
    contact.addressing = request.form.get('addressing', '').strip()
    contact.description_text = request.form.get('description_text', '').strip()
    contact.notes = request.form.get('notes', '').strip()
    contact.affiliate_id = request.form.get('affiliate_id', '').strip()

    # Referenzkontakt
    ref_id = request.form.get('reference_contact_id', '')
    contact.reference_contact_id = int(ref_id) if ref_id.isdigit() else None

    if is_new:
        db.session.add(contact)

    db.session.commit()
    flash('Kontakt erfolgreich gespeichert.', 'success')

    # Weiterleitung je nach Kontakttyp
    tab_map = {3: 'vendors', 4: 'banks'}
    tab = tab_map.get(contact.contact_type, 'contacts')
    return redirect(url_for('addresses.index', tab=tab))


@addresses_bp.route('/contacts/<int:contact_id>/toggle', methods=['POST'])
@login_required
def toggle_contact(contact_id):
    """Kontakt aktivieren/deaktivieren"""
    contact = Contact.query.get_or_404(contact_id)
    check_org(contact)
    contact.is_active = not contact.is_active
    db.session.commit()
    flash(f'Kontakt wurde {"aktiviert" if contact.is_active else "deaktiviert"}.', 'success')
    tab_map = {3: 'vendors', 4: 'banks'}
    tab = tab_map.get(contact.contact_type, 'contacts')
    return redirect(url_for('addresses.index', tab=tab))


# ============================================================================
# GLN/ZSR Online-Arztsuche
# ============================================================================

@addresses_bp.route('/api/lookup-gln')
@login_required
def api_lookup_gln():
    """Arzt-Lookup ueber GLN-Nummer"""
    gln = request.args.get('gln', '').strip()
    if not gln:
        return jsonify({'error': 'GLN-Nummer erforderlich'}), 400

    from services.swiss_registry_service import lookup_by_gln
    result, error = lookup_by_gln(gln)

    if error:
        return jsonify({'error': error}), 404
    return jsonify(result)


@addresses_bp.route('/api/lookup-zsr')
@login_required
def api_lookup_zsr():
    """Arzt-Lookup ueber ZSR-Nummer"""
    zsr = request.args.get('zsr', '').strip()
    if not zsr:
        return jsonify({'error': 'ZSR-Nummer erforderlich'}), 400

    from services.swiss_registry_service import lookup_by_zsr
    result, error = lookup_by_zsr(zsr)

    if error:
        return jsonify({'error': error}), 404
    return jsonify(result)


@addresses_bp.route('/api/search-practitioners')
@login_required
def api_search_practitioners():
    """Freie Suche nach Aerzten/Therapeuten (Cenplex: FindDoctors)"""
    name = request.args.get('q', '').strip()
    canton = request.args.get('canton', '').strip()

    if not name and not canton:
        return jsonify({'error': 'Mindestens Name oder Kanton angeben'}), 400

    from services.swiss_registry_service import search_practitioners
    results, error = search_practitioners(name=name, canton=canton)

    if error:
        return jsonify({'error': error, 'results': []}), 200
    return jsonify({'results': results})


@addresses_bp.route('/api/validate-gln')
@login_required
def api_validate_gln():
    """GLN-Nummer validieren (Cenplex: Mod-10 Pruefsumme)"""
    gln = request.args.get('gln', '').strip()
    if not gln:
        return jsonify({'valid': False, 'error': 'GLN-Nummer erforderlich'})
    valid = validate_gln(gln)
    return jsonify({'valid': valid, 'error': '' if valid else 'Ungueltige GLN-Pruefsumme'})


@addresses_bp.route('/api/validate-zsr')
@login_required
def api_validate_zsr():
    """ZSR-Nummer validieren (Format: 1 Buchstabe + 6 Ziffern)"""
    zsr = request.args.get('zsr', '').strip()
    if not zsr:
        return jsonify({'valid': False, 'error': 'ZSR-Nummer erforderlich'})
    valid = validate_zsr(zsr)
    return jsonify({'valid': valid, 'error': '' if valid else 'Ungueltiges ZSR-Format'})


# ============================================================
# Erweiterte API-Endpunkte (Cenplex: ContactService)
# ============================================================

@addresses_bp.route('/api/doctors/search')
@login_required
def api_search_doctors():
    """Arztsuche (Cenplex: FindDoctors) - Name, GLN, ZSR"""
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify([])

    org_id = current_user.organization_id

    # Zuerst in Doctor-Tabelle suchen
    doctors = Doctor.query.filter_by(organization_id=org_id).filter(
        db.or_(
            Doctor.first_name.ilike(f'%{q}%'),
            Doctor.last_name.ilike(f'%{q}%'),
            Doctor.gln_number.ilike(f'%{q}%'),
            Doctor.zsr_number.ilike(f'%{q}%'),
            Doctor.company.ilike(f'%{q}%')
        )
    ).limit(15).all()

    result = [{
        'id': d.id,
        'type': 'doctor',
        'name': f'{d.last_name}, {d.first_name}' if d.first_name else d.last_name,
        'company': d.company or '',
        'gln': d.gln_number or '',
        'zsr': d.zsr_number or '',
        'city': d.city or '',
        'phone': d.phone or '',
        'specialty': d.specialty or ''
    } for d in doctors]

    # Auch in Kontakten mit Typ=Arzt suchen (Cenplex: ContactType=2)
    contacts = Contact.query.filter_by(organization_id=org_id, contact_type=2).filter(
        db.or_(
            Contact.first_name.ilike(f'%{q}%'),
            Contact.last_name.ilike(f'%{q}%'),
            Contact.company_name.ilike(f'%{q}%'),
            Contact.gln.ilike(f'%{q}%')
        )
    ).limit(10).all()

    for c in contacts:
        result.append({
            'id': c.id,
            'type': 'contact',
            'name': c.company_name or f'{c.last_name}, {c.first_name}',
            'company': c.company_name or '',
            'gln': c.gln or '',
            'zsr': c.zsr or '',
            'city': c.city or '',
            'phone': c.phone or '',
            'specialty': ''
        })

    return jsonify(result)


@addresses_bp.route('/api/contacts/by-type')
@login_required
def api_contacts_by_type():
    """Kontakte nach Typ filtern (Cenplex: Typ 1=Versicherung, 2=Arzt, 3=Lieferant, 4=Bank)"""
    contact_type = request.args.get('type', type=int)
    org_id = current_user.organization_id

    query = Contact.query.filter_by(organization_id=org_id, is_deleted=False)
    if contact_type is not None:
        query = query.filter_by(contact_type=contact_type)

    contacts = query.order_by(Contact.company_name, Contact.last_name).limit(100).all()
    return jsonify([{
        'id': c.id,
        'name': c.company_name or f'{c.last_name or ""}, {c.first_name or ""}',
        'type': c.contact_type,
        'city': c.city or '',
        'email': c.email or '',
        'gln': c.gln or ''
    } for c in contacts])


@addresses_bp.route('/api/insurances/search')
@login_required
def api_search_insurances():
    """Versicherungssuche fuer Autocomplete"""
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify([])

    org_id = current_user.organization_id
    insurances = InsuranceProvider.query.filter_by(
        organization_id=org_id, is_active=True
    ).filter(
        db.or_(
            InsuranceProvider.name.ilike(f'%{q}%'),
            InsuranceProvider.gln_number.ilike(f'%{q}%')
        )
    ).limit(20).all()

    return jsonify([{
        'id': ins.id,
        'name': ins.name,
        'gln': ins.gln_number or '',
        'city': ins.city or '',
        'law_code': ins.law_code or ''
    } for ins in insurances])
