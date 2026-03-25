Du bist ein Application Security Engineer. Dein Auftrag: Kritische Auth-Schwachstellen in /Users/thomasbalke/praxis-app fixen.

WICHTIG: Lies IMMER zuerst die betroffene Datei, bevor du sie aenderst. Aendere NUR das Minimum. Keine neuen Features, kein Refactoring.

## Aufgabe 1: Open Redirect fixen
Datei: /Users/thomasbalke/praxis-app/blueprints/auth/routes.py

Finde die Login-Route mit `next_page = request.args.get('next')` und sichere sie ab:
```python
from urllib.parse import urlparse

# In der login-Route nach next_page = request.args.get('next'):
if next_page:
    parsed = urlparse(next_page)
    # Nur relative URLs erlauben (kein Schema, kein Host)
    if parsed.scheme or parsed.netloc:
        next_page = None
```

## Aufgabe 2: CSRF auf JSON-Endpoints
Datei: /Users/thomasbalke/praxis-app/blueprints/dashboard/routes.py

Finde alle JSON POST-Endpoints (suche nach `request.get_json()` in POST-Routen) und fuege CSRF-Validierung hinzu:
```python
from flask_wtf.csrf import validate_csrf
from wtforms import ValidationError

# Am Anfang jeder JSON-POST-Route:
try:
    validate_csrf(request.headers.get('X-CSRFToken', ''))
except ValidationError:
    return jsonify({'error': 'CSRF-Token ungueltig'}), 403
```

Dann stelle sicher, dass das CSRF-Token im Frontend mitgesendet wird. Suche in /Users/thomasbalke/praxis-app/static/js/ nach fetch() oder XMLHttpRequest POST-Aufrufen und fuege den X-CSRFToken Header hinzu:
```javascript
headers: {
    'Content-Type': 'application/json',
    'X-CSRFToken': document.querySelector('meta[name="csrf-token"]')?.content ||
                   document.querySelector('[name="csrf_token"]')?.value || ''
}
```

Falls kein meta-Tag existiert, fuege in /Users/thomasbalke/praxis-app/templates/base.html im <head> hinzu:
```html
<meta name="csrf-token" content="{{ csrf_token() }}">
```

## Aufgabe 3: Account-Lockout implementieren
Datei: /Users/thomasbalke/praxis-app/models.py - User Model erweitern:
```python
# Im User Model diese Felder hinzufuegen:
failed_login_attempts = db.Column(db.Integer, default=0)
locked_until = db.Column(db.DateTime, nullable=True)
```

Datei: /Users/thomasbalke/praxis-app/blueprints/auth/routes.py - Login-Route:
```python
from datetime import datetime, timedelta

# Vor dem Passwort-Check:
if user and user.locked_until and user.locked_until > datetime.utcnow():
    remaining = (user.locked_until - datetime.utcnow()).seconds // 60
    flash(f'Konto gesperrt. Versuchen Sie es in {remaining + 1} Minuten erneut.', 'error')
    return render_template('auth/login.html')

# Bei fehlgeschlagenem Login:
if user:
    user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
    if user.failed_login_attempts >= 5:
        user.locked_until = datetime.utcnow() + timedelta(minutes=15)
        user.failed_login_attempts = 0
    db.session.commit()

# Bei erfolgreichem Login:
user.failed_login_attempts = 0
user.locked_until = None
```

## Aufgabe 4: Health-Endpoint absichern
Datei: /Users/thomasbalke/praxis-app/app.py - health_check Funktion:
Ersetze `return {'status': 'unhealthy', 'error': str(e)}` durch:
```python
current_app.logger.error(f'Health check failed: {e}')
return {'status': 'unhealthy', 'error': 'Datenbankverbindung fehlgeschlagen'}, 503
```

## Reihenfolge:
1. Lies JEDE Datei zuerst komplett
2. Fuehre Aufgabe 1-4 nacheinander aus
3. Pruefe am Ende, dass keine Syntax-Fehler entstanden sind (python -c "import py_compile; py_compile.compile('datei.py')")

Erstelle KEINE neuen Dateien ausser wenn explizit angegeben. Bearbeite NUR existierende Dateien.
