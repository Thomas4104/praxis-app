"""
Feingranulares Berechtigungssystem nach Cenplex-Vorbild.
Berechtigungen werden als JSON im Employee.user_rights_json gespeichert.

Cenplex-Referenz: Cenplex.Contracts.UserRights (18 Rechte-Klassen)
Jede Klasse erbt von UserRightBase (can_read, can_edit).
"""
import json
from functools import wraps
from flask import abort
from flask_login import current_user


# Standard-Rechte-Struktur (Cenplex: UserRights, Version 1561)
# Defaults entsprechen dem Cenplex-Konstruktor von UserRights
DEFAULT_RIGHTS = {
    'version': 2,

    # Cenplex: InvoiceRights
    'invoice': {
        'can_read': True, 'can_edit': True,
        'can_send': True, 'can_delete': True,
        'can_cancel': False, 'can_delete_payment': False,
        'can_close': True
    },

    # Cenplex: GutspracheRights
    'kostengutsprache': {'can_read': True, 'can_edit': True},

    # Cenplex: ArchiveRights
    'archive': {'can_read': True, 'can_edit': True, 'can_reset_invoice': False},

    # Cenplex: InvoiceValidationRights
    'invoice_validation': {'can_read': True, 'can_edit': True},

    # Cenplex: PracticeRights
    'practice': {'can_read': True, 'can_edit': True},

    # Cenplex: EmployeeRights
    'employee': {
        'can_read': True, 'can_edit': True,
        'can_edit_vacation': False,
        'can_edit_work_schedule': False,
        'can_edit_room_plan': False,
        'only_personal': False,
        'can_delete_vacation': False,
        'use_app': True,
        'can_change_app_calendar': False,
        'can_edit_user_groups': False,
        'can_add_vacation': True,
        'can_edit_vacation_requests': False,
        'can_access_vacation_plan': False,
        'can_edit_vacation_allotment_settings': False,
        'can_save_vacation_allotments': False
    },

    # Cenplex: PatientRights
    'patient': {
        'can_read': True, 'can_edit': True,
        'can_access_traces': False,
        'can_delete_survey': False,
        'can_edit_report_templates': False
    },

    # Cenplex: AddressRights
    'address': {'can_read': True, 'can_edit': True},

    # Cenplex: ProductRights
    'product': {'can_read': True, 'can_edit': True},

    # Cenplex: ResourceRights
    'resource': {'can_read': True, 'can_edit': True},

    # Cenplex: StatisticRights
    'statistic': {'can_read': False, 'can_edit': False, 'allowed_categories': []},

    # Cenplex: KpiRights
    'kpi': {'can_read': False, 'can_edit': False, 'only_personal': False, 'allowed_categories': []},

    # Cenplex: FitnessRights
    'fitness': {'can_read': True, 'can_edit': True, 'can_delete_abo': False, 'can_change_abo': True},

    # Cenplex: SettingRights
    'setting': {'can_read': True, 'can_edit': True},

    # Cenplex: LicenseRights
    'license': {'can_read': False, 'can_edit': False},

    # Cenplex: CalendarRights
    'calendar': {
        'can_read': True, 'can_edit': True,
        'can_delete_series': True,
        'can_bill_series': True,
        'can_delete_appointment_series': True,
        'can_change_pause': True,
        'can_reopen_series': False,
        'can_create_followup': True
    },

    # Cenplex: DashboardRights
    'dashboard': {
        'can_read': True, 'can_edit': True,
        'cannot_change_layout': False,
        'can_change_mission_box': False,
        'can_change_worktime_box': False
    },

    # Cenplex: MailingRights
    'mailing': {'can_read': True, 'can_edit': True},
}

# Beschriftungen fuer die UI (Deutsch)
RIGHTS_LABELS = {
    'invoice': {
        '_label': 'Rechnungen',
        'can_read': 'Anzeigen', 'can_edit': 'Bearbeiten',
        'can_send': 'Versenden', 'can_delete': 'Loeschen',
        'can_cancel': 'Stornieren', 'can_delete_payment': 'Zahlung loeschen',
        'can_close': 'Abschliessen'
    },
    'kostengutsprache': {
        '_label': 'Kostengutsprachen',
        'can_read': 'Anzeigen', 'can_edit': 'Bearbeiten'
    },
    'archive': {
        '_label': 'Archiv',
        'can_read': 'Anzeigen', 'can_edit': 'Bearbeiten',
        'can_reset_invoice': 'Rechnung zuruecksetzen'
    },
    'invoice_validation': {
        '_label': 'Rechnungsvalidierung',
        'can_read': 'Anzeigen', 'can_edit': 'Bearbeiten'
    },
    'practice': {
        '_label': 'Praxis',
        'can_read': 'Anzeigen', 'can_edit': 'Bearbeiten'
    },
    'employee': {
        '_label': 'Mitarbeiter',
        'can_read': 'Anzeigen', 'can_edit': 'Bearbeiten',
        'can_edit_vacation': 'Ferien bearbeiten',
        'can_edit_work_schedule': 'Arbeitsplan bearbeiten',
        'can_edit_room_plan': 'Raumplan bearbeiten',
        'only_personal': 'Nur eigene Daten',
        'can_delete_vacation': 'Ferien loeschen',
        'use_app': 'App verwenden',
        'can_change_app_calendar': 'App-Kalender aendern',
        'can_edit_user_groups': 'Benutzergruppen bearbeiten',
        'can_add_vacation': 'Ferien hinzufuegen',
        'can_edit_vacation_requests': 'Ferienantraege bearbeiten',
        'can_access_vacation_plan': 'Ferienplan anzeigen',
        'can_edit_vacation_allotment_settings': 'Ferienkontingent-Einst. bearbeiten',
        'can_save_vacation_allotments': 'Ferienkontingente speichern'
    },
    'patient': {
        '_label': 'Patienten',
        'can_read': 'Anzeigen', 'can_edit': 'Bearbeiten',
        'can_access_traces': 'Verlauf/Protokoll anzeigen',
        'can_delete_survey': 'Fragebogen loeschen',
        'can_edit_report_templates': 'Berichtsvorlagen bearbeiten'
    },
    'address': {
        '_label': 'Adressen',
        'can_read': 'Anzeigen', 'can_edit': 'Bearbeiten'
    },
    'product': {
        '_label': 'Produkte',
        'can_read': 'Anzeigen', 'can_edit': 'Bearbeiten'
    },
    'resource': {
        '_label': 'Ressourcen',
        'can_read': 'Anzeigen', 'can_edit': 'Bearbeiten'
    },
    'statistic': {
        '_label': 'Auswertungen',
        'can_read': 'Anzeigen', 'can_edit': 'Bearbeiten',
        'allowed_categories': 'Erlaubte Kategorien'
    },
    'kpi': {
        '_label': 'KPI / Kennzahlen',
        'can_read': 'Anzeigen', 'can_edit': 'Bearbeiten',
        'only_personal': 'Nur eigene Daten',
        'allowed_categories': 'Erlaubte Kategorien'
    },
    'fitness': {
        '_label': 'Fitness',
        'can_read': 'Anzeigen', 'can_edit': 'Bearbeiten',
        'can_delete_abo': 'Abo loeschen', 'can_change_abo': 'Abo aendern'
    },
    'setting': {
        '_label': 'Einstellungen',
        'can_read': 'Anzeigen', 'can_edit': 'Bearbeiten'
    },
    'license': {
        '_label': 'Lizenzen',
        'can_read': 'Anzeigen', 'can_edit': 'Bearbeiten'
    },
    'calendar': {
        '_label': 'Kalender',
        'can_read': 'Anzeigen', 'can_edit': 'Bearbeiten',
        'can_delete_series': 'Serie loeschen',
        'can_bill_series': 'Serie abrechnen',
        'can_delete_appointment_series': 'Terminserie loeschen',
        'can_change_pause': 'Pause aendern',
        'can_reopen_series': 'Serie wieder oeffnen',
        'can_create_followup': 'Folgetermin erstellen'
    },
    'dashboard': {
        '_label': 'Dashboard',
        'can_read': 'Anzeigen', 'can_edit': 'Bearbeiten',
        'cannot_change_layout': 'Layout-Aenderung sperren',
        'can_change_mission_box': 'Aufgaben-Box aendern',
        'can_change_worktime_box': 'Arbeitszeit-Box aendern'
    },
    'mailing': {
        '_label': 'E-Mail / SMS',
        'can_read': 'Anzeigen', 'can_edit': 'Bearbeiten'
    },
}

# KPI-Kategorien (Cenplex: KpiType)
KPI_CATEGORIES = {
    'controlling': 'Controlling',
    'sales': 'Umsatz',
    'appointments': 'Termine',
    'fitness': 'Fitness'
}

# Statistik-Kategorien (Cenplex: StatisticMaster)
STATISTIC_CATEGORIES = {
    'series': 'Serien',
    'invoices': 'Rechnungen',
    'employees': 'Mitarbeiter',
    'invoice_positions': 'Rechnungspositionen',
    'appointments': 'Termine',
    'contacts': 'Kontakte',
    'days': 'Tage',
    'sales': 'Umsatz',
    'patients': 'Patienten',
    'abos': 'Abos',
    'products': 'Produkte',
    'location': 'Standorte',
    'fitness': 'Fitness',
    'resources': 'Ressourcen',
    'abo_visits': 'Abo-Besuche',
    'surveys': 'Fragebogen',
    'findings': 'Befunde',
    'payments': 'Zahlungen',
    'treatment_plan': 'Behandlungsplaene'
}

# Admin hat alle Rechte
def _build_admin_rights():
    """Generiert Admin-Rechte: Alle Booleans auf True, Listen auf ['*']"""
    admin = {}
    for key, val in DEFAULT_RIGHTS.items():
        if isinstance(val, dict):
            admin[key] = {}
            for k, v in val.items():
                if isinstance(v, bool):
                    admin[key][k] = True
                elif isinstance(v, list):
                    admin[key][k] = ['*']
                else:
                    admin[key][k] = v
        else:
            admin[key] = val
    # Spezialfall: cannot_change_layout ist negativ-logik, Admin darf Layout aendern
    if 'dashboard' in admin:
        admin['dashboard']['cannot_change_layout'] = False
    admin['version'] = DEFAULT_RIGHTS.get('version', 2)
    return admin


ADMIN_RIGHTS = _build_admin_rights()

# Rollen-Defaults (Cenplex: Vorgaben pro UserRole)
ROLE_DEFAULTS = {
    'therapist': {
        'invoice': {'can_read': True, 'can_edit': False, 'can_send': False},
        'patient': {'can_read': True, 'can_edit': True, 'can_access_traces': True},
        'calendar': {'can_read': True, 'can_edit': True, 'can_create_followup': True},
        'employee': {'can_read': True, 'can_edit': False, 'only_personal': True, 'use_app': True},
        'dashboard': {'can_read': True, 'can_edit': False},
        'product': {'can_read': True, 'can_edit': False},
        'resource': {'can_read': True, 'can_edit': False},
        'address': {'can_read': True, 'can_edit': False},
        'mailing': {'can_read': True, 'can_edit': False},
        'setting': {'can_read': False, 'can_edit': False},
        'statistic': {'can_read': False, 'can_edit': False},
        'kpi': {'can_read': False, 'can_edit': False},
        'fitness': {'can_read': True, 'can_edit': False},
        'practice': {'can_read': False, 'can_edit': False},
        'license': {'can_read': False, 'can_edit': False},
    },
    'reception': {
        'invoice': {'can_read': True, 'can_edit': True, 'can_send': True},
        'patient': {'can_read': True, 'can_edit': True},
        'calendar': {'can_read': True, 'can_edit': True, 'can_create_followup': True},
        'employee': {'can_read': True, 'can_edit': False, 'only_personal': True, 'use_app': True},
        'dashboard': {'can_read': True, 'can_edit': False},
        'product': {'can_read': True, 'can_edit': False},
        'resource': {'can_read': True, 'can_edit': True},
        'address': {'can_read': True, 'can_edit': True},
        'mailing': {'can_read': True, 'can_edit': True},
        'setting': {'can_read': False, 'can_edit': False},
        'statistic': {'can_read': False, 'can_edit': False},
        'kpi': {'can_read': False, 'can_edit': False},
        'fitness': {'can_read': True, 'can_edit': True},
        'practice': {'can_read': False, 'can_edit': False},
        'license': {'can_read': False, 'can_edit': False},
    },
    'manager': {
        'invoice': {'can_read': True, 'can_edit': True, 'can_send': True, 'can_delete': True, 'can_close': True},
        'patient': {'can_read': True, 'can_edit': True, 'can_access_traces': True},
        'calendar': {'can_read': True, 'can_edit': True, 'can_delete_series': True,
                     'can_bill_series': True, 'can_create_followup': True},
        'employee': {'can_read': True, 'can_edit': True, 'can_edit_vacation': True,
                     'can_add_vacation': True, 'can_edit_vacation_requests': True,
                     'can_access_vacation_plan': True, 'use_app': True},
        'dashboard': {'can_read': True, 'can_edit': True},
        'product': {'can_read': True, 'can_edit': True},
        'resource': {'can_read': True, 'can_edit': True},
        'address': {'can_read': True, 'can_edit': True},
        'mailing': {'can_read': True, 'can_edit': True},
        'setting': {'can_read': True, 'can_edit': False},
        'statistic': {'can_read': True, 'can_edit': False},
        'kpi': {'can_read': True, 'can_edit': False},
        'fitness': {'can_read': True, 'can_edit': True, 'can_change_abo': True},
        'practice': {'can_read': True, 'can_edit': False},
        'license': {'can_read': True, 'can_edit': False},
    },
    'billing': {
        'invoice': {'can_read': True, 'can_edit': True, 'can_send': True,
                    'can_delete': True, 'can_close': True, 'can_delete_payment': True},
        'patient': {'can_read': True, 'can_edit': False},
        'calendar': {'can_read': True, 'can_edit': False},
        'employee': {'can_read': False, 'can_edit': False, 'only_personal': True},
        'dashboard': {'can_read': True, 'can_edit': False},
        'product': {'can_read': True, 'can_edit': False},
        'resource': {'can_read': False, 'can_edit': False},
        'address': {'can_read': True, 'can_edit': False},
        'mailing': {'can_read': True, 'can_edit': False},
        'setting': {'can_read': False, 'can_edit': False},
        'statistic': {'can_read': True, 'can_edit': False},
        'kpi': {'can_read': True, 'can_edit': False},
        'fitness': {'can_read': False, 'can_edit': False},
        'practice': {'can_read': False, 'can_edit': False},
        'license': {'can_read': False, 'can_edit': False},
        'archive': {'can_read': True, 'can_edit': True},
        'invoice_validation': {'can_read': True, 'can_edit': True},
        'kostengutsprache': {'can_read': True, 'can_edit': True},
    },
}


def _deep_merge_rights(base, override):
    """Merged override in base-Rechte (OR-Logik fuer booleans, Union fuer Listen)"""
    merged = json.loads(json.dumps(base))
    for section, perms in override.items():
        if section in merged and isinstance(perms, dict) and isinstance(merged[section], dict):
            merged[section].update(perms)
        else:
            merged[section] = perms
    return merged


def get_user_rights(employee=None):
    """Laedt Berechtigungen fuer einen Mitarbeiter.

    Prioritaet: 1) Admin -> alle Rechte
                2) Individuelle Rechte (user_rights_json)
                3) Gruppen-Rechte (OR-Logik)
                4) Rollen-basierte Defaults
                5) DEFAULT_RIGHTS
    """
    if employee is None:
        if not current_user or not current_user.is_authenticated:
            return DEFAULT_RIGHTS
        from models import Employee
        employee = Employee.query.filter_by(user_id=current_user.id).first()

    if not employee:
        return DEFAULT_RIGHTS

    # Admin hat alle Rechte
    user = employee.user
    if user and user.role == 'admin':
        return ADMIN_RIGHTS

    # Basis: Rollen-Defaults oder DEFAULT_RIGHTS
    role = user.role if user else None
    base_rights = json.loads(json.dumps(DEFAULT_RIGHTS))
    if role and role in ROLE_DEFAULTS:
        base_rights = _deep_merge_rights(base_rights, ROLE_DEFAULTS[role])

    # Gruppen-Rechte (OR-Logik: wenn eine Gruppe erlaubt, dann erlaubt)
    if employee.user_groups_json:
        try:
            group_ids = json.loads(employee.user_groups_json)
            if group_ids:
                from models import EmployeeGroup
                groups = EmployeeGroup.query.filter(EmployeeGroup.id.in_(group_ids)).all()
                for group in groups:
                    if group.user_rights_json:
                        group_rights = json.loads(group.user_rights_json)
                        for section, perms in group_rights.items():
                            if section in base_rights and isinstance(perms, dict):
                                for k, v in perms.items():
                                    if isinstance(v, bool) and v:
                                        base_rights[section][k] = True
                                    elif isinstance(v, list):
                                        existing = base_rights[section].get(k, [])
                                        if existing != ['*']:
                                            base_rights[section][k] = list(set(existing + v))
        except (json.JSONDecodeError, TypeError):
            pass

    # Individuelle Rechte (hoechste Prioritaet, ueberschreiben alles)
    if employee.user_rights_json:
        try:
            individual = json.loads(employee.user_rights_json)
            base_rights = _deep_merge_rights(base_rights, individual)
        except (json.JSONDecodeError, TypeError):
            pass

    return base_rights


def has_right(section, permission='can_read'):
    """Prueft ob aktueller Benutzer eine bestimmte Berechtigung hat.

    Cenplex-Logik:
    - can_read=False deaktiviert alle anderen Rechte der Sektion
    - can_edit=False deaktiviert alle Sub-Rechte (ausser can_read)
    - KPI: can_edit und only_personal sind gegenseitig exklusiv
    - Employee: only_personal=True setzt can_read=False (nur eigene Daten)
    - Employee: use_app=False setzt can_change_app_calendar=False
    """
    rights = get_user_rights()
    section_rights = rights.get(section, {})
    if not isinstance(section_rights, dict):
        return False

    # Cenplex-Regel: Wenn can_read=False, sind alle anderen Rechte auch False
    if permission != 'can_read' and not section_rights.get('can_read', False):
        # Ausnahme: employee.only_personal und kpi.only_personal
        if not (permission == 'only_personal' and section in ('kpi', 'employee')):
            return False

    # Cenplex: can_edit=False deaktiviert Sub-Rechte (ausser can_read)
    if permission not in ('can_read', 'can_edit', 'only_personal') and \
       not section_rights.get('can_edit', False):
        return False

    # Cenplex KPI-Speziallogik: can_edit und only_personal sind gegenseitig exklusiv
    if section == 'kpi':
        if permission == 'can_edit' and section_rights.get('only_personal', False):
            return False
        if permission == 'only_personal' and section_rights.get('can_edit', False):
            return False

    # Cenplex Employee-Speziallogik: use_app=False deaktiviert can_change_app_calendar
    if section == 'employee' and permission == 'can_change_app_calendar':
        if not section_rights.get('use_app', False):
            return False

    val = section_rights.get(permission, False)
    if isinstance(val, list):
        return len(val) > 0
    return bool(val)


def has_right_category(section, category):
    """Prueft ob eine bestimmte Kategorie erlaubt ist (fuer KPI/Statistik)"""
    rights = get_user_rights()
    section_rights = rights.get(section, {})
    if not isinstance(section_rights, dict):
        return False
    allowed = section_rights.get('allowed_categories', [])
    if allowed == ['*']:
        return True
    return category in allowed


def require_right(section, permission='can_read'):
    """Decorator: Erfordert bestimmte Berechtigung"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not has_right(section, permission):
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def save_user_rights(employee_id, rights_dict):
    """Speichert individuelle Berechtigungen fuer einen Mitarbeiter"""
    from models import Employee, db
    employee = Employee.query.get(employee_id)
    if employee:
        employee.user_rights_json = json.dumps(rights_dict)
        db.session.commit()
    return employee


def save_group_rights(group_id, rights_dict):
    """Speichert Berechtigungen fuer eine Benutzergruppe"""
    from models import EmployeeGroup, db
    group = EmployeeGroup.query.get(group_id)
    if group:
        group.user_rights_json = json.dumps(rights_dict)
        db.session.commit()
    return group


def get_rights_schema():
    """Gibt das vollstaendige Rechte-Schema fuer die UI zurueck.

    Basiert auf RIGHTS_LABELS und DEFAULT_RIGHTS.
    """
    schema = {}
    for section, defaults in DEFAULT_RIGHTS.items():
        if section == 'version':
            continue
        if not isinstance(defaults, dict):
            continue
        labels = RIGHTS_LABELS.get(section, {})
        section_label = labels.get('_label', section.capitalize())
        permissions = []
        for perm_key, default_val in defaults.items():
            if isinstance(default_val, list):
                # Kategorie-basierte Rechte
                perm_type = 'categories'
            else:
                perm_type = 'boolean'
            permissions.append({
                'key': perm_key,
                'label': labels.get(perm_key, perm_key),
                'type': perm_type,
                'default': default_val
            })
        schema[section] = {
            'label': section_label,
            'permissions': permissions
        }
    return schema
