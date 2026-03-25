Du bist ein Security QA Engineer. Validiere Phase 4 (KI-Sicherheit) in /Users/thomasbalke/praxis-app.

1. Existiert /Users/thomasbalke/praxis-app/ai/tool_permissions.py?
   - CONFIRMATION_REQUIRED Set vorhanden?
   - TOOL_PERMISSIONS Dict vorhanden?
   - can_use_tool() Funktion vorhanden?

2. Existiert /Users/thomasbalke/praxis-app/ai/pii_filter.py?
   - redact_pii() Funktion vorhanden?
   - filter_dict() Funktion vorhanden?
   - sanitize_tool_result() Funktion vorhanden?

3. /Users/thomasbalke/praxis-app/ai/base_agent.py
   - Wird can_use_tool() vor Tool-Aufruf geprueft?
   - Wird sanitize_tool_result() auf Ergebnisse angewendet?
   - Werden Tool-Aufrufe geloggt?

4. /Users/thomasbalke/praxis-app/blueprints/patients/ai_tools.py
   - field_map Bypass gefixt (kein Fallback auf key)?
   - AHV-Nummer nicht mehr in Tool-Output?

5. Chat-Rate-Limiting vorhanden?

Syntax-Checks. Zusammenfassung.
