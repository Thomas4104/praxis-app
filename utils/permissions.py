"""
Rollenbasierte Zugriffskontrolle (RBAC) fuer medizinische Praxissoftware.
Definiert granulare Berechtigungen pro Rolle.
"""
from functools import wraps
from flask import abort, flash, redirect, url_for
from flask_login import current_user

# Rollen-Hierarchie
ROLES = {
    'admin': {
        'level': 100,
        'description': 'Praxisinhaber / Vollzugriff',
    },
    'manager': {
        'level': 80,
        'description': 'Praxisleitung / Erweiterte Rechte',
    },
    'therapist': {
        'level': 60,
        'description': 'Therapeut / Klinische Daten',
    },
    'reception': {
        'level': 40,
        'description': 'Empfang / Termine und Kontaktdaten',
    },
    'billing': {
        'level': 50,
        'description': 'Abrechnung / Finanzdaten',
    },
}

# Berechtigungen pro Modul und Aktion
PERMISSIONS = {
    # Patientendaten
    'patients.view_list':       ['admin', 'manager', 'therapist', 'reception', 'billing'],
    'patients.view_detail':     ['admin', 'manager', 'therapist', 'reception'],
    'patients.view_medical':    ['admin', 'manager', 'therapist'],  # Diagnosen, SOAP, Notizen
    'patients.view_financial':  ['admin', 'manager', 'billing'],     # Rechnungen, Zahlungen
    'patients.edit':            ['admin', 'manager', 'therapist', 'reception'],
    'patients.delete':          ['admin'],
    'patients.merge':           ['admin'],
    'patients.export':          ['admin', 'manager'],

    # Termine
    'calendar.view':            ['admin', 'manager', 'therapist', 'reception'],
    'calendar.create':          ['admin', 'manager', 'therapist', 'reception'],
    'calendar.edit':            ['admin', 'manager', 'therapist', 'reception'],
    'calendar.delete':          ['admin', 'manager'],

    # Behandlung
    'treatment.view':           ['admin', 'manager', 'therapist'],
    'treatment.edit_soap':      ['admin', 'therapist'],  # Nur Therapeut darf SOAP schreiben
    'treatment.create_series':  ['admin', 'manager', 'therapist'],
    'treatment.close_series':   ['admin', 'manager', 'therapist'],

    # Abrechnung
    'billing.view':             ['admin', 'manager', 'billing'],
    'billing.create_invoice':   ['admin', 'manager', 'billing'],
    'billing.send_invoice':     ['admin', 'manager', 'billing'],
    'billing.record_payment':   ['admin', 'manager', 'billing'],
    'billing.start_dunning':    ['admin', 'manager'],
    'billing.cancel_invoice':   ['admin'],

    # Buchhaltung
    'accounting.view':          ['admin', 'manager'],
    'accounting.edit':          ['admin'],

    # Mitarbeiter / HR
    'employees.view':           ['admin', 'manager'],
    'employees.edit':           ['admin'],
    'hr.view_payroll':          ['admin'],
    'hr.edit_payroll':          ['admin'],

    # Einstellungen
    'settings.view':            ['admin'],
    'settings.edit':            ['admin'],

    # Reporting
    'reporting.view':           ['admin', 'manager'],
    'reporting.export':         ['admin', 'manager'],

    # KI-Chat
    'ai.chat':                  ['admin', 'manager', 'therapist', 'reception', 'billing'],
    'ai.destructive_actions':   ['admin', 'manager'],  # Loeschen/Aendern via KI
}


def has_permission(permission):
    """Prueft ob der aktuelle User eine Berechtigung hat."""
    if not current_user.is_authenticated:
        return False
    role = getattr(current_user, 'role', None)
    if not role:
        return False
    allowed_roles = PERMISSIONS.get(permission, [])
    return role in allowed_roles


def require_permission(permission):
    """Decorator fuer Routen die eine bestimmte Berechtigung erfordern."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not has_permission(permission):
                flash('Keine Berechtigung fuer diese Aktion.', 'error')
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def require_any_permission(*permissions):
    """Decorator: Mindestens eine der Berechtigungen muss vorhanden sein."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not any(has_permission(p) for p in permissions):
                flash('Keine Berechtigung fuer diese Aktion.', 'error')
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator
