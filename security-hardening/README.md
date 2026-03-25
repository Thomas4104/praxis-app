# OMNIA Security Hardening - Multi-Agent System

## Uebersicht

Strukturiertes 8-Phasen-Programm zur Sicherheitshaertung der OMNIA Praxissoftware.
Jede Phase setzt spezialisierte KI-Agenten ein, die parallel an unabhaengigen Aufgaben arbeiten.

## Architektur

```
Phase 1: Kritische Sofort-Fixes          ← 3 Agenten (2 parallel + 1 sequentiell)
    ↓
Phase 2: Datenverschluesselung           ← 2 Agenten (sequentiell, abhaengig)
    ↓
Phase 3: Auth & Zugriffskontrolle        ← 2 Agenten (parallel)
    ↓
Phase 4: KI-System Sicherheit            ← 2 Agenten (parallel)
    ↓
Phase 5: Audit-Logging & Compliance      ← 3 Agenten (1 sequentiell + 2 parallel)
    ↓
Phase 6: Infrastruktur-Haertung          ← 2 Agenten (parallel)
    ↓
Phase 7: Test-Suite                      ← 3 Agenten (parallel)
    ↓
Phase 8: Abschluss-Validierung           ← 1 Review-Agent
```

**Gesamt: 18 spezialisierte Agenten, davon bis zu 3 parallel**

## Voraussetzungen

- Claude Code CLI installiert (`claude` Befehl verfuegbar)
- Git-Repository initialisiert
- Python 3.12+ installiert

## Ausfuehrung

```bash
# Komplettes Programm ausfuehren:
cd /Users/thomasbalke/praxis-app
bash security-hardening/run.sh

# Nur eine bestimmte Phase:
bash security-hardening/run.sh --phase 1

# Ab einer bestimmten Phase:
bash security-hardening/run.sh --from 3

# Dry-Run (nur anzeigen):
bash security-hardening/run.sh --dry-run

# Ohne Validierung:
bash security-hardening/run.sh --skip-validate
```

## Phasen im Detail

### Phase 1: Kritische Sofort-Fixes
- Open Redirect Vulnerability fixen
- CSRF auf JSON-Endpoints
- Account-Lockout
- Health-Endpoint absichern
- Portal Organization-ID
- Portal Passwort-Policy
- Security Headers

### Phase 2: Datenverschluesselung
- Encryption-Framework (Fernet/AES)
- EncryptedString TypeDecorator
- Sensible Felder verschluesseln (AHV, IBAN, Diagnosen, SOAP)
- Migrations-Script fuer bestehende Daten

### Phase 3: Authentifizierung & Zugriffskontrolle
- TOTP-basierte 2FA
- Session-Haertung
- Passwort-Richtlinie
- RBAC Permission-System
- Rollenbasierte Route-Protection

### Phase 4: KI-System Sicherheit
- Tool-Permission-System
- Bestaetigungspflicht fuer destruktive Aktionen
- field_map Bypass Fix
- Input-Validierung fuer KI-Tools
- PII-Filter fuer API-Calls
- Rate-Limiting fuer Chat

### Phase 5: Audit-Logging & Compliance
- Erweitertes Audit-System mit HMAC-Integritaet
- Billing-Audit komplett
- SOAP-Noten-Versionierung
- Rechnungs-Immutabilitaet
- Float zu Numeric fuer Geldbetraege

### Phase 6: Infrastruktur
- Docker-Compose Haertung
- Nginx TLS-Konfiguration
- Dockerfile Non-Root User
- Verschluesselte Backups
- Dependency-Updates

### Phase 7: Test-Suite
- Auth-Tests (Login, Lockout, Redirect)
- RBAC-Tests (Rollenberechtigungen)
- Multi-Tenancy-Tests
- Verschluesselungs-Tests
- Audit-Tests
- KI-Sicherheits-Tests

### Phase 8: Abschluss-Validierung
- Checkliste aller Fixes
- Syntax-Validierung
- Abschluss-Report

## Logs

Alle Agent-Logs werden gespeichert in:
```
security-hardening/logs/
```

## Nach der Ausfuehrung

1. **Logs pruefen:** `ls security-hardening/logs/`
2. **Diff ansehen:** `git diff`
3. **Tests laufen lassen:** `python -m pytest tests/ -v`
4. **DB-Migration:** `flask db migrate -m "security hardening" && flask db upgrade`
5. **Bestehende Daten verschluesseln:** `python scripts/encrypt_existing_data.py`
6. **.env erstellen** basierend auf .env.example
7. **Manueller Review** aller Aenderungen
8. **Penetrationstest** durch externes Unternehmen empfohlen
