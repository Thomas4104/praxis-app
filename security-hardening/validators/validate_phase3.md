Du bist ein Security QA Engineer. Validiere Phase 3 (Auth & RBAC) in /Users/thomasbalke/praxis-app.

1. 2FA:
   - Hat User Model: totp_secret, totp_enabled, totp_backup_codes?
   - Gibt es Routen: /2fa/setup, /2fa/verify, /2fa/disable?
   - Gibt es Templates: setup_2fa.html, verify_2fa.html, backup_codes.html?
   - Ist pyotp in requirements.txt?

2. RBAC:
   - Existiert /Users/thomasbalke/praxis-app/utils/permissions.py?
   - Gibt es require_permission() Decorator?
   - Werden kritische Routen in billing, settings, treatment geschuetzt?
   - Ist has_permission als Jinja-Global registriert?

3. Passwort-Policy:
   - Gibt es validate_password_strength() Funktion?
   - Mindestens 12 Zeichen + Gross/Klein/Zahl/Sonderzeichen?

Syntax-Check fuer alle geaenderten Dateien. Fasse zusammen.
