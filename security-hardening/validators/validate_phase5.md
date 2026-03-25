Du bist ein Security QA Engineer. Validiere Phase 5 (Audit & Compliance) in /Users/thomasbalke/praxis-app.

1. /Users/thomasbalke/praxis-app/services/audit_service.py
   - Erweitert mit HMAC-Integritaet?
   - _sanitize_changes() Funktion vorhanden?
   - log_data_export() Funktion vorhanden?

2. AuditLog Model: integrity_hash Feld vorhanden?

3. Billing-Audit: Sind in billing/routes.py log_action() Aufrufe fuer:
   - Rechnungserstellung?
   - Rechnungsversand?
   - Zahlungserfassung?
   - Stornierung?

4. SoapNoteHistory Model vorhanden in models.py?
   - appointment_id, version, changed_by_id, content_hash?

5. SOAP-Speichern Route: Erstellt History-Eintraege?

6. Invoice-Immutabilitaet: Versendete Rechnungen geschuetzt?

7. Float -> Numeric fuer Geldbetraege?

Syntax-Checks. Zusammenfassung.
