"""Routen fuer den Einstellungen-Bereich"""
import json
from datetime import datetime
from flask import render_template, request, redirect, url_for, flash, jsonify, abort
from flask_login import login_required, current_user
from blueprints.settings import settings_bp
from models import db, Organization, User, Employee, Location, Permission, \
    AISettings, EmailTemplate, PrintTemplate, SystemSetting
from services.settings_service import get_setting, set_setting, get_settings_by_category, invalidate_cache
from utils.auth import check_org
from utils.permissions import require_permission


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
@require_permission('settings.edit')
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
    elif category == 'sms':
        return _sms_category(org)
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
@require_permission('settings.edit')
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
@require_permission('settings.edit')
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
@require_permission('settings.edit')
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
        'status_icon': request.form.get('display_status_icon') == 'on',
        'series_counter': request.form.get('display_series_counter') == 'on',
        'documentation_icon': request.form.get('display_documentation_icon') == 'on',
        'billing_icon': request.form.get('display_billing_icon') == 'on',
        # Erweiterte Optionen (Cenplex CalendarData)
        'show_print_states': request.form.get('show_print_states') == 'on',
        'allow_small_columns': request.form.get('allow_small_columns') == 'on',
        'hide_locations': request.form.get('hide_locations') == 'on',
        'allow_admin_time': request.form.get('allow_admin_time') == 'on',
        'show_group_members': request.form.get('show_group_members') == 'on',
        'hover_highlight_all': request.form.get('hover_highlight_all') == 'on',
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
        organization_id=org.id, is_sms=False, is_deleted=False
    ).order_by(EmailTemplate.template_type, EmailTemplate.name).all()

    return render_template('settings/index.html', category='email', org=org,
                           settings=settings, email_templates=templates)


@settings_bp.route('/email/save', methods=['POST'])
@login_required
@require_permission('settings.edit')
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
@require_permission('settings.edit')
def create_email_template():
    """Neue E-Mail-Vorlage erstellen"""
    org_id = current_user.organization_id

    name = request.form.get('name', '').strip()
    if not name:
        flash('Name ist ein Pflichtfeld.', 'error')
        return redirect(url_for('settings.index', category='email'))

    trigger_time_str = request.form.get('trigger_time', '').strip()
    trigger_unit = request.form.get('trigger_unit', 'hours').strip()

    template = EmailTemplate(
        organization_id=org_id,
        name=name,
        template_type=request.form.get('template_type', 'reminder'),
        subject=request.form.get('subject', '').strip(),
        body_html=request.form.get('body_html', '').strip(),
        trigger_time=int(trigger_time_str) if trigger_time_str else None,
        trigger_unit=trigger_unit if trigger_time_str else None,
        send_once_per_series=request.form.get('send_once_per_series') == 'on',
        send_to_guardian=request.form.get('send_to_guardian') == 'on',
        placeholders_json=json.dumps([
            '{patient_name}', '{patient_vorname}', '{patient_nachname}',
            '{patient_anrede}', '{patient_geburtsdatum}',
            '{termin_datum}', '{termin_zeit}', '{termin_ende}', '{termin_liste}',
            '{therapeut_name}', '{therapeut_vorname}', '{therapeut_nachname}',
            '{therapeut_telefon}', '{therapeut_email}',
            '{praxis_name}', '{praxis_telefon}', '{praxis_email}',
            '{praxis_adresse}', '{praxis_plz}', '{praxis_ort}', '{standort_name}'
        ])
    )
    db.session.add(template)
    db.session.commit()

    flash(f'E-Mail-Vorlage "{name}" wurde erstellt.', 'success')
    return redirect(url_for('settings.index', category='email'))


@settings_bp.route('/email/templates/<int:template_id>/edit', methods=['POST'])
@login_required
@require_permission('settings.edit')
def edit_email_template(template_id):
    """E-Mail-Vorlage bearbeiten"""
    template = EmailTemplate.query.get_or_404(template_id)
    check_org(template)

    template.name = request.form.get('name', template.name).strip()
    template.template_type = request.form.get('template_type', template.template_type)
    template.subject = request.form.get('subject', '').strip()
    template.body_html = request.form.get('body_html', '').strip()
    # Neue Felder: Trigger, Einmal-pro-Serie, An Erziehungsberechtigte
    trigger_time = request.form.get('trigger_time', '').strip()
    if trigger_time:
        template.trigger_time = int(trigger_time)
        template.trigger_unit = request.form.get('trigger_unit', 'hours')
    else:
        template.trigger_time = None
        template.trigger_unit = None
    template.send_once_per_series = request.form.get('send_once_per_series') == 'on'
    template.send_to_guardian = request.form.get('send_to_guardian') == 'on'

    db.session.commit()
    flash(f'E-Mail-Vorlage "{template.name}" wurde aktualisiert.', 'success')
    return redirect(url_for('settings.index', category='email'))


@settings_bp.route('/email/templates/<int:template_id>/delete', methods=['POST'])
@login_required
@require_permission('settings.edit')
def delete_email_template(template_id):
    """E-Mail-Vorlage loeschen"""
    template = EmailTemplate.query.get_or_404(template_id)
    check_org(template)
    template.is_deleted = True
    db.session.commit()

    flash(f'E-Mail-Vorlage "{template.name}" wurde gelöscht.', 'success')
    return redirect(url_for('settings.index', category='email'))


@settings_bp.route('/email/templates/<int:template_id>/toggle', methods=['POST'])
@login_required
@require_permission('settings.edit')
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
# Kategorie: SMS-Vorlagen
# ============================================================

def _sms_category(org):
    sms_templates = EmailTemplate.query.filter_by(
        organization_id=org.id, is_sms=True, is_deleted=False
    ).order_by(EmailTemplate.template_type, EmailTemplate.name).all()
    return render_template('settings/index.html', category='sms', org=org,
                           sms_templates=sms_templates)


@settings_bp.route('/sms/templates/new', methods=['POST'])
@login_required
@require_permission('settings.edit')
def create_sms_template():
    """Neue SMS-Vorlage erstellen"""
    name = request.form.get('name', '').strip()
    if not name:
        flash('Name ist ein Pflichtfeld.', 'error')
        return redirect(url_for('settings.index', category='sms'))

    trigger_time = request.form.get('trigger_time', '').strip()
    trigger_unit = request.form.get('trigger_unit', 'hours').strip()

    template = EmailTemplate(
        organization_id=current_user.organization_id,
        name=name,
        template_type=request.form.get('template_type', 'reminder'),
        body_html=request.form.get('body_html', '').strip(),
        is_sms=True,
        trigger_time=int(trigger_time) if trigger_time else None,
        trigger_unit=trigger_unit if trigger_time else None,
        send_once_per_series=request.form.get('send_once_per_series') == 'on',
        placeholders_json=json.dumps([
            '{patient_name}', '{termin_datum}', '{termin_zeit}',
            '{therapeut_name}', '{praxis_name}', '{praxis_telefon}'
        ])
    )
    db.session.add(template)
    db.session.commit()
    flash(f'SMS-Vorlage "{name}" wurde erstellt.', 'success')
    return redirect(url_for('settings.index', category='sms'))


@settings_bp.route('/sms/templates/<int:template_id>/edit', methods=['POST'])
@login_required
@require_permission('settings.edit')
def edit_sms_template(template_id):
    """SMS-Vorlage bearbeiten"""
    template = EmailTemplate.query.get_or_404(template_id)
    check_org(template)
    template.body_html = request.form.get('body_html', '').strip()
    if request.form.get('name'):
        template.name = request.form.get('name', '').strip()
    if request.form.get('template_type'):
        template.template_type = request.form.get('template_type')
    trigger_time = request.form.get('trigger_time', '').strip()
    if trigger_time:
        template.trigger_time = int(trigger_time)
        template.trigger_unit = request.form.get('trigger_unit', 'hours')
    else:
        template.trigger_time = None
        template.trigger_unit = None
    template.send_once_per_series = request.form.get('send_once_per_series') == 'on'
    db.session.commit()
    flash(f'SMS-Vorlage "{template.name}" wurde aktualisiert.', 'success')
    return redirect(url_for('settings.index', category='sms'))


@settings_bp.route('/sms/templates/<int:template_id>/delete', methods=['POST'])
@login_required
@require_permission('settings.edit')
def delete_sms_template(template_id):
    """SMS-Vorlage loeschen"""
    template = EmailTemplate.query.get_or_404(template_id)
    check_org(template)
    template.is_deleted = True
    db.session.commit()
    flash(f'SMS-Vorlage "{template.name}" wurde gelöscht.', 'success')
    return redirect(url_for('settings.index', category='sms'))


@settings_bp.route('/sms/templates/<int:template_id>/toggle', methods=['POST'])
@login_required
@require_permission('settings.edit')
def toggle_sms_template(template_id):
    """SMS-Vorlage aktivieren/deaktivieren"""
    template = EmailTemplate.query.get_or_404(template_id)
    check_org(template)
    template.is_active = not template.is_active
    db.session.commit()
    status = 'aktiviert' if template.is_active else 'deaktiviert'
    flash(f'SMS-Vorlage "{template.name}" wurde {status}.', 'success')
    return redirect(url_for('settings.index', category='sms'))


# ============================================================
# Kategorie: Abrechnung
# ============================================================

def _billing_category(org):
    from models import InvoiceCopyConfig
    settings = get_settings_by_category(org.id, 'billing')
    # TP-Rechnungskopie Konfiguration laden
    tp_copy_config = InvoiceCopyConfig.query.filter_by(
        organization_id=org.id
    ).first()
    return render_template('settings/index.html', category='billing', org=org,
                           settings=settings, tp_copy_config=tp_copy_config)


@settings_bp.route('/billing/save', methods=['POST'])
@login_required
@require_permission('settings.edit')
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


@settings_bp.route('/tp-copy/save', methods=['POST'])
@login_required
@require_permission('settings.edit')
def tp_copy_save():
    """TP-Rechnungskopie Konfiguration speichern"""
    from models import InvoiceCopyConfig

    config = InvoiceCopyConfig.query.filter_by(
        organization_id=current_user.organization_id
    ).first()

    if not config:
        config = InvoiceCopyConfig(organization_id=current_user.organization_id)
        db.session.add(config)

    config.is_active = 'is_active' in request.form
    config.send_channel = request.form.get('send_channel', 'email')
    config.send_timing = request.form.get('send_timing', 'on_send')
    config.sender_email = request.form.get('sender_email', '').strip()
    config.create_task_on_failure = 'create_task_on_failure' in request.form

    template_id = request.form.get('email_template_id')
    config.email_template_id = int(template_id) if template_id else None

    db.session.commit()
    flash('TP-Rechnungskopie Einstellungen gespeichert.', 'success')
    return redirect(url_for('settings.index', category='billing'))


# ============================================================
# Kategorie: Benutzer & Rollen
# ============================================================

def _users_category(org):
    from models import Employee, EmployeeGroup
    from services.user_rights_service import (
        get_rights_schema, get_user_rights, RIGHTS_LABELS,
        KPI_CATEGORIES, STATISTIC_CATEGORIES
    )

    users = User.query.filter_by(
        organization_id=org.id
    ).order_by(User.last_name, User.first_name).all()

    # Berechtigungen laden (Rollen-Matrix)
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

    # Mitarbeiter mit ihren effektiven Rechten (fuer feingranulare Rechte-UI)
    employees = Employee.query.filter_by(
        organization_id=org.id
    ).order_by(Employee.last_name, Employee.first_name).all()

    # Benutzergruppen
    employee_groups = EmployeeGroup.query.filter_by(
        organization_id=org.id
    ).order_by(EmployeeGroup.name).all()

    # Rechte-Schema fuer die UI
    rights_schema = get_rights_schema()

    return render_template('settings/index.html', category='users', org=org,
                           users=users, permissions_matrix=permissions_matrix,
                           modules=modules, actions=actions, roles=roles,
                           employees=employees, employee_groups=employee_groups,
                           rights_schema=rights_schema,
                           kpi_categories=KPI_CATEGORIES,
                           statistic_categories=STATISTIC_CATEGORIES,
                           rights_labels=RIGHTS_LABELS)


@settings_bp.route('/users/permissions/save', methods=['POST'])
@login_required
@require_permission('settings.edit')
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
@require_permission('settings.edit')
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
@require_permission('settings.edit')
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
@require_permission('settings.edit')
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
@require_permission('settings.edit')
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
@require_permission('settings.edit')
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
@require_permission('settings.edit')
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
@require_permission('settings.edit')
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


# ============================================================
# Befund-Vorlagen
# ============================================================

@settings_bp.route('/finding-templates')
@login_required
@require_permission('settings.edit')
def finding_templates():
    """Befund-Vorlagen verwalten"""
    from models import FindingTemplate
    templates = FindingTemplate.query.filter_by(
        organization_id=current_user.organization_id
    ).order_by(FindingTemplate.sort_order, FindingTemplate.name).all()
    return render_template('settings/finding_templates.html', templates=templates)


@settings_bp.route('/finding-templates/new', methods=['GET', 'POST'])
@login_required
@require_permission('settings.edit')
def finding_template_new():
    """Neue Befund-Vorlage erstellen"""
    from models import FindingTemplate, Location

    if request.method == 'POST':
        fields = request.form.get('fields_json', '[]')
        # JSON validieren
        try:
            json.loads(fields)
        except json.JSONDecodeError:
            flash('Ungueltiges JSON in Felddefinition.', 'error')
            return redirect(url_for('settings.finding_template_new'))

        template = FindingTemplate(
            organization_id=current_user.organization_id,
            name=request.form.get('name', '').strip(),
            template_type=request.form.get('template_type', 'erstbefund'),
            location_id=request.form.get('location_id') or None,
            fields_json=fields,
            is_default='is_default' in request.form,
        )

        # Wenn Standard: andere Standards deaktivieren
        if template.is_default:
            FindingTemplate.query.filter_by(
                organization_id=current_user.organization_id,
                is_default=True
            ).update({'is_default': False})

        db.session.add(template)
        db.session.commit()
        flash('Befund-Vorlage erstellt.', 'success')
        return redirect(url_for('settings.finding_templates'))

    locations = Location.query.filter_by(
        organization_id=current_user.organization_id,
        is_active=True
    ).all()
    return render_template('settings/finding_template_form.html',
                         template=None, locations=locations)


@settings_bp.route('/finding-templates/<int:template_id>/edit', methods=['GET', 'POST'])
@login_required
@require_permission('settings.edit')
def finding_template_edit(template_id):
    """Befund-Vorlage bearbeiten"""
    from models import FindingTemplate, Location

    template = FindingTemplate.query.get_or_404(template_id)
    if template.organization_id != current_user.organization_id:
        abort(403)

    if request.method == 'POST':
        template.name = request.form.get('name', '').strip()
        template.template_type = request.form.get('template_type', 'erstbefund')
        template.location_id = request.form.get('location_id') or None
        template.fields_json = request.form.get('fields_json', '[]')
        template.is_default = 'is_default' in request.form

        if template.is_default:
            FindingTemplate.query.filter(
                FindingTemplate.organization_id == current_user.organization_id,
                FindingTemplate.id != template.id,
                FindingTemplate.is_default == True
            ).update({'is_default': False})

        db.session.commit()
        flash('Befund-Vorlage aktualisiert.', 'success')
        return redirect(url_for('settings.finding_templates'))

    locations = Location.query.filter_by(
        organization_id=current_user.organization_id,
        is_active=True
    ).all()
    return render_template('settings/finding_template_form.html',
                         template=template, locations=locations)


@settings_bp.route('/finding-templates/<int:template_id>/delete', methods=['POST'])
@login_required
@require_permission('settings.edit')
def finding_template_delete(template_id):
    """Befund-Vorlage loeschen"""
    from models import FindingTemplate
    template = FindingTemplate.query.get_or_404(template_id)
    if template.organization_id != current_user.organization_id:
        abort(403)

    db.session.delete(template)
    db.session.commit()
    flash('Befund-Vorlage geloescht.', 'success')
    return redirect(url_for('settings.finding_templates'))


# ============================================================
# Behandlungsplan-Vorlagen
# ============================================================

@settings_bp.route('/plan-templates')
@login_required
@require_permission('settings.edit')
def plan_templates():
    """Behandlungsplan-Vorlagen verwalten"""
    from models import TreatmentPlanTemplate
    templates = TreatmentPlanTemplate.query.filter_by(
        organization_id=current_user.organization_id
    ).order_by(TreatmentPlanTemplate.sort_order, TreatmentPlanTemplate.name).all()
    return render_template('settings/plan_templates.html', templates=templates)


@settings_bp.route('/plan-templates/new', methods=['GET', 'POST'])
@login_required
@require_permission('settings.edit')
def plan_template_new():
    """Neue Behandlungsplan-Vorlage erstellen"""
    from models import TreatmentPlanTemplate
    import json

    if request.method == 'POST':
        template = TreatmentPlanTemplate(
            organization_id=current_user.organization_id,
            name=request.form.get('name', '').strip(),
            description=request.form.get('description', '').strip(),
            goals_json=request.form.get('goals_json', '[]'),
            measures_json=request.form.get('measures_json', '[]'),
            frequency_json=request.form.get('frequency_json', '{}'),
            insurance_type=request.form.get('insurance_type') or None,
        )
        db.session.add(template)
        db.session.commit()
        flash('Behandlungsplan-Vorlage erstellt.', 'success')
        return redirect(url_for('settings.plan_templates'))

    return render_template('settings/plan_template_form.html', template=None)


@settings_bp.route('/plan-templates/<int:template_id>/edit', methods=['GET', 'POST'])
@login_required
@require_permission('settings.edit')
def plan_template_edit(template_id):
    """Behandlungsplan-Vorlage bearbeiten"""
    from models import TreatmentPlanTemplate

    template = TreatmentPlanTemplate.query.get_or_404(template_id)
    if template.organization_id != current_user.organization_id:
        abort(403)

    if request.method == 'POST':
        template.name = request.form.get('name', '').strip()
        template.description = request.form.get('description', '').strip()
        template.goals_json = request.form.get('goals_json', '[]')
        template.measures_json = request.form.get('measures_json', '[]')
        template.frequency_json = request.form.get('frequency_json', '{}')
        template.insurance_type = request.form.get('insurance_type') or None
        db.session.commit()
        flash('Vorlage aktualisiert.', 'success')
        return redirect(url_for('settings.plan_templates'))

    return render_template('settings/plan_template_form.html', template=template)


@settings_bp.route('/plan-templates/<int:template_id>/delete', methods=['POST'])
@login_required
@require_permission('settings.edit')
def plan_template_delete(template_id):
    """Behandlungsplan-Vorlage loeschen"""
    from models import TreatmentPlanTemplate
    template = TreatmentPlanTemplate.query.get_or_404(template_id)
    if template.organization_id != current_user.organization_id:
        abort(403)
    db.session.delete(template)
    db.session.commit()
    flash('Vorlage geloescht.', 'success')
    return redirect(url_for('settings.plan_templates'))


# ============================================================
# Frageboegen-Vorlagen
# ============================================================

@settings_bp.route('/questionnaires')
@login_required
@require_permission('settings.edit')
def questionnaires():
    """Frageboegen verwalten"""
    from models import Questionnaire
    items = Questionnaire.query.filter_by(
        organization_id=current_user.organization_id
    ).order_by(Questionnaire.sort_order, Questionnaire.name).all()
    return render_template('settings/questionnaires.html', questionnaires=items)


@settings_bp.route('/questionnaires/new', methods=['GET', 'POST'])
@login_required
@require_permission('settings.edit')
def questionnaire_new():
    """Neuen Fragebogen erstellen"""
    from models import Questionnaire

    if request.method == 'POST':
        questions = request.form.get('questions_json', '[]')
        # JSON validieren
        try:
            json.loads(questions)
        except json.JSONDecodeError:
            flash('Ungueltiges JSON in Fragendefinition.', 'error')
            return redirect(url_for('settings.questionnaire_new'))

        q = Questionnaire(
            organization_id=current_user.organization_id,
            name=request.form.get('name', '').strip(),
            description=request.form.get('description', '').strip() or None,
            questions_json=questions,
            scoring_json=request.form.get('scoring_json', '').strip() or None,
            is_portal_visible='is_portal_visible' in request.form,
            is_active='is_active' in request.form,
            sort_order=int(request.form.get('sort_order', 0) or 0),
        )
        db.session.add(q)
        db.session.commit()
        flash('Fragebogen erstellt.', 'success')
        return redirect(url_for('settings.questionnaires'))

    return render_template('settings/questionnaire_form.html', questionnaire=None)


@settings_bp.route('/questionnaires/<int:questionnaire_id>/edit', methods=['GET', 'POST'])
@login_required
@require_permission('settings.edit')
def questionnaire_edit(questionnaire_id):
    """Fragebogen bearbeiten"""
    from models import Questionnaire

    q = Questionnaire.query.get_or_404(questionnaire_id)
    if q.organization_id != current_user.organization_id:
        abort(403)

    if request.method == 'POST':
        q.name = request.form.get('name', '').strip()
        q.description = request.form.get('description', '').strip() or None
        q.questions_json = request.form.get('questions_json', '[]')
        q.scoring_json = request.form.get('scoring_json', '').strip() or None
        q.is_portal_visible = 'is_portal_visible' in request.form
        q.is_active = 'is_active' in request.form
        q.sort_order = int(request.form.get('sort_order', 0) or 0)

        # JSON validieren
        try:
            json.loads(q.questions_json)
        except json.JSONDecodeError:
            flash('Ungueltiges JSON in Fragendefinition.', 'error')
            return render_template('settings/questionnaire_form.html', questionnaire=q)

        db.session.commit()
        flash('Fragebogen aktualisiert.', 'success')
        return redirect(url_for('settings.questionnaires'))

    return render_template('settings/questionnaire_form.html', questionnaire=q)


@settings_bp.route('/questionnaires/<int:questionnaire_id>/delete', methods=['POST'])
@login_required
@require_permission('settings.edit')
def questionnaire_delete(questionnaire_id):
    """Fragebogen loeschen"""
    from models import Questionnaire
    q = Questionnaire.query.get_or_404(questionnaire_id)
    if q.organization_id != current_user.organization_id:
        abort(403)
    db.session.delete(q)
    db.session.commit()
    flash('Fragebogen geloescht.', 'success')
    return redirect(url_for('settings.questionnaires'))


# ============================================================
# Terminkarten-Darstellung
# ============================================================

@settings_bp.route('/appointment-display/save', methods=['POST'])
@login_required
@require_permission('settings.edit')
def appointment_display_save():
    """Terminkarten-Darstellung konfigurieren"""
    org_id = current_user.organization_id

    config = {
        'display_mode': request.form.get('display_mode', 'compact'),  # compact, expanded
        'show_patient_name': 'show_patient_name' in request.form,
        'show_time': 'show_time' in request.form,
        'show_room': 'show_room' in request.form,
        'show_series_counter': 'show_series_counter' in request.form,
        'show_status_icon': 'show_status_icon' in request.form,
        'show_documentation_icon': 'show_documentation_icon' in request.form,
        'show_billing_icon': 'show_billing_icon' in request.form,
    }

    # Farbkategorien aus Formular lesen
    categories = []
    cat_names = request.form.getlist('category_name')
    cat_colors = request.form.getlist('category_color')
    for name, color in zip(cat_names, cat_colors):
        if name.strip():
            categories.append({'name': name.strip(), 'color': color})
    config['color_categories'] = categories

    # In SystemSetting speichern
    setting = SystemSetting.query.filter_by(
        organization_id=org_id,
        key='appointment_display_config'
    ).first()

    if not setting:
        setting = SystemSetting(
            organization_id=org_id,
            key='appointment_display_config',
            value=json.dumps(config, ensure_ascii=False)
        )
        db.session.add(setting)
    else:
        setting.value = json.dumps(config, ensure_ascii=False)

    db.session.commit()
    flash('Terminkarten-Einstellungen gespeichert.', 'success')
    return redirect(url_for('settings.index', category='calendar'))


# ============================================================
# Cenplex Phase 18: Benutzerrechte (User Rights)
# ============================================================

@settings_bp.route('/api/user-rights-schema')
@login_required
@admin_required
def api_user_rights_schema():
    """Benutzerrechte-Schema (Cenplex: 18 Rechte-Klassen)"""
    from services.user_rights_service import get_rights_schema, KPI_CATEGORIES, STATISTIC_CATEGORIES
    schema = get_rights_schema()
    return jsonify({
        'schema': schema,
        'kpi_categories': KPI_CATEGORIES,
        'statistic_categories': STATISTIC_CATEGORIES
    })


@settings_bp.route('/api/user-rights/<int:employee_id>')
@login_required
@admin_required
def api_get_user_rights(employee_id):
    """Benutzerrechte eines Mitarbeiters laden (effektive Rechte inkl. Gruppen/Rolle)"""
    from models import Employee
    from services.user_rights_service import get_user_rights, DEFAULT_RIGHTS
    emp = Employee.query.get_or_404(employee_id)
    if emp.organization_id != current_user.organization_id:
        abort(403)

    # Effektive Rechte (Merge aus Rolle + Gruppen + Individuell)
    effective = get_user_rights(emp)

    # Individuelle Overrides (nur die manuell gesetzten)
    individual = {}
    if emp.user_rights_json:
        try:
            individual = json.loads(emp.user_rights_json)
        except (json.JSONDecodeError, TypeError):
            pass

    return jsonify({
        'effective': effective,
        'individual': individual,
        'role': emp.user.role if emp.user else 'therapist'
    })


@settings_bp.route('/api/user-rights/<int:employee_id>', methods=['PUT'])
@login_required
@require_permission('settings.edit')
def api_save_user_rights(employee_id):
    """Benutzerrechte speichern (Cenplex: SaveUserRights)"""
    from models import Employee
    from services.user_rights_service import save_user_rights
    emp = Employee.query.get_or_404(employee_id)
    if emp.organization_id != current_user.organization_id:
        abort(403)

    # Admin-Rechte koennen nicht manuell gesetzt werden
    if emp.user and emp.user.role == 'admin':
        return jsonify({'error': 'Admin-Rechte koennen nicht geaendert werden'}), 400

    data = request.get_json()
    save_user_rights(employee_id, data)
    return jsonify({'success': True})


@settings_bp.route('/api/user-rights/<int:employee_id>/reset', methods=['POST'])
@login_required
@require_permission('settings.edit')
def api_reset_user_rights(employee_id):
    """Benutzerrechte auf Rollen-Default zuruecksetzen"""
    from models import Employee
    emp = Employee.query.get_or_404(employee_id)
    if emp.organization_id != current_user.organization_id:
        abort(403)

    emp.user_rights_json = None
    db.session.commit()
    return jsonify({'success': True})
