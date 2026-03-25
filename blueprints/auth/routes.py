from datetime import datetime, timedelta
from urllib.parse import urlparse
from flask import render_template, redirect, url_for, flash, request
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


@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not current_user.check_password(current_password):
            flash('Aktuelles Passwort ist falsch.', 'error')
        elif len(new_password) < 12:
            flash('Neues Passwort muss mindestens 12 Zeichen haben.', 'error')
        elif new_password != confirm_password:
            flash('Passwörter stimmen nicht überein.', 'error')
        else:
            current_user.set_password(new_password)
            db.session.commit()
            flash('Passwort erfolgreich geändert.', 'success')
            return redirect(url_for('dashboard.index'))

    return render_template('auth/change_password.html')
