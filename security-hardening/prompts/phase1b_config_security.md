Du bist ein Infrastructure Security Engineer. Dein Auftrag: Kritische Konfigurationsschwachstellen in /Users/thomasbalke/praxis-app fixen.

WICHTIG: Lies IMMER zuerst die betroffene Datei, bevor du sie aenderst.

## Aufgabe 1: Security Headers vervollstaendigen
Datei: /Users/thomasbalke/praxis-app/app.py

Finde die `set_security_headers` Funktion (nach @app.after_request) und erweitere sie um fehlende Headers:
```python
response.headers['Content-Security-Policy'] = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: https:; "
    "font-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)
response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
response.headers['X-Permitted-Cross-Domain-Policies'] = 'none'
```

## Aufgabe 2: Docker-Compose absichern
Datei: /Users/thomasbalke/praxis-app/docker-compose.yml

1. Entferne die exponierten Ports fuer DB und Redis (oder binde an 127.0.0.1):
   - Aendere `"5432:5432"` zu `"127.0.0.1:5432:5432"` oder entferne ports komplett
   - Aendere `"6379:6379"` zu `"127.0.0.1:6379:6379"` oder entferne ports komplett

2. Ersetze hardcoded Credentials durch Environment-Referenzen:
   - Aendere `POSTGRES_PASSWORD=omnia_secret` zu `POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-changeme}`
   - Aendere die DATABASE_URI analog

3. Fuege Netzwerk-Segmentierung hinzu:
```yaml
networks:
  frontend:
    driver: bridge
  backend:
    driver: bridge
    internal: true
```
Web-Service bekommt beide Netzwerke, DB und Redis nur `backend`.

4. Fuege Health-Checks hinzu fuer den Web-Service.

5. Fuege Resource-Limits hinzu:
```yaml
deploy:
  resources:
    limits:
      cpus: '2'
      memory: 2G
```

## Aufgabe 3: Nginx TLS/HTTPS konfigurieren
Datei: /Users/thomasbalke/praxis-app/nginx.conf

Erweitere die Konfiguration um:
1. HTTP zu HTTPS Redirect (Port 80 -> 443)
2. SSL-Konfiguration mit Let's Encrypt Pfaden
3. Moderne TLS-Einstellungen (TLSv1.2 + TLSv1.3)
4. `server_tokens off;`
5. Rate-Limiting Zone fuer Login

Behalte die bestehende proxy_pass und gzip Konfiguration bei. Stelle sicher, dass die Datei als Kommentar markiert, dass die SSL-Zertifikate vorhanden sein muessen.

## Aufgabe 4: Dockerfile absichern
Datei: /Users/thomasbalke/praxis-app/Dockerfile

1. Fuege einen non-root User hinzu:
```dockerfile
RUN groupadd -r appuser && useradd -r -g appuser -d /app appuser
# ... nach COPY und pip install ...
USER appuser
```

2. Pinne das Base-Image genauer (z.B. python:3.12-slim-bookworm)

## Aufgabe 5: .env.example aktualisieren
Datei: /Users/thomasbalke/praxis-app/.env.example (erstelle falls nicht vorhanden)

Stelle sicher, dass alle Secrets dokumentiert sind:
```
# WICHTIG: Alle Werte muessen vor Produktivbetrieb gesetzt werden!
FLASK_ENV=production
SECRET_KEY=          # MUSS gesetzt werden! Generieren: python -c "import secrets; print(secrets.token_hex(32))"
DATABASE_URI=        # z.B. postgresql://user:pass@db:5432/omnia
POSTGRES_PASSWORD=   # Starkes Passwort generieren
ANTHROPIC_API_KEY=   # Von console.anthropic.com
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0
```

## Reihenfolge:
1. Lies JEDE Datei zuerst
2. Fuehre Aufgaben 1-5 nacheinander aus
3. Validiere die YAML-Syntax: python3 -c "import yaml; yaml.safe_load(open('docker-compose.yml'))"
4. Validiere die Nginx-Config Syntax wenn moeglich
