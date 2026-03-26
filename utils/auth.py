"""Autorisierungs-Hilfsfunktionen fuer Multi-Tenancy"""
from flask import abort
from flask_login import current_user


def check_org(obj):
    """Prueft ob ein Objekt zur Organisation des aktuellen Users gehoert."""
    if not hasattr(obj, 'organization_id'):
        return
    if obj.organization_id != current_user.organization_id:
        abort(403)


def get_org_id():
    """Gibt die organization_id des aktuellen Users zurueck."""
    return current_user.organization_id
