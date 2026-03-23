"""Routen fuer den Einstellungen-Bereich"""
import json
from datetime import datetime
from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from blueprints.settings import settings_bp
from models import db, Organization, User, Employee, Location, Permission, \
    AISettings, EmailTemplate, PrintTemplate, SystemSetting
from services.settings_service import get_setting, set_setting, get_settings_by_category, invalidate_cache
from utils.auth import check_org


# ============================================================
# Zugriffskontrolle
# ============================================================

def admin_required(f):
    """Decorator: Nur Admins duerfen zugreifen"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.role != 'admin':
            flash('Nur Administratoren haben Zugriff auf die Einstellungen.', 'error')
            return redirect(url_for('dashboard.index'))
        return f(*args, **kwargs)
    return decorated_function


# ============================================================
# Hauptseite mit Kategorien
# ============================================================

@settings_bp.route('/')
@login_required
@admin_required
def index():
    """Einstellungen-Hauptseite"""
    category = request.args.get('category', 'general')
    org = Organization.query.get(current_user.organization_id)

    if category == 'general':
        return _general_category(org)
    elif category == 'ai':
        return _ai_category(org)
    elif category == 'calendar':
        return _calendar_category(org)
    elif category == 'email':
        return _email_category(org)
    elif category == 'billing':
        return _billing_category(org)
    elif category == 'users':
        return _users_category(org)
    elif category == 'print_templates':
        return _print_templates_category(org)
    elif category == 'location_visibility':
        return _location_visibility_category(org)

    return _general_category(org)


# ============================================================
# Kategorie: Allgemein
# ============================================================

def _general_category(org):
    settings = get_settings_by_category(org.id, 'general')
    return render_template('settings/index.html', category='general', org=org,
                           settings=settings)


@settings_bp.route('/general/save', methods=['POST'])
@login_required
@admin_required
def save_general():
    """Allgemeine Einstellungen speichern"""
    org_id = current_user.organization_id

    set_setting(org_id, 'app_language', request.form.get('app_language', 'de'), 'string', 'general')
    set_setting(org_id, 'timezone', request.form.get('timezone', 'Europe/Zurich'), 'string', 'general')
    set_setting(org_id, 'date_format', request.form.get('date_format', 'DD.MM.YYYY'), 'string', 'general')
    set_setting(org_id, 'currency', request.form.get('currency', 'CHF'), 'string', 'general')

    flash('Allgemeine Einstellungen wurden gespeichert.', 'success')
    return redirect(url_for('settings.index', category='general'))


# ============================================================
# Kategorie: KI-Einstellungen
# ============================================================

def _ai_category(org):
    ai_settings = AISettings.query.filter_by(organization_id=org.id).first()
    if not ai_settings:
        ai_settings = AISettings(
            organization_id=org.id,
            intensity_level='normal',
            budget_monthly=100.0,
            budget_used=0.0,
            features_enabled_json=json.dumps({
                'chat_assistant': True,
                'auto_appointment_suggestions': True,
                'proactive_hints': True,
                'documentation_suggestions': True
            })
        )
        db.session.add(ai_settings)
        db.session.commit()

    features = {}
    if ai_settings.features_enabled_json:
        try:
            features = json.loads(ai_settings.features_enabled_json)
        except (json.JSONDecodeError, TypeError):
            pass

    return render_template('settings/index.html', category='ai', org=org,
                           ai_settings=ai_settings, features=features)


@settings_bp.route('/ai/save', methods=['POST'])
@login_required
@admin_required
def save_ai():
    """KI-Einstellungen speichern"""
    org_id = current_user.organization_id
    ai_settings = AISettings.query.filter_by(organization_id=org_id).first()
    if not ai_settings:
        ai_settings = AISettings(organization_id=org_id)
        db.session.add(ai_settings)

    ai_settings.intensity_level = request.form.get('intensity_level', 'normal')

    try:
        ai_settings.budget_monthly = float(request.form.get('budget_monthly', '100'))
    except ValueError:
        ai_settings.budget_monthly = 100.0

    features = {
        'chat_assistant': request.form.get('chat_assistant') == 'on',
        'auto_appointment_suggestions': request.form.get('auto_appointment_suggestions') == 'on',
        'proactive_hints': request.form.get('proactive_hints') == 'on',
        'documentation_suggestions': request.form.get('documentation_suggestions') == 'on'
    }
    ai_settings.features_enabled_json = json.dumps(features)

    db.session.commit()
    flash('KI-Einstellungen wurden gespeichert.', 'success')
    return redirect(url_for('settings.index', category='ai'))


# ============================================================
# Kategorie: Kalender
# ============================================================

def _calendar_category(org):
    settings = get_settings_by_category(org.id, 'calendar')

    # Terminart-Farben laden
    appointment_colors = get_setting(org.id, 'appointment_colors', {
        'treatment': '#4a90d9',
        'initial': '#27ae60',
        'followup': '#f39c12',
        'group': '#9b59b6',
        'domicile': '#e67e22',
        'cancelled': '#e74c3c'
    })

    # Termin-Anzeige-Optionen laden
    appointment_display = get_setting(org.id, 'appointment_display', {
        'patient_name': True,
        'appointment_type': True,
        'time': True,
        'room': True,
        'status_icon': True
    })

    return render_template('settings/index.html', category='calendar', org=org,
                           settings=settings, appointment_colors=appointment_colors,
                           appointment_display=appointment_display)


@settings_bp.route('/calendar/save', methods=['POST'])
@login_required
@admin_required
def save_calendar():
    """Kalender-Einstellungen speichern"""
    org_id = current_user.organization_id

    set_setting(org_id, 'calendar_time_grid', request.form.get('time_grid', '15'), 'integer', 'calendar')
    set_setting(org_id, 'calendar_day_start', request.form.get('day_start', '07:00'), 'string', 'calendar')
    set_setting(org_id, 'calendar_day_end', request.form.get('day_end', '19:00'), 'string', 'calendar')
    set_setting(org_id, 'calendar_default_duration', request.form.get('default_duration', '30'), 'integer', 'calendar')

    # Termin-Anzeige-Optionen
    display = {
        'patient_name': request.form.get('display_patient_name') == 'on',
        'appointment_type': request.form.get('display_appointment_type') == 'on',
        'time': request.form.get('display_time') == 'on',
        'room': request.form.get('display_room') == 'on',
        'status_icon': request.form.get('display_status_icon') == 'on'
    }
    set_setting(org_id, 'appointment_display', display, 'json', 'calendar')

    # Terminart-Farben
    colors = {
        'treatment': request.form.get('color_treatment', '#4a90d9'),
        'initial': request.form.get('color_initial', '#27ae60'),
        'followup': request.form.get('color_followup', '#f39c12'),
        'group': request.form.get('color_group', '#9b59b6'),
        'domicile': request.form.get('color_domicile', '#e67e22'),
        'cancelled': request.form.get('color_cancelled', '#e74c3c')
    }
    set_setting(org_id, 'appointment_colors', colors, 'json', 'calendar')

    flash('Kalender-Einstellungen wurden gespeichert.', 'success')
    return redirect(url_for('settings.index', category='calendar'))


# ============================================================
# Kategorie: E-Mail
# ============================================================

def _email_category(org):
    settings = get_settings_by_category(org.id, 'email')
    templates = EmailTemplate.query.filter_by(
        organization_id=org.id
    ).order_by(EmailTemplate.template_type, EmailTemplate.name).all()

    return render_template('settings/index.html', category='email', org=org,
                           settings=settings, email_templates=templates)


@settings_bp.route('/email/save', methods=['POST'])
@login_required
@admin_required
def save_email():
    """E-Mail-Einstellungen speichern"""
    org_id = current_user.organization_id

    set_setting(org_id, 'email_sender_address', request.form.get('sender_address', ''), 'string', 'email')
    set_setting(org_id, 'email_sender_name', request.form.get('sender_name', ''), 'string', 'email')
    set_setting(org_id, 'email_signature', request.form.get('signature', ''), 'string', 'email')
    set_setting(org_id, 'email_auto_reminder', request.form.get('auto_reminder') == 'on', 'boolean', 'email')
    set_setting(org_id, 'email_reminder_hours', request.form.get('reminder_hours', '24'), 'integer', 'email')

    flash('E-Mail-Einstellungen wurden gespeichert.', 'success')
    return redirect(url_for('settings.index', category='email'))


@settings_bp.route('/email/templates/new', methods=['POST'])
@login_required
@admin_required
def create_email_template():
    """Neue E-Mail-Vorlage erstellen"""
    org_id = current_user.organization_id

    name = request.form.get('name', '').strip()
    if not name:
        flash('Name ist ein Pflichtfeld.', 'error')
        return redirect(url_for('settings.index', category='email'))

    template = EmailTemplate(
        organization_id=org_id,
        name=name,
        template_type=request.form.get('template_type', 'reminder'),
        subject=request.form.get('subject', '').strip(),
        body_html=request.form.get('body_html', '').strip(),
        placeholders_json=json.dumps([
            '{patient_name}', '{termin_datum}', '{termin_zeit}',
            '{therapeut_name}', '{praxis_name}', '{praxis_telefon}'
        ])
    )
    db.session.add(template)
    db.session.commit()

    flash(f'E-Mail-Vorlage "{name}" wurde erstellt.', 'success')
    return redirect(url_for('settings.index', category='email'))


@settings_bp.route('/email/templates/<int:template_id>/edit', methods=['POST'])
@login_required
@admin_required
def edit_email_template(template_id):
    """E-Mail-Vorlage bearbeiten"""
    template = EmailTemplate.query.get_or_404(template_id)
    check_org(template)

    template.name = request.form.get('name', template.name).strip()
    template.template_type = request.form.get('template_type', template.template_type)
    template.subject = request.form.get('subject', '').strip()
    template.body_html = request.form.get('body_html', '').strip()

    db.session.commit()
    flash(f'E-Mail-Vorlage "{template.name}" wurde aktualisiert.', 'success')
    return redirect(url_for('settings.index', category='email'))


@settings_bp.route('/email/templates/<int:template_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_email_template(template_id):
    """E-Mail-Vorlage loeschen"""
    template = EmailTemplate.query.get_or_404(template_id)
    check_org(template)
    name = template.name
    db.session.delete(template)
    db.session.commit()

    flash(f'E-Mail-Vorlage "{name}" wurde gelöscht.', 'success')
    return redirect(url_for('settings.index', category='email'))


@settings_bp.route('/email/templates/<int:template_id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_email_template(template_id):
    """E-Mail-Vorlage aktivieren/deaktivieren"""
    template = EmailTemplate.query.get_or_404(template_id)
    check_org(template)
    template.is_active = not template.is_active
    db.session.commit()

    status = 'aktiviert' if template.is_active else 'deaktiviert'
    flash(f'E-Mail-Vorlage "{template.name}" wurde {status}.', 'success')
    return redirect(url_for('settings.index', category='email'))


# ============================================================
# Kategorie: Abrechnung
# ============================================================

def _billing_category(org):
    settings = get_settings_by_category(org.id, 'billing')
    return render_template('settings/index.html', category='billing', org=org,
                           settings=settings)


@settings_bp.route('/billing/save', methods=['POST'])
@login_required
@admin_required
def save_billing():
    """Abrechnungs-Einstellungen speichern"""
    org_id = current_user.organization_id

    set_setting(org_id, 'billing_default_model', request.form.get('default_model', 'tiers_garant'), 'string', 'billing')
    set_setting(org_id, 'billing_payment_term', request.form.get('payment_term', '30'), 'integer', 'billing')
    set_setting(org_id, 'billing_invoice_format', request.form.get('invoice_format', 'RE-{JAHR}-{NR}'), 'string', 'billing')
    set_setting(org_id, 'billing_next_invoice_number', request.form.get('next_invoice_number', '1'), 'integer', 'billing')

    # Mahnwesen
    set_setting(org_id, 'dunning_1_days', request.form.get('dunning_1_days', '30'), 'integer', 'billing')
    set_setting(org_id, 'dunning_2_days', request.form.get('dunning_2_days', '60'), 'integer', 'billing')
    set_setting(org_id, 'dunning_3_days', request.form.get('dunning_3_days', '90'), 'integer', 'billing')
    set_setting(org_id, 'dunning_1_fee', request.form.get('dunning_1_fee', '0'), 'float', 'billing')
    set_setting(org_id, 'dunning_2_fee', request.form.get('dunning_2_fee', '20'), 'float', 'billing')
    set_setting(org_id, 'dunning_3_fee', request.form.get('dunning_3_fee', '50'), 'float', 'billing')
    set_setting(org_id, 'dunning_1_text', request.form.get('dunning_1_text', ''), 'string', 'billing')
    set_setting(org_id, 'dunning_2_text', request.form.get('dunning_2_text', ''), 'string', 'billing')
    set_setting(org_id, 'dunning_3_text', request.form.get('dunning_3_text', ''), 'string', 'billing')

    flash('Abrechnungs-Einstellungen wurden gespeichert.', 'success')
    return redirect(url_for('settings.index', category='billing'))


# ============================================================
# Kategorie: Benutzer & Rollen
# ============================================================

def _users_category(org):
    users = User.query.filter_by(
        organization_id=org.id
    ).order_by(User.last_name, User.first_name).all()

    # Berechtigungen laden
    permissions = Permission.query.filter_by(organization_id=org.id).all()
    permissions_matrix = {}
    for p in permissions:
        if p.role not in permissions_matrix:
            permissions_matrix[p.role] = {}
        if p.module not in permissions_matrix[p.role]:
            permissions_matrix[p.role][p.module] = {}
        permissions_matrix[p.role][p.module][p.action] = p.is_allowed

    modules = ['dashboard', 'kalender', 'patienten', 'mitarbeiter', 'behandlung',
               'abrechnung', 'produkte', 'ressourcen', 'adressen', 'einstellungen']
    actions = ['lesen', 'erstellen', 'bearbeiten', 'loeschen']
    roles = ['admin', 'therapist', 'reception']

    return render_template('settings/index.html', category='users', org=org,
                           users=users, permissions_matrix=permissions_matrix,
                           modules=modules, actions=actions, roles=roles)


@settings_bp.route('/users/permissions/save', methods=['POST'])
@login_required
@admin_required
def save_permissions():
    """Rollen-Berechtigungen speichern"""
    modules = ['dashboard', 'kalender', 'patienten', 'mitarbeiter', 'behandlung',
               'abrechnung', 'produkte', 'ressourcen', 'adressen', 'einstellungen']
    actions = ['lesen', 'erstellen', 'bearbeiten', 'loeschen']
    roles = ['therapist', 'reception']  # Admin hat immer alle Rechte

    for role in roles:
        for module in modules:
            for action in actions:
                key = f'perm_{role}_{module}_{action}'
                is_allowed = request.form.get(key) == 'on'

                perm = Permission.query.filter_by(
                    organization_id=current_user.organization_id,
                    role=role, module=module, action=action
                ).first()

                if perm:
                    perm.is_allowed = is_allowed
                else:
                    perm = Permission(
                        organization_id=current_user.organization_id,
                        role=role, module=module, action=action,
                        is_allowed=is_allowed
                    )
                    db.session.add(perm)

    db.session.commit()
    flash('Berechtigungen wurden gespeichert.', 'success')
    return redirect(url_for('settings.index', category='users'))


# ============================================================
# Kategorie: Druckvorlagen
# ============================================================

def _print_templates_category(org):
    templates = PrintTemplate.query.filter_by(
        organization_id=org.id
    ).order_by(PrintTemplate.template_type, PrintTemplate.name).all()

    return render_template('settings/index.html', category='print_templates', org=org,
                           print_templates=templates)


@settings_bp.route('/print-templates/new', methods=['POST'])
@login_required
@admin_required
def create_print_template():
    """Neue Druckvorlage erstellen"""
    org_id = current_user.organization_id

    name = request.form.get('name', '').strip()
    if not name:
        flash('Name ist ein Pflichtfeld.', 'error')
        return redirect(url_for('settings.index', category='print_templates'))

    template = PrintTemplate(
        organization_id=org_id,
        name=name,
        template_type=request.form.get('template_type', 'invoice'),
        body_html=request.form.get('body_html', '').strip()
    )
    db.session.add(template)
    db.session.commit()

    flash(f'Druckvorlage "{name}" wurde erstellt.', 'success')
    return redirect(url_for('settings.index', category='print_templates'))


@settings_bp.route('/print-templates/<int:template_id>/edit', methods=['POST'])
@login_required
@admin_required
def edit_print_template(template_id):
    """Druckvorlage bearbeiten"""
    template = PrintTemplate.query.get_or_404(template_id)
    check_org(template)

    template.name = request.form.get('name', template.name).strip()
    template.template_type = request.form.get('template_type', template.template_type)
    template.body_html = request.form.get('body_html', '').strip()

    db.session.commit()
    flash(f'Druckvorlage "{template.name}" wurde aktualisiert.', 'success')
    return redirect(url_for('settings.index', category='print_templates'))


@settings_bp.route('/print-templates/<int:template_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_print_template(template_id):
    """Druckvorlage loeschen"""
    template = PrintTemplate.query.get_or_404(template_id)
    check_org(template)
    name = template.name
    db.session.delete(template)
    db.session.commit()

    flash(f'Druckvorlage "{name}" wurde gelöscht.', 'success')
    return redirect(url_for('settings.index', category='print_templates'))


@settings_bp.route('/print-templates/<int:template_id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_print_template(template_id):
    """Druckvorlage aktivieren/deaktivieren"""
    template = PrintTemplate.query.get_or_404(template_id)
    check_org(template)
    template.is_active = not template.is_active
    db.session.commit()

    status = 'aktiviert' if template.is_active else 'deaktiviert'
    flash(f'Druckvorlage "{template.name}" wurde {status}.', 'success')
    return redirect(url_for('settings.index', category='print_templates'))


# ============================================================
# Kategorie: Standort-Sichtbarkeit
# ============================================================

def _location_visibility_category(org):
    employees = Employee.query.filter_by(
        organization_id=org.id, is_active=True
    ).order_by(Employee.id).all()

    locations = Location.query.filter_by(
        organization_id=org.id, is_active=True
    ).order_by(Location.name).all()

    # Aktuelle Sichtbarkeits-Matrix laden
    visibility = get_setting(org.id, 'location_visibility', {})

    return render_template('settings/index.html', category='location_visibility', org=org,
                           employees=employees, locations=locations, visibility=visibility)


@settings_bp.route('/location-visibility/save', methods=['POST'])
@login_required
@admin_required
def save_location_visibility():
    """Standort-Sichtbarkeit speichern"""
    org_id = current_user.organization_id

    employees = Employee.query.filter_by(
        organization_id=org_id, is_active=True
    ).all()
    locations = Location.query.filter_by(
        organization_id=org_id, is_active=True
    ).all()

    visibility = {}
    for emp in employees:
        emp_locations = []
        for loc in locations:
            key = f'vis_{emp.id}_{loc.id}'
            if request.form.get(key) == 'on':
                emp_locations.append(loc.id)
        visibility[str(emp.id)] = emp_locations

    set_setting(org_id, 'location_visibility', visibility, 'json', 'location_visibility')

    flash('Standort-Sichtbarkeit wurde gespeichert.', 'success')
    return redirect(url_for('settings.index', category='location_visibility'))


# ============================================================
# API-Endpunkte fuer AJAX
# ============================================================

@settings_bp.route('/api/email-template/<int:template_id>')
@login_required
@admin_required
def api_get_email_template(template_id):
    """E-Mail-Vorlage als JSON zurueckgeben"""
    template = EmailTemplate.query.get_or_404(template_id)
    check_org(template)
    placeholders = []
    if template.placeholders_json:
        try:
            placeholders = json.loads(template.placeholders_json)
        except (json.JSONDecodeError, TypeError):
            pass

    return jsonify({
        'id': template.id,
        'name': template.name,
        'template_type': template.template_type,
        'subject': template.subject,
        'body_html': template.body_html,
        'placeholders': placeholders,
        'is_active': template.is_active
    })


@settings_bp.route('/api/print-template/<int:template_id>')
@login_required
@admin_required
def api_get_print_template(template_id):
    """Druckvorlage als JSON zurueckgeben"""
    template = PrintTemplate.query.get_or_404(template_id)
    check_org(template)
    return jsonify({
        'id': template.id,
        'name': template.name,
        'template_type': template.template_type,
        'body_html': template.body_html,
        'is_active': template.is_active
    })
