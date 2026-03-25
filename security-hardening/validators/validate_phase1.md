Du bist ein Security QA Engineer. Validiere die Phase-1 Aenderungen in /Users/thomasbalke/praxis-app.

Pruefe diese Dateien und berichte den Status:

1. /Users/thomasbalke/praxis-app/blueprints/auth/routes.py
   - Gibt es eine urlparse-Validierung fuer den 'next' Parameter?
   - Gibt es Account-Lockout Logik (failed_login_attempts, locked_until)?
   - Syntax korrekt? python3 -c "import ast; ast.parse(open('/Users/thomasbalke/praxis-app/blueprints/auth/routes.py').read())"

2. /Users/thomasbalke/praxis-app/blueprints/dashboard/routes.py
   - Haben JSON POST-Endpoints CSRF-Validierung?
   - Syntax korrekt?

3. /Users/thomasbalke/praxis-app/blueprints/portal/routes.py
   - Ist organization_id NICHT mehr hardcoded auf 1?
   - Ist die Passwort-Mindestlaenge >= 12?
   - Gibt es Datums-Validierung fuer Online-Booking?
   - Syntax korrekt?

4. /Users/thomasbalke/praxis-app/app.py
   - Gibt es Content-Security-Policy Header?
   - Gibt der Health-Endpoint keine internen Details preis?
   - Syntax korrekt?

5. /Users/thomasbalke/praxis-app/models.py
   - Hat das User Model failed_login_attempts und locked_until Felder?
   - Syntax korrekt?

6. /Users/thomasbalke/praxis-app/templates/base.html
   - Gibt es ein meta csrf-token Tag?

Fasse die Ergebnisse zusammen: Was ist OK, was fehlt noch.
