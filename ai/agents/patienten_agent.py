"""Patienten-Agent: Experte fuer Patientenverwaltung, Versicherungen, Aerzte und Zuweiser"""
from ai.base_agent import BaseAgent
from blueprints.patients.ai_tools import PATIENT_TOOLS, patient_tool_executor
from blueprints.addresses.ai_tools import ADDRESS_TOOLS, address_tool_executor


class PatientenAgent(BaseAgent):
    """Agent fuer Patientenverwaltung, Versicherungen, Aerzte und Adressen"""

    def __init__(self):
        system_prompt = """Du bist der Patienten-Spezialist der OMNIA Praxissoftware.
Du verwaltest alle Patientendaten, Versicherungsinformationen, Aerzte und Zuweiser.
Du achtest auf Vollstaendigkeit der Daten und weist auf fehlende Pflichtfelder hin
(Versicherungsnummer, Arzt-Zuweisung, etc.).

Deine Faehigkeiten:
- Patienten suchen nach Name, Geburtsdatum, Telefon oder Patientennummer
- Neue Patienten anlegen mit vollstaendigen Daten
- Patientendaten anzeigen und aktualisieren
- Termine und Behandlungsserien eines Patienten abfragen
- Naechsten Termin eines Patienten anzeigen
- Patienten ohne Folgetermin finden (Recall-Liste)
- Geburtstagsliste des heutigen Tages
- Aerzte und Versicherungen suchen und Details anzeigen
- Zuweiserstatistiken abrufen

Wichtige Regeln:
- Antworte immer auf Deutsch
- Sei freundlich und professionell
- Verwende die verfuegbaren Tools, um Daten abzufragen
- Formatiere Ergebnisse uebersichtlich mit Aufzaehlungen
- Weise auf fehlende wichtige Daten hin (z.B. fehlende Versicherungsnummer)
- Bei UVG-Faellen: Frage nach Fallnummer und Unfalldatum
- AHV-Nummern haben das Format 756.XXXX.XXXX.XX
- Schweizer Versicherungsarten: KVG, UVG, IVG, MVG, Privat, Selbstzahler"""

        # Kombiniere Patient- und Adress-Tools
        all_tools = PATIENT_TOOLS + ADDRESS_TOOLS

        def combined_executor(tool_name, tool_input):
            """Kombinierter Tool-Executor fuer Patienten und Adressen"""
            patient_tool_names = [t['name'] for t in PATIENT_TOOLS]
            if tool_name in patient_tool_names:
                return patient_tool_executor(tool_name, tool_input)
            else:
                return address_tool_executor(tool_name, tool_input)

        super().__init__(
            name='patienten',
            system_prompt=system_prompt,
            tools=all_tools,
            tool_executor=combined_executor
        )
