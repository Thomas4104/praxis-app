"""Ressourcen-Agent: Experte fuer Produkte, Raeume, Geraete und Lagerbestand"""
from ai.base_agent import BaseAgent
from blueprints.products.ai_tools import PRODUCT_TOOLS, product_tool_executor
from blueprints.resources.ai_tools import RESOURCE_TOOLS, resource_tool_executor


# Alle Tools zusammenfuehren
ALL_TOOLS = PRODUCT_TOOLS + RESOURCE_TOOLS


def combined_tool_executor(tool_name, tool_input):
    """Fuehrt Tools aus beiden Bereichen aus"""
    # Produkt-Tools
    product_tool_names = [t['name'] for t in PRODUCT_TOOLS]
    if tool_name in product_tool_names:
        return product_tool_executor(tool_name, tool_input)

    # Ressourcen-Tools
    resource_tool_names = [t['name'] for t in RESOURCE_TOOLS]
    if tool_name in resource_tool_names:
        return resource_tool_executor(tool_name, tool_input)

    return {'error': f'Unbekanntes Tool: {tool_name}'}


class RessourcenAgent(BaseAgent):
    """Agent fuer Produkte, Ressourcen, Lagerbestand und Wartung"""

    def __init__(self):
        system_prompt = """Du bist der Ressourcen-Experte der OMNIA Praxissoftware.
Du hilfst bei allen Fragen rund um Produkte, Raeume, Geraete und Lagerbestand.

Deine Faehigkeiten:
- Produkte suchen und Details anzeigen
- Lagerbestaende pruefen und Nachbestellbedarf erkennen
- Raeume und Geraete suchen
- Verfuegbarkeit von Ressourcen pruefen
- Freie Raeume finden
- Wartungsstatus von Geraeten pruefen

Wichtige Regeln:
- Antworte immer auf Deutsch
- Sei freundlich und professionell
- Verwende die verfuegbaren Tools, um Daten abzufragen
- Formatiere Ergebnisse uebersichtlich mit Aufzaehlungen
- Wenn Produkte unter Mindestbestand liegen, weise darauf hin
- Wenn Wartungen ueberfaellig sind, warne deutlich
- Gib bei Preisen immer CHF als Waehrung an"""

        super().__init__(
            name='ressourcen',
            system_prompt=system_prompt,
            tools=ALL_TOOLS,
            tool_executor=combined_tool_executor
        )
