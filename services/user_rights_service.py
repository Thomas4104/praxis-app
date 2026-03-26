"""
Feingranulares Berechtigungssystem nach Cenplex-Vorbild.
Berechtigungen werden als JSON im Employee.user_rights_json gespeichert.
"""
import json
from functools import wraps
from flask import abort
from flask_login import current_user


# Standard-Rechte-Struktur (Cenplex: UserRights)
DEFAULT_RIGHTS = {
    'version': 1,
    'invoice': {
        'can_read': True, 'can_edit': False, 'can_send': False,
        'can_delete': False, 'can_cancel': False, 'can_delete_payment': False,
        'can_close': False
    },
    'kostengutsprache': {'can_read': True, 'can_edit': False},
    'patient': {'can_read': True, 'can_edit': False},
    'employee': {
        'can_read': False, 'can_edit': False, 'can_edit_vacation': False,
        'can_edit_work_schedule': False, 'can_edit_room_plan': False,
        'only_personal': True, 'can_delete_vacation': False,
        'can_add_vacation': False, 'can_edit_vacation_requests': False
    },
    'calendar': {'can_read': True, 'can_edit': True},
    'product': {'can_read': True, 'can_edit': False},
    'resource': {'can_read': True, 'can_edit': False},
    'statistic': {'can_read': False, 'can_edit': False, 'allowed_categories': []},
    'fitness': {'can_read': False, 'can_edit': False, 'can_change_abo': False},
    'setting': {'can_read': False, 'can_edit': False},
    'dashboard': {'can_read': True},
    'mailing': {'can_read': True, 'can_edit': False},
    'address': {'can_read': True, 'can_edit': False},
    'practice': {'can_read': False, 'can_edit': False},
    'kpi': {'can_edit': False, 'allowed_categories': []},
    'archive': {'can_read': False},
    'invoice_validation': {'can_read': False}
}

# Admin hat alle Rechte
ADMIN_RIGHTS = {key: {k: True if isinstance(v, bool) else v for k, v in val.items()}
                if isinstance(val, dict) else val
                for key, val in DEFAULT_RIGHTS.items()}
ADMIN_RIGHTS['version'] = 1


def get_user_rights(employee=None):
    """Laedt Berechtigungen fuer einen Mitarbeiter"""
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

    # Individuelle Rechte aus JSON
    if employee.user_rights_json:
        try:
            rights = json.loads(employee.user_rights_json)
            # Merge mit Default-Rechten (fehlende Keys auffuellen)
            merged = json.loads(json.dumps(DEFAULT_RIGHTS))
            for section, perms in rights.items():
                if section in merged and isinstance(perms, dict):
                    merged[section].update(perms)
                else:
                    merged[section] = perms
            return merged
        except (json.JSONDecodeError, TypeError):
            pass

    # Gruppen-Rechte pruefen
    if employee.user_groups_json:
        try:
            group_ids = json.loads(employee.user_groups_json)
            from models import EmployeeGroup
            groups = EmployeeGroup.query.filter(EmployeeGroup.id.in_(group_ids)).all()
            # Rechte aus allen Gruppen zusammenfuehren (OR-Logik)
            merged = json.loads(json.dumps(DEFAULT_RIGHTS))
            for group in groups:
                if group.user_rights_json:
                    group_rights = json.loads(group.user_rights_json)
                    for section, perms in group_rights.items():
                        if section in merged and isinstance(perms, dict):
                            for k, v in perms.items():
                                if isinstance(v, bool) and v:
                                    merged[section][k] = True
                                elif isinstance(v, list):
                                    existing = merged[section].get(k, [])
                                    merged[section][k] = list(set(existing + v))
            return merged
        except (json.JSONDecodeError, TypeError):
            pass

    # Rollen-basierte Defaults
    if user:
        if user.role == 'therapist':
            rights = json.loads(json.dumps(DEFAULT_RIGHTS))
            rights['patient']['can_edit'] = True
            rights['calendar']['can_edit'] = True
            return rights
        elif user.role == 'reception':
            rights = json.loads(json.dumps(DEFAULT_RIGHTS))
            rights['patient']['can_edit'] = True
            rights['calendar']['can_edit'] = True
            rights['invoice']['can_read'] = True
            rights['address']['can_edit'] = True
            return rights

    return DEFAULT_RIGHTS


def has_right(section, permission='can_read'):
    """Prueft ob aktueller Benutzer eine bestimmte Berechtigung hat"""
    rights = get_user_rights()
    section_rights = rights.get(section, {})
    if isinstance(section_rights, dict):
        return section_rights.get(permission, False)
    return False


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
    """Speichert Berechtigungen fuer einen Mitarbeiter"""
    from models import Employee, db
    employee = Employee.query.get(employee_id)
    if employee:
        employee.user_rights_json = json.dumps(rights_dict)
        db.session.commit()
    return employee
