"""
Berechtigungssystem fuer KI-Agent-Tools.
Kontrolliert welche Tools von welchen Rollen ausgefuehrt werden duerfen
und welche Tools eine Bestaetigung erfordern.
"""
from flask_login import current_user

# Tools die eine explizite User-Bestaetigung erfordern
CONFIRMATION_REQUIRED = {
    'patient_deaktivieren',
    'patient_loeschen',
    'zahlung_verbuchen',
    'mahnlauf_starten',
    'rechnung_stornieren',
    'serie_abschliessen',
    'termin_absagen',
    'mitarbeiter_bearbeiten',
}

# Tools gruppiert nach Berechtigung
TOOL_PERMISSIONS = {
    # Lesende Tools - alle Rollen
    'read': {
        'patient_suchen', 'patient_details', 'patient_termine',
        'patient_serien', 'naechster_termin', 'patienten_ohne_folgetermin',
        'geburtstage_heute', 'arzt_suchen', 'versicherung_suchen',
        'termine_anzeigen', 'termine_patient', 'tagesplan',
        'naechster_freier_termin', 'verfuegbarkeit_pruefen',
        'luecken_finden', 'termine_suchen', 'rechnungen_suchen',
        'mitarbeiter_suchen', 'aufgaben_suchen', 'ressourcen_suchen',
        'produkte_suchen',
    },
    # Therapeuten-Tools
    'therapist': {
        'termin_erstellen', 'termin_bearbeiten', 'termin_status_aendern',
        'soap_speichern', 'serie_erstellen', 'serie_planen',
        'therapieziel_erstellen',
    },
    # Empfangs-Tools
    'reception': {
        'termin_erstellen', 'termin_bearbeiten', 'termin_verschieben',
        'termin_status_aendern', 'patient_erstellen', 'patient_bearbeiten',
        'warteliste_hinzufuegen',
    },
    # Abrechnungs-Tools
    'billing': {
        'rechnung_erstellen', 'rechnung_senden', 'zahlung_verbuchen',
    },
    # Admin-only Tools
    'admin': {
        'patient_deaktivieren', 'mahnlauf_starten', 'rechnung_stornieren',
        'einstellungen_aendern', 'mitarbeiter_bearbeiten',
    },
}

# Rollen-Zuordnung zu Tool-Gruppen
ROLE_TOOL_ACCESS = {
    'admin':     ['read', 'therapist', 'reception', 'billing', 'admin'],
    'manager':   ['read', 'therapist', 'reception', 'billing'],
    'therapist': ['read', 'therapist'],
    'reception': ['read', 'reception'],
    'billing':   ['read', 'billing'],
}


def can_use_tool(tool_name, user=None):
    """Prueft ob der User ein bestimmtes Tool verwenden darf."""
    if user is None:
        user = current_user
    role = getattr(user, 'role', 'reception')
    allowed_groups = ROLE_TOOL_ACCESS.get(role, ['read'])
    for group in allowed_groups:
        if tool_name in TOOL_PERMISSIONS.get(group, set()):
            return True
    return False


def requires_confirmation(tool_name):
    """Prueft ob ein Tool eine User-Bestaetigung erfordert."""
    return tool_name in CONFIRMATION_REQUIRED


def get_allowed_tools(user=None):
    """Gibt alle erlaubten Tools fuer den User zurueck."""
    if user is None:
        user = current_user
    role = getattr(user, 'role', 'reception')
    allowed_groups = ROLE_TOOL_ACCESS.get(role, ['read'])
    tools = set()
    for group in allowed_groups:
        tools.update(TOOL_PERMISSIONS.get(group, set()))
    return tools
