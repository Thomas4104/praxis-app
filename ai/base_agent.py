import json
import traceback
from flask import current_app
from ai.tool_permissions import can_use_tool, requires_confirmation
from ai.pii_filter import sanitize_tool_result


class BaseAgent:
    """Basis-Klasse fuer alle KI-Agenten mit Tool-Calling-Loop"""

    def __init__(self, name, system_prompt, tools, tool_executor):
        self.name = name
        self.system_prompt = system_prompt
        self.tools = tools
        self.tool_executor = tool_executor
        self.max_iterations = 10

    def run(self, auftrag, context_text=''):
        """Fuehrt den Agenten mit Tool-Calling-Loop aus"""
        api_key = current_app.config.get('ANTHROPIC_API_KEY', '')
        model = current_app.config.get('ANTHROPIC_MODEL', 'claude-sonnet-4-20250514')

        if not api_key:
            return 'KI-Funktionen sind nicht verfuegbar. Bitte ANTHROPIC_API_KEY konfigurieren.'

        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        # System-Prompt mit Kontext aufbauen
        full_system = self.system_prompt
        if context_text:
            full_system += f'\n\n--- Aktueller Kontext ---\n{context_text}'

        messages = [{'role': 'user', 'content': auftrag}]

        for iteration in range(self.max_iterations):
            try:
                response = client.messages.create(
                    model=model,
                    max_tokens=4096,
                    system=full_system,
                    tools=self.tools if self.tools else [],
                    messages=messages
                )
            except Exception as e:
                current_app.logger.error(f'KI-API Fehler: {e}')
                return f'Es ist ein Fehler bei der KI-Verarbeitung aufgetreten: {str(e)}'

            # Antwort verarbeiten
            text_parts = []
            tool_use_blocks = []

            for block in response.content:
                if block.type == 'text':
                    text_parts.append(block.text)
                elif block.type == 'tool_use':
                    tool_use_blocks.append(block)

            # Wenn keine Tool-Aufrufe, Text zurueckgeben
            if not tool_use_blocks:
                return '\n'.join(text_parts) if text_parts else 'Keine Antwort erhalten.'

            # Tool-Aufrufe ausfuehren
            messages.append({'role': 'assistant', 'content': response.content})

            tool_results = []
            for tool_block in tool_use_blocks:
                try:
                    # Berechtigungspruefung vor Tool-Ausfuehrung
                    if not can_use_tool(tool_block.name):
                        result = {
                            'error': f'Keine Berechtigung fuer Tool: {tool_block.name}. '
                                     f'Ihre Rolle erlaubt dieses Tool nicht.'
                        }
                    elif requires_confirmation(tool_block.name):
                        result = {
                            'confirmation_required': True,
                            'tool': tool_block.name,
                            'input': tool_block.input,
                            'message': f'Diese Aktion erfordert Ihre Bestaetigung: {tool_block.name}'
                        }
                    else:
                        result = self.tool_executor(tool_block.name, tool_block.input)
                    result = sanitize_tool_result(tool_block.name, result)

                    # Audit-Logging nach Tool-Aufruf
                    try:
                        from services.audit_service import log_action
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
                    except Exception:
                        current_app.logger.warning(f'Audit-Log fuer Tool {tool_block.name} fehlgeschlagen')

                    tool_results.append({
                        'type': 'tool_result',
                        'tool_use_id': tool_block.id,
                        'content': json.dumps(result, ensure_ascii=False, default=str)
                    })
                except Exception as e:
                    current_app.logger.error(f'Tool-Fehler ({tool_block.name}): {traceback.format_exc()}')
                    tool_results.append({
                        'type': 'tool_result',
                        'tool_use_id': tool_block.id,
                        'content': json.dumps({'error': str(e)}, ensure_ascii=False),
                        'is_error': True
                    })

            messages.append({'role': 'user', 'content': tool_results})

        return 'Maximale Anzahl an Verarbeitungsschritten erreicht. Bitte versuchen Sie es erneut.'
