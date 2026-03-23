import json
import re
from datetime import datetime, date
from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from blueprints.practice import practice_bp
from models import db, Organization, Location, BankAccount, Holiday, TreatmentSeriesTemplate, TaxPointValue, InsuranceProvider


# ============================================================
# Praxis-Uebersicht (Tabs)
# ============================================================

@practice_bp.route('/')
@login_required
def index():
    """Praxis-Uebersicht mit Tabs"""
    tab = request.args.get('tab', 'base')
    org = Organization.query.get(current_user.organization_id)

    if tab == 'base':
        return render_template('practice/index.html', tab=tab, org=org)
    elif tab == 'locations':
        return _locations_tab(org)
    elif tab == 'opening_hours':
        return _opening_hours_tab(org)
    elif tab == 'holidays':
        return _holidays_tab(org)
    elif tab == 'bank_accounts':
        return _bank_accounts_tab(org)
    elif tab == 'templates':
        return _templates_tab(org)
    elif tab == 'tax_points':
        return _tax_points_tab(org)

    return render_template('practice/index.html', tab='base', org=org)


def _locations_tab(org):
    status = request.args.get('status', 'active')
    query = Location.query.filter_by(organization_id=org.id)
    if status == 'active':
        query = query.filter_by(is_active=True)
    elif status == 'inactive':
        query = query.filter_by(is_active=False)
    locations = query.order_by(Location.name).all()
    return render_template('practice/index.html', tab='locations', org=org,
                           locations=locations, status=status)


def _opening_hours_tab(org):
    opening_hours = {}
    if org.opening_hours_json:
        try:
            opening_hours = json.loads(org.opening_hours_json)
        except (json.JSONDecodeError, TypeError):
            pass
    return render_template('practice/index.html', tab='opening_hours', org=org,
                           opening_hours=opening_hours)


def _holidays_tab(org):
    year = request.args.get('year', date.today().year, type=int)
    holidays = Holiday.query.filter_by(organization_id=org.id).filter(
        db.extract('year', Holiday.date) == year
    ).order_by(Holiday.date).all()
    locations = Location.query.filter_by(organization_id=org.id, is_active=True).all()
    return render_template('practice/index.html', tab='holidays', org=org,
                           holidays=holidays, year=year, locations=locations)


def _bank_accounts_tab(org):
    accounts = BankAccount.query.filter_by(
        organization_id=org.id, is_active=True
    ).order_by(BankAccount.bank_name).all()
    return render_template('practice/index.html', tab='bank_accounts', org=org,
                           bank_accounts=accounts)


def _templates_tab(org):
    status = request.args.get('status', 'active')
    query = TreatmentSeriesTemplate.query.filter_by(organization_id=org.id)
    if status == 'active':
        query = query.filter_by(is_active=True)
    elif status == 'inactive':
        query = query.filter_by(is_active=False)
    templates = query.order_by(TreatmentSeriesTemplate.name).all()
    locations = Location.query.filter_by(organization_id=org.id, is_active=True).all()
    return render_template('practice/index.html', tab='templates', org=org,
                           templates=templates, locations=locations, status=status)


def _tax_points_tab(org):
    tax_points = TaxPointValue.query.filter_by(
        organization_id=org.id
    ).order_by(TaxPointValue.tariff_type, TaxPointValue.valid_from.desc()).all()
    insurers = InsuranceProvider.query.filter_by(is_active=True).all()
    return render_template('practice/index.html', tab='tax_points', org=org,
                           tax_points=tax_points, insurers=insurers)


# ============================================================
# Basisdaten bearbeiten
# ============================================================

@practice_bp.route('/base/edit', methods=['POST'])
@login_required
def edit_base():
    """Basisdaten der Organisation bearbeiten"""
    if current_user.role != 'admin':
        flash('Nur Administratoren dürfen die Basisdaten bearbeiten.', 'error')
        return redirect(url_for('practice.index', tab='base'))

    org = Organization.query.get(current_user.organization_id)

    org.name = request.form.get('name', '').strip()
    org.address = request.form.get('address', '').strip()
    org.city = request.form.get('city', '').strip()
    org.zip_code = request.form.get('zip_code', '').strip()
    org.phone = request.form.get('phone', '').strip()
    org.email = request.form.get('email', '').strip()
    org.zsr_number = request.form.get('zsr_number', '').strip()
    org.gln_number = request.form.get('gln_number', '').strip()
    org.nif_number = request.form.get('nif_number', '').strip()
    org.uid_number = request.form.get('uid_number', '').strip()
    org.contact_person = request.form.get('contact_person', '').strip()
    org.default_language = request.form.get('default_language', 'de').strip()

    if not org.name:
        flash('Organisationsname ist ein Pflichtfeld.', 'error')
        return redirect(url_for('practice.index', tab='base'))

    db.session.commit()
    flash('Basisdaten wurden erfolgreich gespeichert.', 'success')
    return redirect(url_for('practice.index', tab='base'))


# ============================================================
# Standorte
# ============================================================

@practice_bp.route('/locations/new', methods=['GET', 'POST'])
@login_required
def create_location():
    """Neuen Standort erstellen"""
    if request.method == 'POST':
        return _save_location(None)
    return render_template('practice/location_form.html', location=None)


@practice_bp.route('/locations/<int:location_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_location(location_id):
    """Standort bearbeiten"""
    location = Location.query.get_or_404(location_id)
    if request.method == 'POST':
        return _save_location(location)
    return render_template('practice/location_form.html', location=location)


@practice_bp.route('/locations/<int:location_id>/toggle', methods=['POST'])
@login_required
def toggle_location(location_id):
    """Standort aktivieren/deaktivieren"""
    location = Location.query.get_or_404(location_id)
    location.is_active = not location.is_active
    db.session.commit()
    status_text = 'aktiviert' if location.is_active else 'deaktiviert'
    flash(f'Standort "{location.name}" wurde {status_text}.', 'success')
    return redirect(url_for('practice.index', tab='locations'))


def _save_location(location):
    """Speichert einen Standort"""
    name = request.form.get('name', '').strip()
    errors = []
    if not name:
        errors.append('Name ist ein Pflichtfeld.')
    if errors:
        for e in errors:
            flash(e, 'error')
        return render_template('practice/location_form.html', location=location)

    is_new = location is None
    if is_new:
        location = Location(organization_id=current_user.organization_id)

    location.name = name
    location.address = request.form.get('address', '').strip()
    location.city = request.form.get('city', '').strip()
    location.zip_code = request.form.get('zip_code', '').strip()
    location.phone = request.form.get('phone', '').strip()
    location.email = request.form.get('email', '').strip()

    # Oeffnungszeiten aus Formular
    oeffnungszeiten = {}
    tage = ['montag', 'dienstag', 'mittwoch', 'donnerstag', 'freitag', 'samstag', 'sonntag']
    for tag in tage:
        geschlossen = request.form.get(f'{tag}_geschlossen')
        if geschlossen:
            oeffnungszeiten[tag] = None
        else:
            von = request.form.get(f'{tag}_von', '').strip()
            bis = request.form.get(f'{tag}_bis', '').strip()
            if von and bis:
                oeffnungszeiten[tag] = {'von': von, 'bis': bis}
            else:
                oeffnungszeiten[tag] = None

    if any(v is not None for v in oeffnungszeiten.values()):
        location.opening_hours_json = json.dumps(oeffnungszeiten)

    location.is_active = request.form.get('is_active') == 'on'

    if is_new:
        db.session.add(location)
    db.session.commit()

    flash(f'Standort "{location.name}" wurde erfolgreich gespeichert.', 'success')
    return redirect(url_for('practice.index', tab='locations'))


# ============================================================
# Oeffnungszeiten (Organisation)
# ============================================================

@practice_bp.route('/opening-hours/save', methods=['POST'])
@login_required
def save_opening_hours():
    """Oeffnungszeiten der Organisation speichern"""
    if current_user.role != 'admin':
        flash('Nur Administratoren dürfen die Öffnungszeiten bearbeiten.', 'error')
        return redirect(url_for('practice.index', tab='opening_hours'))

    org = Organization.query.get(current_user.organization_id)

    oeffnungszeiten = {}
    tage = ['montag', 'dienstag', 'mittwoch', 'donnerstag', 'freitag', 'samstag', 'sonntag']
    for tag in tage:
        geschlossen = request.form.get(f'{tag}_geschlossen')
        if geschlossen:
            oeffnungszeiten[tag] = None
        else:
            von = request.form.get(f'{tag}_von', '').strip()
            bis = request.form.get(f'{tag}_bis', '').strip()
            if von and bis:
                oeffnungszeiten[tag] = {'von': von, 'bis': bis}
            else:
                oeffnungszeiten[tag] = None

    org.opening_hours_json = json.dumps(oeffnungszeiten)
    db.session.commit()

    flash('Öffnungszeiten wurden erfolgreich gespeichert.', 'success')
    return redirect(url_for('practice.index', tab='opening_hours'))


# ============================================================
# Feiertage
# ============================================================

@practice_bp.route('/holidays/add', methods=['POST'])
@login_required
def add_holiday():
    """Feiertag hinzufuegen"""
    name = request.form.get('name', '').strip()
    date_str = request.form.get('date', '').strip()
    location_id = request.form.get('location_id', '').strip()

    if not name or not date_str:
        flash('Name und Datum sind Pflichtfelder.', 'error')
        return redirect(url_for('practice.index', tab='holidays'))

    try:
        holiday_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        flash('Ungültiges Datum.', 'error')
        return redirect(url_for('practice.index', tab='holidays'))

    holiday = Holiday(
        organization_id=current_user.organization_id,
        name=name,
        date=holiday_date,
        location_id=int(location_id) if location_id else None
    )
    db.session.add(holiday)
    db.session.commit()

    flash(f'Feiertag "{name}" wurde hinzugefügt.', 'success')
    return redirect(url_for('practice.index', tab='holidays', year=holiday_date.year))


@practice_bp.route('/holidays/<int:holiday_id>/delete', methods=['POST'])
@login_required
def delete_holiday(holiday_id):
    """Feiertag loeschen"""
    holiday = Holiday.query.get_or_404(holiday_id)
    year = holiday.date.year
    name = holiday.name
    db.session.delete(holiday)
    db.session.commit()

    flash(f'Feiertag "{name}" wurde gelöscht.', 'success')
    return redirect(url_for('practice.index', tab='holidays', year=year))


@practice_bp.route('/holidays/load-canton', methods=['POST'])
@login_required
def load_canton_holidays():
    """Vordefinierte Feiertage fuer einen Kanton laden"""
    canton = request.form.get('canton', '').strip()
    year = request.form.get('year', date.today().year, type=int)

    if not canton:
        flash('Bitte wählen Sie einen Kanton aus.', 'error')
        return redirect(url_for('practice.index', tab='holidays', year=year))

    # Schweizer Feiertage nach Kanton
    feiertage = _get_canton_holidays(canton, year)

    count = 0
    for name, d in feiertage:
        # Pruefen ob schon vorhanden
        existing = Holiday.query.filter_by(
            organization_id=current_user.organization_id,
            date=d,
            name=name
        ).first()
        if not existing:
            db.session.add(Holiday(
                organization_id=current_user.organization_id,
                name=name,
                date=d,
                canton=canton
            ))
            count += 1

    db.session.commit()
    flash(f'{count} Feiertage für Kanton {canton.upper()} ({year}) wurden geladen.', 'success')
    return redirect(url_for('practice.index', tab='holidays', year=year))


def _get_canton_holidays(canton, year):
    """Gibt die Feiertage fuer einen Schweizer Kanton zurueck"""
    from datetime import timedelta

    # Ostersonntag berechnen (Gauss-Algorithmus)
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    easter = date(year, month, day)

    # Gemeinsame Feiertage
    common = [
        ('Neujahr', date(year, 1, 1)),
        ('Karfreitag', easter - timedelta(days=2)),
        ('Ostermontag', easter + timedelta(days=1)),
        ('Auffahrt', easter + timedelta(days=39)),
        ('Pfingstmontag', easter + timedelta(days=50)),
        ('Bundesfeiertag', date(year, 8, 1)),
        ('Weihnachten', date(year, 12, 25)),
    ]

    # Kantonsspezifische Feiertage
    cantonal = {
        'zh': [
            ('Tag der Arbeit', date(year, 5, 1)),
            ('Stephanstag', date(year, 12, 26)),
        ],
        'be': [
            ('Berchtoldstag', date(year, 1, 2)),
            ('Stephanstag', date(year, 12, 26)),
        ],
        'ag': [
            ('Berchtoldstag', date(year, 1, 2)),
            ('Stephanstag', date(year, 12, 26)),
        ],
        'sg': [
            ('Allerheiligen', date(year, 11, 1)),
            ('Stephanstag', date(year, 12, 26)),
        ],
        'lu': [
            ('Berchtoldstag', date(year, 1, 2)),
            ('Fronleichnam', easter + timedelta(days=60)),
            ('Mariä Himmelfahrt', date(year, 8, 15)),
            ('Allerheiligen', date(year, 11, 1)),
            ('Mariä Empfängnis', date(year, 12, 8)),
            ('Stephanstag', date(year, 12, 26)),
        ],
        'bs': [
            ('Tag der Arbeit', date(year, 5, 1)),
            ('Stephanstag', date(year, 12, 26)),
        ],
        'bl': [
            ('Tag der Arbeit', date(year, 5, 1)),
            ('Stephanstag', date(year, 12, 26)),
        ],
        'so': [
            ('Berchtoldstag', date(year, 1, 2)),
            ('Tag der Arbeit', date(year, 5, 1)),
        ],
        'gr': [
            ('Stephanstag', date(year, 12, 26)),
        ],
        'tg': [
            ('Berchtoldstag', date(year, 1, 2)),
            ('Tag der Arbeit', date(year, 5, 1)),
            ('Stephanstag', date(year, 12, 26)),
        ],
    }

    result = common + cantonal.get(canton.lower(), [])
    result.sort(key=lambda x: x[1])
    return result


# ============================================================
# Bankkonten
# ============================================================

@practice_bp.route('/bank-accounts/new', methods=['GET', 'POST'])
@login_required
def create_bank_account():
    """Neues Bankkonto erstellen"""
    if request.method == 'POST':
        return _save_bank_account(None)
    return render_template('practice/bank_account_form.html', account=None)


@practice_bp.route('/bank-accounts/<int:account_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_bank_account(account_id):
    """Bankkonto bearbeiten"""
    account = BankAccount.query.get_or_404(account_id)
    if request.method == 'POST':
        return _save_bank_account(account)
    return render_template('practice/bank_account_form.html', account=account)


@practice_bp.route('/bank-accounts/<int:account_id>/toggle', methods=['POST'])
@login_required
def toggle_bank_account(account_id):
    """Bankkonto aktivieren/deaktivieren"""
    account = BankAccount.query.get_or_404(account_id)
    account.is_active = not account.is_active
    db.session.commit()
    status_text = 'aktiviert' if account.is_active else 'deaktiviert'
    flash(f'Bankkonto "{account.account_name or account.bank_name}" wurde {status_text}.', 'success')
    return redirect(url_for('practice.index', tab='bank_accounts'))


@practice_bp.route('/bank-accounts/<int:account_id>/set-default', methods=['POST'])
@login_required
def set_default_bank_account(account_id):
    """Bankkonto als Standard setzen"""
    # Alle anderen auf nicht-Standard setzen
    BankAccount.query.filter_by(
        organization_id=current_user.organization_id
    ).update({'is_default': False})

    account = BankAccount.query.get_or_404(account_id)
    account.is_default = True
    db.session.commit()

    flash(f'"{account.account_name or account.bank_name}" ist jetzt das Standardkonto.', 'success')
    return redirect(url_for('practice.index', tab='bank_accounts'))


def _validate_iban(iban):
    """Validiert eine Schweizer IBAN"""
    iban = iban.replace(' ', '').upper()
    if not re.match(r'^CH\d{2}[A-Z0-9]{17}$', iban):
        return False, 'IBAN muss mit CH beginnen, gefolgt von 2 Prüfziffern und 17 Zeichen.'
    # Numerische Validierung (Modulo 97)
    rearranged = iban[4:] + iban[:4]
    numeric = ''
    for ch in rearranged:
        if ch.isdigit():
            numeric += ch
        else:
            numeric += str(ord(ch) - 55)
    if int(numeric) % 97 != 1:
        return False, 'IBAN-Prüfsumme ist ungültig.'
    return True, ''


def _save_bank_account(account):
    """Speichert ein Bankkonto"""
    bank_name = request.form.get('bank_name', '').strip()
    iban = request.form.get('iban', '').strip().replace(' ', '').upper()
    qr_iban = request.form.get('qr_iban', '').strip().replace(' ', '').upper()

    errors = []
    if not bank_name:
        errors.append('Bankname ist ein Pflichtfeld.')
    if not iban:
        errors.append('IBAN ist ein Pflichtfeld.')
    else:
        valid, msg = _validate_iban(iban)
        if not valid:
            errors.append(msg)

    if qr_iban:
        valid, msg = _validate_iban(qr_iban)
        if not valid:
            errors.append(f'QR-IBAN: {msg}')

    if errors:
        for e in errors:
            flash(e, 'error')
        return render_template('practice/bank_account_form.html', account=account)

    is_new = account is None
    if is_new:
        account = BankAccount(organization_id=current_user.organization_id)

    account.bank_name = bank_name
    account.iban = iban
    account.qr_iban = qr_iban or None
    account.bic_swift = request.form.get('bic_swift', '').strip() or None
    account.account_name = request.form.get('account_name', '').strip() or None

    if request.form.get('is_default') == 'on':
        # Alle anderen auf nicht-Standard
        BankAccount.query.filter_by(
            organization_id=current_user.organization_id
        ).update({'is_default': False})
        account.is_default = True

    if is_new:
        db.session.add(account)
    db.session.commit()

    flash(f'Bankkonto "{account.account_name or account.bank_name}" wurde erfolgreich gespeichert.', 'success')
    return redirect(url_for('practice.index', tab='bank_accounts'))


# ============================================================
# Serienvorlagen
# ============================================================

@practice_bp.route('/templates/new', methods=['GET', 'POST'])
@login_required
def create_template():
    """Neue Serienvorlage erstellen"""
    if request.method == 'POST':
        return _save_template(None)
    locations = Location.query.filter_by(
        organization_id=current_user.organization_id, is_active=True
    ).all()
    return render_template('practice/template_form.html', template=None, locations=locations)


@practice_bp.route('/templates/<int:template_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_template(template_id):
    """Serienvorlage bearbeiten"""
    template = TreatmentSeriesTemplate.query.get_or_404(template_id)
    if request.method == 'POST':
        return _save_template(template)
    locations = Location.query.filter_by(
        organization_id=current_user.organization_id, is_active=True
    ).all()
    return render_template('practice/template_form.html', template=template, locations=locations)


@practice_bp.route('/templates/<int:template_id>/toggle', methods=['POST'])
@login_required
def toggle_template(template_id):
    """Serienvorlage aktivieren/deaktivieren"""
    template = TreatmentSeriesTemplate.query.get_or_404(template_id)
    template.is_active = not template.is_active
    db.session.commit()
    status_text = 'aktiviert' if template.is_active else 'deaktiviert'
    flash(f'Vorlage "{template.name}" wurde {status_text}.', 'success')
    return redirect(url_for('practice.index', tab='templates'))


def _save_template(template):
    """Speichert eine Serienvorlage"""
    name = request.form.get('name', '').strip()
    errors = []
    if not name:
        errors.append('Name ist ein Pflichtfeld.')
    if errors:
        for e in errors:
            flash(e, 'error')
        locations = Location.query.filter_by(
            organization_id=current_user.organization_id, is_active=True
        ).all()
        return render_template('practice/template_form.html', template=template, locations=locations)

    is_new = template is None
    if is_new:
        template = TreatmentSeriesTemplate(organization_id=current_user.organization_id)

    template.name = name
    template.short_name = request.form.get('short_name', '').strip() or None
    template.tariff_type = request.form.get('tariff_type', '').strip() or None

    try:
        template.num_appointments = int(request.form.get('num_appointments', '9'))
    except ValueError:
        template.num_appointments = 9

    try:
        template.duration_minutes = int(request.form.get('duration_minutes', '30'))
    except ValueError:
        template.duration_minutes = 30

    try:
        template.min_interval_days = int(request.form.get('min_interval_days', '1'))
    except ValueError:
        template.min_interval_days = 1

    loc_id = request.form.get('default_location_id', '')
    template.default_location_id = int(loc_id) if loc_id else None

    template.group_therapy = request.form.get('group_therapy') == 'on'
    try:
        template.max_group_size = int(request.form.get('max_group_size', '0')) or None
    except ValueError:
        template.max_group_size = None

    template.requires_resource = request.form.get('requires_resource') == 'on'
    template.resource_type = request.form.get('resource_type', '').strip() or None

    try:
        val = request.form.get('auto_billing_after', '')
        template.auto_billing_after = int(val) if val else None
    except ValueError:
        template.auto_billing_after = None

    template.cancellation_fee_type = request.form.get('cancellation_fee_type', '').strip() or None
    try:
        val = request.form.get('cancellation_fee_amount', '')
        template.cancellation_fee_amount = float(val) if val else None
    except ValueError:
        template.cancellation_fee_amount = None

    template.is_active = request.form.get('is_active') == 'on'

    if is_new:
        db.session.add(template)
    db.session.commit()

    flash(f'Vorlage "{template.name}" wurde erfolgreich gespeichert.', 'success')
    return redirect(url_for('practice.index', tab='templates'))


# ============================================================
# Taxpunktwerte
# ============================================================

@practice_bp.route('/tax-points/add', methods=['POST'])
@login_required
def add_tax_point():
    """Taxpunktwert hinzufuegen"""
    tariff_type = request.form.get('tariff_type', '').strip()
    value_str = request.form.get('value', '').strip()
    valid_from_str = request.form.get('valid_from', '').strip()

    errors = []
    if not tariff_type:
        errors.append('Tarif-Typ ist ein Pflichtfeld.')
    if not value_str:
        errors.append('Wert ist ein Pflichtfeld.')
    if not valid_from_str:
        errors.append('Gültig ab ist ein Pflichtfeld.')

    if errors:
        for e in errors:
            flash(e, 'error')
        return redirect(url_for('practice.index', tab='tax_points'))

    try:
        value = float(value_str)
    except ValueError:
        flash('Ungültiger Wert.', 'error')
        return redirect(url_for('practice.index', tab='tax_points'))

    try:
        valid_from = datetime.strptime(valid_from_str, '%Y-%m-%d').date()
    except ValueError:
        flash('Ungültiges Datum.', 'error')
        return redirect(url_for('practice.index', tab='tax_points'))

    valid_to_str = request.form.get('valid_to', '').strip()
    valid_to = None
    if valid_to_str:
        try:
            valid_to = datetime.strptime(valid_to_str, '%Y-%m-%d').date()
        except ValueError:
            pass

    canton = request.form.get('canton', '').strip() or None
    insurer_id_str = request.form.get('insurer_id', '').strip()
    insurer_id = int(insurer_id_str) if insurer_id_str else None

    tp = TaxPointValue(
        organization_id=current_user.organization_id,
        tariff_type=tariff_type,
        value=value,
        valid_from=valid_from,
        valid_to=valid_to,
        canton=canton,
        insurer_id=insurer_id
    )
    db.session.add(tp)
    db.session.commit()

    flash(f'Taxpunktwert für {tariff_type} (CHF {value:.2f}) wurde hinzugefügt.', 'success')
    return redirect(url_for('practice.index', tab='tax_points'))


@practice_bp.route('/tax-points/<int:tp_id>/delete', methods=['POST'])
@login_required
def delete_tax_point(tp_id):
    """Taxpunktwert loeschen"""
    tp = TaxPointValue.query.get_or_404(tp_id)
    tariff = tp.tariff_type
    db.session.delete(tp)
    db.session.commit()

    flash(f'Taxpunktwert für {tariff} wurde gelöscht.', 'success')
    return redirect(url_for('practice.index', tab='tax_points'))


@practice_bp.route('/tax-points/<int:tp_id>/edit', methods=['POST'])
@login_required
def edit_tax_point(tp_id):
    """Taxpunktwert bearbeiten"""
    tp = TaxPointValue.query.get_or_404(tp_id)

    tariff_type = request.form.get('tariff_type', '').strip()
    value_str = request.form.get('value', '').strip()
    valid_from_str = request.form.get('valid_from', '').strip()

    if tariff_type:
        tp.tariff_type = tariff_type
    if value_str:
        try:
            tp.value = float(value_str)
        except ValueError:
            pass
    if valid_from_str:
        try:
            tp.valid_from = datetime.strptime(valid_from_str, '%Y-%m-%d').date()
        except ValueError:
            pass

    valid_to_str = request.form.get('valid_to', '').strip()
    if valid_to_str:
        try:
            tp.valid_to = datetime.strptime(valid_to_str, '%Y-%m-%d').date()
        except ValueError:
            pass
    else:
        tp.valid_to = None

    tp.canton = request.form.get('canton', '').strip() or None
    insurer_id_str = request.form.get('insurer_id', '').strip()
    tp.insurer_id = int(insurer_id_str) if insurer_id_str else None

    db.session.commit()
    flash(f'Taxpunktwert für {tp.tariff_type} wurde aktualisiert.', 'success')
    return redirect(url_for('practice.index', tab='tax_points'))
