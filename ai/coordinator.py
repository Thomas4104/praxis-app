# Koordinator-Agent: Router, delegiert an Spezialisten
# Der erste Ansprechpartner des Benutzers

import json
import anthropic
from flask import current_app
from ai.context import get_user_context, format_context_for_prompt
from ai.agents.termin_agent import create_termin_agent
from ai.agents.patienten_agent import create_patienten_agent
from ai.agents.mitarbeiter_agent import create_mitarbeiter_agent
from ai.agents.abrechnungs_agent import create_abrechnungs_agent

COORDINATOR_SYSTEM_PROMPT = """Du bist der Koordinator der OMNIA Praxissoftware. Du nimmst Anfragen entgegen und delegierst sie an spezialisierte Agenten.

Du hast folgende Spezialisten zur Verfügung:
- termin_agent: Alles rund um Kalender, Termine, Planung, Verfügbarkeit, Warteliste, Ressourcen (Räume/Geräte), intelligenter Planungsassistent mit Constraint-Solver (prüft 7 Abhängigkeiten), Serien-Terminplanung
- patienten_agent: Patientendaten, Behandlungsserien starten/anzeigen/verwalten, Behandlungsplan (Ziele, Messungen, Heilungsphasen), Templates auflisten
- mitarbeiter_agent: Personal, Arbeitszeiten, Abwesenheiten
- abrechnungs_agent: Rechnungen erstellen/anzeigen/auflisten, Tarife berechnen (311/312/338/590), Mahnwesen (3 Stufen), Zahlungen verbuchen, Gutsprachen erstellen/verwalten, offene Posten anzeigen, Tiers Garant/Payant

Wichtige Workflows:
1. "Starte eine neue Serie für Patient X": → patienten_agent (behandlungsserie_starten)
2. "Plane die Termine für die Serie": → termin_agent (serie_planen)
3. "Zeige den Behandlungsplan": → patienten_agent (behandlungsplan_anzeigen)
4. "Ist Therapeut X am Dienstag um 10:00 frei?": → termin_agent (verfuegbarkeit_pruefen)
5. "Finde den nächsten freien Termin": → termin_agent (naechster_freier_termin)
6. "Setze Patient auf die Warteliste": → termin_agent (warteliste_verwalten)
7. "Prüfe ob Raum 1 frei ist": → termin_agent (ressource_pruefen)
8. "Erstelle eine Rechnung für Serie X": → abrechnungs_agent (rechnung_erstellen)
9. "Welche Rechnungen sind offen?": → abrechnungs_agent (offene_posten_anzeigen)
10. "Sende Mahnung für Rechnung X": → abrechnungs_agent (mahnung_senden)
11. "Verbuche Zahlung": → abrechnungs_agent (zahlung_verbuchen)
12. "Erstelle Gutsprache für Patient X": → abrechnungs_agent (gutsprache_erstellen)
13. "Was kostet eine Physio-Behandlung?": → abrechnungs_agent (tarif_berechnen)
14. "Ist die Rechnung von Frau Müller bezahlt?": → abrechnungs_agent (rechnungen_auflisten)

Regeln:
- Analysiere die Anfrage und entscheide, welcher Spezialist zuständig ist
- Bei komplexen Anfragen: beauftrage mehrere Spezialisten nacheinander
- Fasse die Ergebnisse benutzerfreundlich zusammen
- Allgemeine Fragen (Smalltalk, Hilfe, Erklärungen) beantwortest du selbst
- Antworte immer auf Deutsch, kurz und professionell
- Nenne bei Patienten-Aktionen immer den vollen Namen zur Bestätigung
- Du bist freundlich und hilfsbereit
- Wenn der Benutzer eine Begrüssung sendet, begrüsse ihn zurück und biete deine Hilfe an

Beispiel für komplexen Workflow:
Benutzer: "Starte eine neue Physio-Serie für Frau Müller, 9 Termine bei Thomas, jeweils Dienstags"
→ 1. patienten_agent: patient_suchen("Müller") → patient_id finden
→ 2. patienten_agent: templates_auflisten() → Physio-Template finden
→ 3. patienten_agent: behandlungsserie_starten(patient_id, therapeut_id, template_id)
→ 4. termin_agent: serie_planen(serie_id, bevorzugter_tag=1, automatisch_buchen=true)
→ Ergebnis zusammenfassen"""

COORDINATOR_TOOLS = [
    {
        "name": "spezialist_beauftragen",
        "description": "Beauftragt einen spezialisierten Agenten mit einer Aufgabe.",
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "Name des Agenten: termin_agent, patienten_agent, mitarbeiter_agent, abrechnungs_agent",
                    "enum": ["termin_agent", "patienten_agent", "mitarbeiter_agent", "abrechnungs_agent"]
                },
                "auftrag": {
                    "type": "string",
                    "description": "Klarer Auftrag an den Spezialisten, inkl. aller relevanten Details aus der Benutzeranfrage"
                },
            },
            "required": ["agent_name", "auftrag"]
        }
    }
]

# Agenten-Cache
_agents = {}


def _get_agent(name):
    """Gibt den passenden Agenten zurück (gecacht)."""
    if name not in _agents:
        if name == 'termin_agent':
            _agents[name] = create_termin_agent()
        elif name == 'patienten_agent':
            _agents[name] = create_patienten_agent()
        elif name == 'mitarbeiter_agent':
            _agents[name] = create_mitarbeiter_agent()
        elif name == 'abrechnungs_agent':
            _agents[name] = create_abrechnungs_agent()
    return _agents.get(name)


def _execute_coordinator_tool(tool_name, tool_input):
    """Führt das Koordinator-Tool aus (delegiert an Spezialisten)."""
    if tool_name != 'spezialist_beauftragen':
        return {'error': f'Unbekanntes Tool: {tool_name}'}

    agent_name = tool_input['agent_name']
    auftrag = tool_input['auftrag']

    agent = _get_agent(agent_name)
    if not agent:
        return {'error': f'Agent nicht gefunden: {agent_name}'}

    # Kontext an Spezialisten weitergeben
    context = get_user_context()
    context_text = format_context_for_prompt(context)

    # Spezialisten ausführen
    result = agent.run(auftrag, context_text=context_text)
    return {'agent': agent_name, 'ergebnis': result}


def process_chat_message(user_message, conversation_history=None):
    """
    Verarbeitet eine Chat-Nachricht vom Benutzer.

    Args:
        user_message: Die Nachricht des Benutzers
        conversation_history: Bisherige Chat-Nachrichten [{role, content}]

    Returns:
        str: Die Antwort des Koordinators
    """
    api_key = current_app.config.get('ANTHROPIC_API_KEY', '')
    model = current_app.config.get('ANTHROPIC_MODEL', 'claude-sonnet-4-20250514')

    if not api_key:
        return 'Fehler: Kein API-Key konfiguriert. Bitte ANTHROPIC_API_KEY in der .env Datei setzen.'

    client = anthropic.Anthropic(api_key=api_key)

    # Kontext laden
    context = get_user_context()
    context_text = format_context_for_prompt(context)

    full_system = COORDINATOR_SYSTEM_PROMPT
    if context_text:
        full_system += f'\n\n--- Aktueller Kontext ---\n{context_text}'

    # Nachrichten aufbauen
    messages = []
    if conversation_history:
        for msg in conversation_history:
            messages.append({'role': msg['role'], 'content': msg['content']})
    messages.append({'role': 'user', 'content': user_message})

    # Tool-Calling-Loop
    max_iterations = 10
    for _ in range(max_iterations):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=4096,
                system=full_system,
                messages=messages,
                tools=COORDINATOR_TOOLS,
            )
        except anthropic.APIError as e:
            return f'KI-Fehler: {str(e)}'

        # Finale Antwort?
        if response.stop_reason == 'end_turn' or response.stop_reason != 'tool_use':
            text_parts = []
            for block in response.content:
                if block.type == 'text':
                    text_parts.append(block.text)
            return '\n'.join(text_parts) if text_parts else 'Ich konnte leider keine Antwort generieren.'

        # Tool-Calls verarbeiten
        assistant_content = response.content
        messages.append({'role': 'assistant', 'content': assistant_content})

        tool_results = []
        for block in assistant_content:
            if block.type == 'tool_use':
                try:
                    result = _execute_coordinator_tool(block.name, block.input)
                    tool_results.append({
                        'type': 'tool_result',
                        'tool_use_id': block.id,
                        'content': json.dumps(result, ensure_ascii=False, default=str),
                    })
                except Exception as e:
                    tool_results.append({
                        'type': 'tool_result',
                        'tool_use_id': block.id,
                        'content': f'Fehler: {str(e)}',
                        'is_error': True,
                    })

        messages.append({'role': 'user', 'content': tool_results})

    return 'Die Anfrage war zu komplex. Bitte versuche es mit einer einfacheren Frage.'
