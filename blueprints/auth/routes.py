from datetime import datetime
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

        if user and user.check_password(password):
            if not user.is_active:
                flash('Dieses Konto ist deaktiviert.', 'error')
                return render_template('auth/login.html')

            login_user(user, remember=True)
            user.last_login = datetime.utcnow()
            log_action('login', 'user', user.id)
            db.session.commit()

            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard.index'))
        else:
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
