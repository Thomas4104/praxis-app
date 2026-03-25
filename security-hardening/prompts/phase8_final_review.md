Du bist der Lead Security Architect. Dein Auftrag: Finale Validierung aller Security-Haertungen in /Users/thomasbalke/praxis-app.

Erstelle einen abschliessenden Security-Report.

## Schritt 1: Pruefliste durchgehen

Pruefe JEDE der folgenden Dateien und bestaetige den Status:

### Auth & Session
- [ ] /Users/thomasbalke/praxis-app/blueprints/auth/routes.py - Open Redirect gefixt?
- [ ] /Users/thomasbalke/praxis-app/blueprints/auth/routes.py - Account Lockout implementiert?
- [ ] /Users/thomasbalke/praxis-app/blueprints/auth/routes.py - 2FA implementiert?
- [ ] /Users/thomasbalke/praxis-app/config.py - Session-Cookies gehaertet?

### CSRF & Headers
- [ ] /Users/thomasbalke/praxis-app/blueprints/dashboard/routes.py - CSRF auf JSON-Endpoints?
- [ ] /Users/thomasbalke/praxis-app/app.py - Content-Security-Policy Header?
- [ ] /Users/thomasbalke/praxis-app/app.py - Health-Endpoint keine Details bei Fehler?

### Verschluesselung
- [ ] /Users/thomasbalke/praxis-app/utils/encryption.py - Existiert und funktional?
- [ ] /Users/thomasbalke/praxis-app/models.py - Sensible Felder verschluesselt?
- [ ] AHV-Nummer, IBAN, Diagnosen, SOAP-Noten - EncryptedString?

### RBAC
- [ ] /Users/thomasbalke/praxis-app/utils/permissions.py - Existiert?
- [ ] Billing-Routen geschuetzt?
- [ ] Settings-Routen geschuetzt?
- [ ] Treatment/SOAP-Routen geschuetzt?

### KI-Sicherheit
- [ ] /Users/thomasbalke/praxis-app/ai/tool_permissions.py - Existiert?
- [ ] /Users/thomasbalke/praxis-app/ai/pii_filter.py - Existiert?
- [ ] base_agent.py - Tool-Permission-Check eingebaut?
- [ ] patient_bearbeiten - field_map Bypass gefixt?

### Audit & Compliance
- [ ] audit_service.py - Erweitert mit HMAC-Integritaet?
- [ ] Billing-Operationen geloggt?
- [ ] SOAP-Versionierung implementiert?
- [ ] Rechnungs-Immutabilitaet?

### Infrastruktur
- [ ] docker-compose.yml - Keine exponierten DB-Ports?
- [ ] docker-compose.yml - Keine hardcoded Credentials?
- [ ] nginx.conf - TLS konfiguriert?
- [ ] Dockerfile - Non-root User?
- [ ] backup.sh - Verschluesselung?

### Tests
- [ ] tests/conftest.py - Existiert?
- [ ] tests/test_auth.py - Existiert?
- [ ] tests/test_rbac.py - Existiert?
- [ ] tests/test_audit.py - Existiert?
- [ ] tests/test_ai_security.py - Existiert?

## Schritt 2: Syntax-Validierung

Fuehre fuer JEDE geaenderte Python-Datei aus:
```bash
python3 -c "import ast; ast.parse(open('DATEI').read()); print('OK: DATEI')"
```

## Schritt 3: Report erstellen

Erstelle: /Users/thomasbalke/praxis-app/security-hardening/SECURITY_REPORT.md

Format:
```markdown
# OMNIA Praxissoftware - Security Hardening Report
Datum: [aktuelles Datum]

## Zusammenfassung
[Anzahl behobene Schwachstellen / offene Punkte]

## Phase 1: Kritische Sofort-Fixes
| Fix | Status | Datei |
|-----|--------|-------|
| Open Redirect | OK/OFFEN | auth/routes.py |
| ... | ... | ... |

## Phase 2: Datenverschluesselung
...

## Phase 3: Auth & RBAC
...

## Phase 4: KI-Sicherheit
...

## Phase 5: Audit & Compliance
...

## Phase 6: Infrastruktur
...

## Phase 7: Tests
...

## Offene Punkte / Empfehlungen
[Was noch zu tun ist]

## Naechste Schritte
1. Alle Tests ausfuehren: python -m pytest tests/ -v
2. DB-Migration erstellen: flask db migrate -m "security hardening"
3. Bestehende Daten verschluesseln: python scripts/encrypt_existing_data.py
4. .env Datei mit echten Secrets erstellen
5. Penetrationstest durch externes Unternehmen
```

## Reihenfolge:
1. Gehe die Pruefliste durch (lies jede Datei)
2. Fuehre Syntax-Validierung aus
3. Erstelle den Report
