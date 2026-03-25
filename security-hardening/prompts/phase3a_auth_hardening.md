Du bist ein Identity & Access Management Experte. Dein Auftrag: Authentifizierung in /Users/thomasbalke/praxis-app haerten.

WICHTIG: Lies IMMER zuerst die betroffenen Dateien KOMPLETT.

## Aufgabe 1: TOTP-basierte Zwei-Faktor-Authentifizierung (2FA)

### 1a: Dependency hinzufuegen
Datei: /Users/thomasbalke/praxis-app/requirements.txt
```
pyotp>=2.9.0
```

### 1b: User Model erweitern
Datei: /Users/thomasbalke/praxis-app/models.py

Fuege im User Model folgende Felder hinzu:
```python
totp_secret = db.Column(db.String(32), nullable=True)  # Base32-encoded TOTP secret
totp_enabled = db.Column(db.Boolean, default=False)
totp_backup_codes = db.Column(db.Text, nullable=True)  # JSON-Array mit Backup-Codes
```

Fuege Methoden hinzu:
```python
def generate_totp_secret(self):
    import pyotp
    self.totp_secret = pyotp.random_base32()
    return self.totp_secret

def verify_totp(self, token):
    if not self.totp_secret:
        return False
    import pyotp
    totp = pyotp.TOTP(self.totp_secret)
    return totp.verify(token, valid_window=1)

def generate_backup_codes(self):
    import secrets, json
    codes = [secrets.token_hex(4) for _ in range(8)]
    self.totp_backup_codes = json.dumps(codes)
    return codes

def use_backup_code(self, code):
    import json
    if not self.totp_backup_codes:
        return False
    codes = json.loads(self.totp_backup_codes)
    if code in codes:
        codes.remove(code)
        self.totp_backup_codes = json.dumps(codes)
        return True
    return False
```

### 1c: 2FA-Setup Route
Datei: /Users/thomasbalke/praxis-app/blueprints/auth/routes.py

Fuege neue Routen hinzu fuer 2FA-Setup:
```python
@auth_bp.route('/2fa/setup', methods=['GET', 'POST'])
@login_required
def setup_2fa():
    if request.method == 'GET':
        secret = current_user.generate_totp_secret()
        db.session.commit()
        import pyotp
        totp = pyotp.TOTP(secret)
        provisioning_uri = totp.provisioning_uri(
            name=current_user.username,
            issuer_name='OMNIA Praxissoftware'
        )
        # QR-Code generieren
        import qrcode, io, base64
        qr = qrcode.make(provisioning_uri)
        buf = io.BytesIO()
        qr.save(buf, format='PNG')
        qr_b64 = base64.b64encode(buf.getvalue()).decode()
        return render_template('auth/setup_2fa.html',
                             secret=secret, qr_code=qr_b64)

    # POST: Token verifizieren
    token = request.form.get('token', '')
    if current_user.verify_totp(token):
        current_user.totp_enabled = True
        backup_codes = current_user.generate_backup_codes()
        db.session.commit()
        flash('Zwei-Faktor-Authentifizierung aktiviert.', 'success')
        return render_template('auth/backup_codes.html', codes=backup_codes)
    else:
        flash('Ungueltiger Code. Bitte erneut versuchen.', 'error')
        return redirect(url_for('auth.setup_2fa'))


@auth_bp.route('/2fa/verify', methods=['GET', 'POST'])
def verify_2fa():
    user_id = session.get('2fa_user_id')
    if not user_id:
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        token = request.form.get('token', '')
        user = User.query.get(user_id)
        if not user:
            return redirect(url_for('auth.login'))

        if user.verify_totp(token) or user.use_backup_code(token):
            session.pop('2fa_user_id', None)
            login_user(user)
            user.failed_login_attempts = 0
            user.locked_until = None
            db.session.commit()
            log_action('login', 'user', user.id)
            return redirect(url_for('dashboard.index'))
        else:
            flash('Ungueltiger 2FA-Code.', 'error')

    return render_template('auth/verify_2fa.html')


@auth_bp.route('/2fa/disable', methods=['POST'])
@login_required
def disable_2fa():
    token = request.form.get('token', '')
    if current_user.verify_totp(token):
        current_user.totp_enabled = False
        current_user.totp_secret = None
        current_user.totp_backup_codes = None
        db.session.commit()
        flash('Zwei-Faktor-Authentifizierung deaktiviert.', 'success')
    else:
        flash('Ungueltiger Code.', 'error')
    return redirect(url_for('settings.index'))
```

### 1d: Login-Route anpassen
In der bestehenden Login-Route, NACH dem erfolgreichen Passwort-Check:
```python
if user.totp_enabled:
    session['2fa_user_id'] = user.id
    return redirect(url_for('auth.verify_2fa'))
# Nur wenn kein 2FA: direkt einloggen
login_user(user)
```

### 1e: Templates erstellen
Erstelle minimale Templates:

/Users/thomasbalke/praxis-app/templates/auth/setup_2fa.html
/Users/thomasbalke/praxis-app/templates/auth/verify_2fa.html
/Users/thomasbalke/praxis-app/templates/auth/backup_codes.html

Diese muessen das base.html Template erweitern. Schaue dir zuerst ein bestehendes Auth-Template an (z.B. login.html) um den Stil zu uebernehmen. Halte die Templates einfach und funktional.

## Aufgabe 2: Session-Haertung
Datei: /Users/thomasbalke/praxis-app/config.py

Stelle sicher in ProductionConfig:
```python
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Strict'  # Von 'Lax' auf 'Strict' aendern
PERMANENT_SESSION_LIFETIME = timedelta(minutes=20)  # Von 30 auf 20 reduzieren
```

## Aufgabe 3: Passwort-Richtlinie verschaerfen
Datei: /Users/thomasbalke/praxis-app/blueprints/auth/routes.py

Finde die Passwortaenderungs-Route und fuege Validierung hinzu:
```python
def validate_password_strength(password):
    """Prueft Passwort-Staerke fuer medizinische Systeme."""
    errors = []
    if len(password) < 12:
        errors.append('Mindestens 12 Zeichen')
    if not any(c.isupper() for c in password):
        errors.append('Mindestens ein Grossbuchstabe')
    if not any(c.islower() for c in password):
        errors.append('Mindestens ein Kleinbuchstabe')
    if not any(c.isdigit() for c in password):
        errors.append('Mindestens eine Zahl')
    if not any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?' for c in password):
        errors.append('Mindestens ein Sonderzeichen')
    return errors
```

## Reihenfolge:
1. Lies auth/routes.py, models.py (User), config.py, ein bestehendes Auth-Template
2. Erweitere User Model
3. Aktualisiere requirements.txt
4. Implementiere Routen
5. Erstelle Templates
6. Aktualisiere Config
7. Syntax-Checks
