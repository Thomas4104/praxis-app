# Basis-Klasse für alle KI-Agenten
# Implementiert den Tool-Calling-Loop mit der Claude API

import json
import anthropic
from flask import current_app


class BaseAgent:
    """Basis-Klasse für alle Agenten. Implementiert den Tool-Calling-Loop."""

    def __init__(self, name, system_prompt, tools, tool_executor):
        """
        Args:
            name: Name des Agenten (z.B. 'termin_agent')
            system_prompt: System-Prompt mit Fachwissen
            tools: Liste der Tool-Definitionen (Anthropic-Format)
            tool_executor: Funktion die tool_name + tool_input entgegennimmt und Ergebnis liefert
        """
        self.name = name
        self.system_prompt = system_prompt
        self.tools = tools
        self.tool_executor = tool_executor

    def run(self, user_message, context_text='', conversation_history=None):
        """
        Führt den Agenten aus mit Tool-Calling-Loop.

        Args:
            user_message: Die Nachricht des Benutzers oder Auftrags
            context_text: Zusätzlicher Kontext (Benutzer, Standort, etc.)
            conversation_history: Bisherige Nachrichten für Kontext

        Returns:
            str: Die finale Antwort des Agenten
        """
        api_key = current_app.config.get('ANTHROPIC_API_KEY', '')
        model = current_app.config.get('ANTHROPIC_MODEL', 'claude-sonnet-4-20250514')

        if not api_key:
            return 'Fehler: Kein API-Key konfiguriert. Bitte ANTHROPIC_API_KEY in .env setzen.'

        client = anthropic.Anthropic(api_key=api_key)

        # System-Prompt mit Kontext erweitern
        full_system = self.system_prompt
        if context_text:
            full_system += f'\n\n--- Aktueller Kontext ---\n{context_text}'

        # Nachrichten vorbereiten
        messages = []
        if conversation_history:
            messages.extend(conversation_history)
        messages.append({'role': 'user', 'content': user_message})

        # Tool-Calling-Loop (max 10 Iterationen zur Sicherheit)
        max_iterations = 10
        for _ in range(max_iterations):
            try:
                kwargs = {
                    'model': model,
                    'max_tokens': 4096,
                    'system': full_system,
                    'messages': messages,
                }
                if self.tools:
                    kwargs['tools'] = self.tools

                response = client.messages.create(**kwargs)
            except anthropic.APIError as e:
                return f'KI-Fehler: {str(e)}'

            # Antwort verarbeiten
            if response.stop_reason == 'end_turn' or response.stop_reason != 'tool_use':
                # Finale Antwort - Text extrahieren
                text_parts = []
                for block in response.content:
                    if block.type == 'text':
                        text_parts.append(block.text)
                return '\n'.join(text_parts) if text_parts else 'Keine Antwort erhalten.'

            # Tool-Calls verarbeiten
            assistant_content = response.content
            messages.append({'role': 'assistant', 'content': assistant_content})

            tool_results = []
            for block in assistant_content:
                if block.type == 'tool_use':
                    tool_name = block.name
                    tool_input = block.input
                    tool_id = block.id

                    # Tool ausführen
                    try:
                        result = self.tool_executor(tool_name, tool_input)
                        tool_results.append({
                            'type': 'tool_result',
                            'tool_use_id': tool_id,
                            'content': json.dumps(result, ensure_ascii=False, default=str) if not isinstance(result, str) else result,
                        })
                    except Exception as e:
                        tool_results.append({
                            'type': 'tool_result',
                            'tool_use_id': tool_id,
                            'content': f'Fehler bei Tool-Ausführung: {str(e)}',
                            'is_error': True,
                        })

            messages.append({'role': 'user', 'content': tool_results})

        return 'Die Anfrage war zu komplex. Bitte vereinfache deine Frage.'
