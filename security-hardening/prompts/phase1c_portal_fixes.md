Du bist ein Web Application Security Specialist. Dein Auftrag: Kritische Portal-Schwachstellen in /Users/thomasbalke/praxis-app fixen.

WICHTIG: Lies IMMER zuerst die betroffene Datei komplett, bevor du sie aenderst.

## Aufgabe 1: Hardcoded Organization-ID im Portal fixen
Datei: /Users/thomasbalke/praxis-app/blueprints/portal/routes.py

Finde die Stelle wo `organization_id=1` hardcoded ist (vermutlich bei Patient-Erstellung fuer Portal-Registrierung).

Fix: Die Organization muss dynamisch bestimmt werden. Moegliche Ansaetze:
1. Organization aus einer SystemSetting lesen
2. Organization aus der URL/Subdomain ableiten
3. Default-Organization aus Config lesen

Implementiere den praktischsten Ansatz:
```python
# Aus SystemSetting oder Config lesen
from services.settings_service import get_setting
default_org_id = get_setting(None, 'portal_default_organization_id', None)
if not default_org_id:
    # Fallback: Erste aktive Organisation
    from models import Organization
    org = Organization.query.first()
    default_org_id = org.id if org else 1

patient = Patient(
    organization_id=int(default_org_id),
    ...
)
```

## Aufgabe 2: Portal-Passwort-Mindestlaenge erhoehen
Datei: /Users/thomasbalke/praxis-app/blueprints/portal/routes.py

Finde die Passwort-Validierung (vermutlich `len(password) < 8`) und aendere auf 12:
```python
if not password or len(password) < 12:
    flash('Passwort muss mindestens 12 Zeichen lang sein.', 'error')
```

## Aufgabe 3: Portal-Session Sicherheit
Datei: /Users/thomasbalke/praxis-app/blueprints/portal/routes.py

Finde alle Stellen wo `session['portal_account_id']` gesetzt wird und stelle sicher:
1. Session wird bei Login regeneriert (session.clear() vor dem Setzen)
2. Portal-Account-ID wird bei jedem Request validiert

Fuege eine `get_portal_user()` Hilfsfunktion hinzu (falls nicht vorhanden) die:
- account_id aus Session liest
- Account aus DB laedt
- Prueft ob account.is_active == True
- Prueft ob account.patient.organization_id korrekt ist
- Bei Fehler: Session cleared, redirect zu Portal-Login

## Aufgabe 4: Online-Booking Datums-Validierung
Datei: /Users/thomasbalke/praxis-app/blueprints/portal/routes.py

Finde die Online-Booking-Route und fuege Validierung hinzu:
```python
from datetime import date, datetime

# Datum muss in der Zukunft liegen
if requested_date <= date.today():
    flash('Bitte waehlen Sie ein Datum in der Zukunft.', 'error')
    return redirect(...)

# Datum darf nicht mehr als 3 Monate in der Zukunft liegen
max_date = date.today() + timedelta(days=90)
if requested_date > max_date:
    flash('Buchungen sind maximal 3 Monate im Voraus moeglich.', 'error')
    return redirect(...)
```

## Aufgabe 5: Invoice-Sichtbarkeit im Portal einschraenken
Datei: /Users/thomasbalke/praxis-app/blueprints/portal/routes.py

Finde die Stelle wo Invoices fuer den Portal-User geladen werden. Stelle sicher:
- Nur Invoices mit Status 'sent' oder 'overdue' sind sichtbar (nicht 'draft' oder 'cancelled')
- patient_id wird gegen den eingeloggten Portal-Account geprueft

## Reihenfolge:
1. Lies /Users/thomasbalke/praxis-app/blueprints/portal/routes.py KOMPLETT
2. Lies /Users/thomasbalke/praxis-app/models.py (relevante Models: PortalAccount, Patient, OnlineBookingRequest)
3. Fuehre Aufgaben 1-5 nacheinander aus
4. Syntax-Check am Ende
