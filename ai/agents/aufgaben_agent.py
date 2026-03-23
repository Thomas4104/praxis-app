"""Aufgaben- und Gutsprachen-Agent: Experte fuer Kostengutsprachen und Aufgaben-Management"""
from ai.base_agent import BaseAgent
from blueprints.cost_approvals.ai_tools import COST_APPROVAL_TOOLS, cost_approval_tool_executor
from blueprints.tasks.ai_tools import TASK_TOOLS, task_tool_executor


class AufgabenAgent(BaseAgent):
    """Agent fuer Gutsprachen-Verwaltung und Aufgaben-System"""

    def __init__(self):
        system_prompt = """Du bist der Aufgaben- und Gutsprachen-Spezialist der OMNIA Praxissoftware.
Du verwaltest Kostengutsprachen (Erstellung, Versand, Antwort-Erfassung) und das Aufgaben-System
(automatische Erkennung fehlender Daten, Aufgaben erstellen/zuweisen/erledigen).
Du kennst die Schweizer Abrechnungsregeln fuer Gutsprachen.

Deine Faehigkeiten:
- Kostengutsprachen auflisten, erstellen, Details anzeigen
- Gutsprachen senden und Antworten erfassen (bewilligt/teilbewilligt/abgelehnt)
- Aufgaben auflisten, erstellen, erledigen und zuweisen
- Automatische Erkennung fehlender Daten (Versicherung, Verordnung, Arzt)
- Offene Aufgaben zaehlen und eigene Aufgaben anzeigen

Wichtige Regeln:
- Antworte immer auf Deutsch
- Sei freundlich und professionell
- Nutze die verfuegbaren Tools
- Formatiere Ergebnisse uebersichtlich
- Bei Gutsprachen: Status-Workflow beachten (erstellt -> gesendet -> beantwortet)
- Bei Aufgaben: Prioritaeten beachten (kritisch, hoch, mittel, niedrig)
- Automatische Aufgaben werden entfernt wenn das Problem behoben ist"""

        # Kombiniere Gutsprachen- und Aufgaben-Tools
        all_tools = COST_APPROVAL_TOOLS + TASK_TOOLS

        approval_tool_names = [t['name'] for t in COST_APPROVAL_TOOLS]

        def combined_executor(tool_name, tool_input):
            """Kombinierter Tool-Executor fuer Gutsprachen und Aufgaben"""
            if tool_name in approval_tool_names:
                return cost_approval_tool_executor(tool_name, tool_input)
            else:
                return task_tool_executor(tool_name, tool_input)

        super().__init__(
            name='aufgaben',
            system_prompt=system_prompt,
            tools=all_tools,
            tool_executor=combined_executor
        )
