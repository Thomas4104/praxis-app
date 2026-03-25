from datetime import datetime, timedelta
from urllib.parse import urlparse
from flask import render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash
from blueprints.auth import auth_bp
from models import db, User
from app import limiter
from services.audit_service import log_action


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        user = User.query.filter_by(username=username).first()

        # Konto-Sperre pruefen
        if user and user.locked_until and user.locked_until > datetime.utcnow():
            remaining = (user.locked_until - datetime.utcnow()).seconds // 60
            flash(f'Konto gesperrt. Versuchen Sie es in {remaining + 1} Minuten erneut.', 'error')
            return render_template('auth/login.html')

        if user and user.check_password(password):
            if not user.is_active:
                flash('Dieses Konto ist deaktiviert.', 'error')
                return render_template('auth/login.html')

            # 2FA-Pruefung
            if user.totp_enabled:
                session['2fa_user_id'] = user.id
                db.session.commit()
                return redirect(url_for('auth.verify_2fa'))

            # Fehlgeschlagene Versuche zuruecksetzen
            user.failed_login_attempts = 0
            user.locked_until = None

            login_user(user, remember=True)
            user.last_login = datetime.utcnow()
            log_action('login', 'user', user.id)
            db.session.commit()

            next_page = request.args.get('next')
            if next_page:
                parsed = urlparse(next_page)
                # Nur relative URLs erlauben (kein Schema, kein Host)
                if parsed.scheme or parsed.netloc:
                    next_page = None
            return redirect(next_page or url_for('dashboard.index'))
        else:
            # Fehlgeschlagene Versuche zaehlen
            if user:
                user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
                if user.failed_login_attempts >= 5:
                    user.locked_until = datetime.utcnow() + timedelta(minutes=15)
                    user.failed_login_attempts = 0
            log_action('login_failed', 'user', 0)
            db.session.commit()
            flash('Ungültige Anmeldedaten.', 'error')

    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    log_action('logout', 'user', current_user.id)
    db.session.commit()
    logout_user()
    flash('Sie wurden erfolgreich abgemeldet.', 'success')
    return redirect(url_for('auth.login'))


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


@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not current_user.check_password(current_password):
            flash('Aktuelles Passwort ist falsch.', 'error')
        elif new_password != confirm_password:
            flash('Passwörter stimmen nicht überein.', 'error')
        else:
            pw_errors = validate_password_strength(new_password)
            if pw_errors:
                flash('Passwort-Anforderungen: ' + ', '.join(pw_errors), 'error')
            else:
                current_user.set_password(new_password)
                db.session.commit()
                flash('Passwort erfolgreich geändert.', 'success')
                return redirect(url_for('dashboard.index'))

    return render_template('auth/change_password.html')


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
            user.last_login = datetime.utcnow()
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
