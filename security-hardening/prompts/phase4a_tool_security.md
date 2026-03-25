Du bist ein KI-Sicherheitsexperte. Dein Auftrag: Das AI-Tool-System in /Users/thomasbalke/praxis-app/ai/ absichern.

WICHTIG: Lies IMMER zuerst ALLE Dateien im ai/ Verzeichnis und die ai_tools.py Dateien in den Blueprints.

## Aufgabe 1: Tool-Permission-System erstellen
Erstelle: /Users/thomasbalke/praxis-app/ai/tool_permissions.py

```python
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
        'patient_suchen', 'patient_details', 'termine_heute',
        'termine_suchen', 'rechnungen_suchen', 'mitarbeiter_suchen',
        'aufgaben_suchen', 'ressourcen_suchen', 'produkte_suchen',
    },
    # Therapeuten-Tools
    'therapist': {
        'termin_erstellen', 'termin_bearbeiten', 'soap_speichern',
        'serie_erstellen', 'therapieziel_erstellen',
    },
    # Empfangs-Tools
    'reception': {
        'termin_erstellen', 'termin_bearbeiten', 'termin_verschieben',
        'patient_erstellen', 'patient_bearbeiten',
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
```

## Aufgabe 2: Base-Agent absichern
Datei: /Users/thomasbalke/praxis-app/ai/base_agent.py

Finde die Stelle wo Tools ausgefuehrt werden (vermutlich die Schleife mit `self.tool_executor(tool_block.name, tool_block.input)`).

Fuege VOR dem Tool-Aufruf die Berechtigungspruefung ein:
```python
from ai.tool_permissions import can_use_tool, requires_confirmation

# Vor tool_executor Aufruf:
if not can_use_tool(tool_block.name):
    result = {
        'error': f'Keine Berechtigung fuer Tool: {tool_block.name}. '
                 f'Ihre Rolle erlaubt dieses Tool nicht.'
    }
else:
    if requires_confirmation(tool_block.name):
        result = {
            'confirmation_required': True,
            'tool': tool_block.name,
            'input': tool_block.input,
            'message': f'Diese Aktion erfordert Ihre Bestaetigung: {tool_block.name}'
        }
    else:
        result = self.tool_executor(tool_block.name, tool_block.input)
```

## Aufgabe 3: field_map Bypass in patient_bearbeiten fixen
Datei: /Users/thomasbalke/praxis-app/blueprints/patients/ai_tools.py

Finde die `patient_bearbeiten` Tool-Implementierung. Dort gibt es vermutlich:
```python
db_field = field_map.get(key, key)  # BUG: Fallback auf key
```

Fix: NUR Felder aus field_map erlauben:
```python
for key, value in felder.items():
    db_field = field_map.get(key)
    if db_field is None:
        continue  # Unbekanntes Feld ignorieren statt durchlassen
    if hasattr(patient, db_field):
        setattr(patient, db_field, value)
        updated.append(key)
```

## Aufgabe 4: Input-Validierung fuer KI-Tools
Finde in den ai_tools.py Dateien die Tool-Executors und fuege Validierung hinzu.

Speziell fuer termin_erstellen (vermutlich in calendar/ai_tools.py):
```python
# Dauer validieren
dauer = tool_input.get('dauer', 30)
if not isinstance(dauer, int) or dauer < 5 or dauer > 480:
    return {'error': 'Dauer muss zwischen 5 und 480 Minuten liegen.'}

# Datum validieren
from datetime import date, datetime, timedelta
try:
    datum = datetime.strptime(tool_input['datum'], '%Y-%m-%d').date()
except (ValueError, KeyError):
    return {'error': 'Ungueltiges Datumsformat. Erwartet: YYYY-MM-DD'}

if datum < date.today():
    return {'error': 'Termine koennen nicht in der Vergangenheit erstellt werden.'}
if datum > date.today() + timedelta(days=365):
    return {'error': 'Termine koennen maximal 1 Jahr im Voraus erstellt werden.'}
```

## Aufgabe 5: KI-Audit-Logging
Datei: /Users/thomasbalke/praxis-app/ai/base_agent.py

Fuege nach jedem Tool-Aufruf ein Audit-Log hinzu:
```python
from services.audit_service import log_action

# Nach erfolgreichem Tool-Aufruf:
log_action(
    f'ai_tool_{tool_block.name}',
    'ai_agent',
    0,
    changes={
        'agent': self.__class__.__name__,
        'tool': tool_block.name,
        'input_keys': list(tool_block.input.keys()) if tool_block.input else [],
    }
)
```

## Reihenfolge:
1. Lies ALLE ai/*.py Dateien und ALLE blueprints/*/ai_tools.py Dateien
2. Erstelle ai/tool_permissions.py
3. Aktualisiere base_agent.py
4. Fixe patient_bearbeiten field_map
5. Fuege Input-Validierung hinzu
6. Fuege Audit-Logging hinzu
7. Syntax-Checks
