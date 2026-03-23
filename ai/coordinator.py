import json
import traceback
from flask import current_app
from ai.context import ContextManager
from ai.agents.allgemein_agent import AllgemeinAgent
from ai.agents.ressourcen_agent import RessourcenAgent
from ai.agents.praxis_agent import PraxisAgent
from ai.agents.mitarbeiter_agent import MitarbeiterAgent
from ai.agents.patienten_agent import PatientenAgent
from ai.agents.termin_agent import TerminAgent
from ai.agents.behandlungsplan_agent import BehandlungsplanAgent
from ai.agents.einstellungen_agent import EinstellungenAgent
from ai.agents.aufgaben_agent import AufgabenAgent


class Coordinator:
    """Koordinator: Nimmt Benutzer-Anfragen entgegen und delegiert an Spezialisten"""

    def __init__(self):
        self.agents = {
            'allgemein': AllgemeinAgent(),
            'ressourcen': RessourcenAgent(),
            'praxis': PraxisAgent(),
            'mitarbeiter': MitarbeiterAgent(),
            'patienten': PatientenAgent(),
            'termin': TerminAgent(),
            'behandlungsplan': BehandlungsplanAgent(),
            'einstellungen': EinstellungenAgent(),
            'aufgaben': AufgabenAgent()
        }

    def register_agent(self, name, agent):
        """Registriert einen neuen Spezialisten-Agenten"""
        self.agents[name] = agent

    def process(self, user_message, user=None):
        """Verarbeitet eine Benutzer-Nachricht ueber den Koordinator"""
        api_key = current_app.config.get('ANTHROPIC_API_KEY', '')
        model = current_app.config.get('ANTHROPIC_MODEL', 'claude-sonnet-4-20250514')

        if not api_key:
            return 'KI-Funktionen sind nicht verfuegbar. Bitte ANTHROPIC_API_KEY in der .env Datei konfigurieren.'

        # Kontext aufbauen
        try:
            context_text = ContextManager.build_context(user)
        except Exception:
            context_text = 'Kontext konnte nicht geladen werden.'

        # Agenten-Beschreibungen fuer den Koordinator
        agent_descriptions = []
        for name, agent in self.agents.items():
            agent_descriptions.append(f'- {name}: {agent.system_prompt[:200]}...')

        system_prompt = f"""Du bist der Koordinator der OMNIA Praxissoftware.
Deine Aufgabe ist es, Benutzer-Anfragen zu analysieren und an den richtigen Spezialisten zu delegieren.

Verfuegbare Spezialisten:
{chr(10).join(agent_descriptions)}

--- Aktueller Kontext ---
{context_text}

Regeln:
- Antworte immer auf Deutsch
- Sei freundlich und professionell
- Nutze das Tool 'spezialist_beauftragen', um Aufgaben an Spezialisten zu delegieren
- Fasse die Ergebnisse verstaendlich zusammen
- Bei einfachen Fragen (Begruessungen, allgemeine Fragen) antworte direkt ohne Tool
- Wenn du unsicher bist, frage den Benutzer nach mehr Details"""

        tools = [
            {
                'name': 'spezialist_beauftragen',
                'description': 'Beauftragt einen Spezialisten-Agenten mit einer Aufgabe. Der Spezialist hat eigene Tools und Fachwissen.',
                'input_schema': {
                    'type': 'object',
                    'properties': {
                        'agent_name': {
                            'type': 'string',
                            'description': 'Name des Spezialisten (z.B. "allgemein")',
                            'enum': list(self.agents.keys())
                        },
                        'auftrag': {
                            'type': 'string',
                            'description': 'Detaillierter Auftrag an den Spezialisten'
                        }
                    },
                    'required': ['agent_name', 'auftrag']
                }
            }
        ]

        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        messages = [{'role': 'user', 'content': user_message}]

        for iteration in range(10):
            try:
                response = client.messages.create(
                    model=model,
                    max_tokens=4096,
                    system=system_prompt,
                    tools=tools,
                    messages=messages
                )
            except Exception as e:
                current_app.logger.error(f'Koordinator API-Fehler: {e}')
                return f'Es ist ein Fehler aufgetreten. Bitte versuchen Sie es erneut.'

            text_parts = []
            tool_use_blocks = []

            for block in response.content:
                if block.type == 'text':
                    text_parts.append(block.text)
                elif block.type == 'tool_use':
                    tool_use_blocks.append(block)

            if not tool_use_blocks:
                return '\n'.join(text_parts) if text_parts else 'Keine Antwort erhalten.'

            # Tool-Aufrufe ausfuehren
            messages.append({'role': 'assistant', 'content': response.content})

            tool_results = []
            for tool_block in tool_use_blocks:
                if tool_block.name == 'spezialist_beauftragen':
                    agent_name = tool_block.input.get('agent_name')
                    auftrag = tool_block.input.get('auftrag')

                    if agent_name not in self.agents:
                        result = f'Spezialist "{agent_name}" nicht gefunden.'
                    else:
                        try:
                            agent = self.agents[agent_name]
                            result = agent.run(auftrag, context_text)
                        except Exception as e:
                            current_app.logger.error(f'Agenten-Fehler ({agent_name}): {traceback.format_exc()}')
                            result = f'Der Spezialist konnte die Aufgabe nicht ausfuehren: {str(e)}'

                    tool_results.append({
                        'type': 'tool_result',
                        'tool_use_id': tool_block.id,
                        'content': str(result)
                    })

            messages.append({'role': 'user', 'content': tool_results})

        return 'Die Anfrage war zu komplex. Bitte formulieren Sie sie einfacher.'
