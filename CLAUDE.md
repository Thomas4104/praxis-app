# OMNIA Praxissoftware

## Was ist das?
Webbasierte Praxis-Planungssoftware für Physiotherapie-, Psychotherapie- und Arztpraxen in der Schweiz. KI-zentriert mit Anthropic Claude API.

## Technischer Stack
- **Backend:** Python 3.12, Flask 3.x, SQLAlchemy ORM, SQLite (Production: PostgreSQL)
- **Frontend:** HTML5, CSS3, Vanilla JavaScript (kein React/Vue)
- **KI:** Anthropic Claude API mit Multi-Agent-System (15 spezialisierte Agenten)
- **Auth:** Flask-Login, rollenbasiert (admin/therapist/reception)
- **Server:** Ubuntu 24.04, Gunicorn, nginx, SSL via Let's Encrypt

## Deployment
- **GitHub:** https://github.com/Thomas4104/praxis-app
- **Server:** ubuntu@83.228.241.233 (SSH Key: ~/.ssh/OMNIA_Infomaniak)
- **URL:** https://app.omnia-health.ch
- **Login Demo:** admin/admin, thomas/thomas, sarah/sarah, lisa/lisa

## Struktur
- `app.py` — App-Factory, create_app(), 20 Blueprints
- `models.py` — 69 Model-Klassen, alle mit Indexes und updated_at
- `config.py` — Dev/Prod/Test Config, SECRET_KEY erzwungen
- `ai/` — KI-System: coordinator.py, base_agent.py, 15 Agenten in agents/
- `blueprints/` — 20 Module (auth, dashboard, patients, calendar, billing, etc.)
- `services/` — audit_service.py, settings_service.py, billing_service.py
- `utils/auth.py` — check_org(), get_org_id() für Multi-Tenancy
- `templates/base.html` — Hauptlayout mit Sidebar, KI-Chat, rollenbasierte Nav
- `static/js/` — app.js, chat.js, calendar.js, dashboard.js
- `migrations/` — Alembic/Flask-Migrate

## Wichtige Regeln
- **UI komplett auf Deutsch** (Labels, Buttons, Meldungen)
- **Keine Umlaute in Variablen/Funktionsnamen**, nur in Strings
- **Code-Kommentare auf Deutsch**
- **Multi-Tenancy:** JEDE DB-Query MUSS organization_id filtern (utils/auth.py nutzen)
- **CSRF:** Aktiv. Alle POST-Formulare brauchen csrf_token. JS nutzt fetchWithCSRF()
- **Passwort-Policy:** Staff min. 12 Zeichen, Portal min. 8 Zeichen
- **Audit-Logging:** services/audit_service.py für Patientenzugriff, Login, Rechnungen

## Deploy-Prozess
```bash
git push origin main
ssh -i ~/.ssh/OMNIA_Infomaniak ubuntu@83.228.241.233 "cd praxis-app && git pull && source venv/bin/activate && pip install -r requirements.txt && set -a && source .env && set +a && export FLASK_APP=app.py && flask db upgrade && sudo systemctl restart praxis-app"
```

## Referenz-Dokumente
- Rollout-Report: /Users/thomasbalke/Documents/OMNIA/Cenplex/OMNIA_Rollout_Readiness_Report.md
- Swiss MR Vergleich: /Users/thomasbalke/Documents/OMNIA/Cenplex/Swiss_MR_vs_OMNIA_Technischer_Vergleich.md
- Cenplex Produkthilfe: /Users/thomasbalke/Documents/OMNIA/Cenplex/Cenplex_Produkthilfe_Komplett (1).docx
