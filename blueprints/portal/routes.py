"""
Portal-Routen: Patientenportal (separates Login-System)
"""
import functools
from datetime import datetime, date, time, timedelta
from flask import render_template, request, redirect, url_for, flash, session, jsonify, abort
from flask_login import login_required, current_user
from models import db, Patient, PatientDocument, Appointment, TreatmentSeries, \
    TreatmentSeriesTemplate, Employee, Location, Invoice, Task, \
    PortalAccount, PortalMessage, OnlineBookingRequest, WorkSchedule, Absence, Email
from blueprints.portal import portal_bp
from app import limiter
from utils.auth import check_org


# ============================================================
# Portal-Auth: Separates Session-Management
# ============================================================

def get_portal_user():
    """Gibt den aktuell eingeloggten Portal-Benutzer zurueck"""
    portal_account_id = session.get('portal_account_id')
    if portal_account_id:
        account = PortalAccount.query.get(portal_account_id)
        if account and account.is_active:
            return account
    return None


def portal_login_required(f):
    """Decorator: Stellt sicher, dass der Portal-Benutzer eingeloggt ist"""
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        portal_user = get_portal_user()
        if portal_user is None:
            return redirect(url_for('portal.login'))
        return f(*args, **kwargs)
    return decorated_function


# ============================================================
# Portal-Login / Registrierung
# ============================================================

@portal_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def login():
    """Portal-Login fuer Patienten"""
    # Falls bereits eingeloggt
    if get_portal_user():
        return redirect(url_for('portal.dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        account = PortalAccount.query.filter_by(email=email).first()

        if account and account.check_password(password):
            if not account.is_active:
                flash('Ihr Konto wurde noch nicht aktiviert. Bitte kontaktieren Sie Ihre Praxis.', 'warning')
                return render_template('portal/portal_login.html')

            # Login erfolgreich
            session['portal_account_id'] = account.id
            account.last_login = datetime.utcnow()
            db.session.commit()
            return redirect(url_for('portal.dashboard'))
        else:
            flash('E-Mail oder Passwort ungültig.', 'error')

    return render_template('portal/portal_login.html')


@portal_bp.route('/logout')
def logout():
    """Portal-Logout"""
    session.pop('portal_account_id', None)
    flash('Sie wurden erfolgreich abgemeldet.', 'success')
    return redirect(url_for('portal.login'))


@portal_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Portal-Registrierung fuer neue Patienten"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        password_confirm = request.form.get('password_confirm', '')
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        date_of_birth = request.form.get('date_of_birth', '')

        # Validierung
        errors = []
        if not email:
            errors.append('Bitte geben Sie Ihre E-Mail-Adresse ein.')
        if not password or len(password) < 8:
            errors.append('Das Passwort muss mindestens 8 Zeichen lang sein.')
        if password != password_confirm:
            errors.append('Die Passwörter stimmen nicht überein.')
        if not first_name or not last_name:
            errors.append('Bitte geben Sie Ihren Vor- und Nachnamen ein.')
        if not date_of_birth:
            errors.append('Bitte geben Sie Ihr Geburtsdatum ein.')

        # E-Mail bereits vorhanden?
        if PortalAccount.query.filter_by(email=email).first():
            errors.append('Diese E-Mail-Adresse ist bereits registriert.')

        if errors:
            for err in errors:
                flash(err, 'error')
            return render_template('portal/portal_register.html')

        # Patient suchen oder erstellen
        dob = datetime.strptime(date_of_birth, '%Y-%m-%d').date()
        patient = Patient.query.filter_by(
            first_name=first_name, last_name=last_name, date_of_birth=dob
        ).first()

        if not patient:
            # Neuen Patienten anlegen (wird von Praxis geprueft)
            patient = Patient(
                organization_id=1,  # Standard-Organisation
                first_name=first_name,
                last_name=last_name,
                date_of_birth=dob,
                email=email,
                is_active=True
            )
            db.session.add(patient)
            db.session.flush()

        # Portal-Account erstellen (inaktiv bis Praxis bestaetigt)
        account = PortalAccount(
            patient_id=patient.id,
            email=email,
            is_active=False,
            is_verified=False
        )
        account.set_password(password)
        db.session.add(account)

        # Aufgabe fuer die Praxis erstellen
        task = Task(
            organization_id=patient.organization_id,
            task_type='portal',
            category='portal',
            title=f'Neuer Portal-Patient: {first_name} {last_name} → Bestätigen/Ablehnen',
            description=f'Patient {first_name} {last_name} hat sich im Patientenportal registriert. '
                        f'E-Mail: {email}. Bitte Registrierung prüfen und bestätigen oder ablehnen.',
            related_patient_id=patient.id,
            priority='high',
            status='open',
            auto_generated=True
        )
        db.session.add(task)
        db.session.commit()

        flash('Ihre Registrierung wurde erfolgreich eingereicht. '
              'Sie erhalten eine Bestätigung, sobald Ihre Praxis den Zugang freigeschaltet hat.', 'success')
        return redirect(url_for('portal.login'))

    return render_template('portal/portal_register.html')


# ============================================================
# Portal-Dashboard
# ============================================================

@portal_bp.route('/')
@portal_login_required
def dashboard():
    """Portal-Uebersicht fuer Patienten"""
    account = get_portal_user()
    patient = account.patient

    # Naechster Termin
    next_appointment = Appointment.query.filter_by(patient_id=patient.id) \
        .filter(Appointment.start_time > datetime.now()) \
        .filter(Appointment.status.in_(['scheduled', 'confirmed'])) \
        .order_by(Appointment.start_time.asc()).first()

    # Aktive Behandlungsserie
    active_series = TreatmentSeries.query.filter_by(
        patient_id=patient.id, status='active').first()

    series_progress = None
    if active_series:
        total = active_series.template.num_appointments if active_series.template else 0
        done = Appointment.query.filter_by(
            series_id=active_series.id, status='completed').count()
        series_progress = {'total': total, 'done': done, 'series': active_series}

    # Offene Rechnungen
    open_invoices = Invoice.query.filter_by(patient_id=patient.id) \
        .filter(Invoice.status.in_(['sent', 'overdue'])) \
        .order_by(Invoice.created_at.desc()).all()

    # Ungelesene Nachrichten
    unread_messages = PortalMessage.query.filter_by(
        patient_id=patient.id, sender_type='practice'
    ).filter(PortalMessage.read_at.is_(None)).count()

    return render_template('portal/portal_dashboard.html',
                           account=account, patient=patient,
                           next_appointment=next_appointment,
                           series_progress=series_progress,
                           open_invoices=open_invoices,
                           unread_messages=unread_messages)


# ============================================================
# Termine
# ============================================================

@portal_bp.route('/appointments')
@portal_login_required
def appointments():
    """Termine anzeigen"""
    account = get_portal_user()
    patient = account.patient

    upcoming = Appointment.query.filter_by(patient_id=patient.id) \
        .filter(Appointment.start_time > datetime.now()) \
        .filter(Appointment.status.in_(['scheduled', 'confirmed'])) \
        .order_by(Appointment.start_time.asc()).all()

    past = Appointment.query.filter_by(patient_id=patient.id) \
        .filter(Appointment.start_time <= datetime.now()) \
        .order_by(Appointment.start_time.desc()).limit(20).all()

    # Buchungsanfragen
    booking_requests = OnlineBookingRequest.query.filter_by(
        patient_id=patient.id
    ).order_by(OnlineBookingRequest.created_at.desc()).limit(10).all()

    return render_template('portal/portal_appointments.html',
                           account=account, patient=patient,
                           upcoming=upcoming, past=past,
                           booking_requests=booking_requests)


@portal_bp.route('/appointments/<int:appointment_id>/cancel', methods=['POST'])
@portal_login_required
def cancel_appointment(appointment_id):
    """Termin absagen (mindestens 24h vorher)"""
    account = get_portal_user()
    appointment = Appointment.query.get_or_404(appointment_id)

    # Sicherheitscheck: Nur eigene Termine
    if appointment.patient_id != account.patient_id:
        abort(403)

    # Mindestens 24h vorher
    if appointment.start_time - datetime.now() < timedelta(hours=24):
        flash('Termine können nur mindestens 24 Stunden im Voraus abgesagt werden.', 'error')
        return redirect(url_for('portal.appointments'))

    appointment.status = 'cancelled'
    appointment.cancellation_reason = 'Vom Patienten über das Portal abgesagt'

    # Aufgabe fuer die Praxis
    task = Task(
        organization_id=account.patient.organization_id,
        task_type='portal',
        category='termin',
        title=f'Portal-Absage: {account.patient.first_name} {account.patient.last_name} '
              f'am {appointment.start_time.strftime("%d.%m.%Y %H:%M")}',
        description=f'Patient hat den Termin am {appointment.start_time.strftime("%d.%m.%Y um %H:%M")} '
                    f'über das Patientenportal abgesagt.',
        related_patient_id=account.patient_id,
        priority='high',
        status='open',
        auto_generated=True
    )
    db.session.add(task)
    db.session.commit()

    flash('Der Termin wurde erfolgreich abgesagt.', 'success')
    return redirect(url_for('portal.appointments'))


@portal_bp.route('/book', methods=['GET', 'POST'])
@portal_login_required
def book_appointment():
    """Online-Terminbuchung"""
    account = get_portal_user()
    patient = account.patient

    # Verfuegbare Vorlagen und Therapeuten laden
    templates = TreatmentSeriesTemplate.query.filter_by(
        organization_id=patient.organization_id, is_active=True
    ).all()
    employees = Employee.query.filter_by(
        organization_id=patient.organization_id, is_active=True
    ).all()

    if request.method == 'POST':
        template_id = request.form.get('template_id', type=int)
        employee_id = request.form.get('employee_id', type=int) or None
        requested_date = request.form.get('requested_date', '')
        requested_time = request.form.get('requested_time', '')
        notes = request.form.get('notes', '').strip()

        if not template_id or not requested_date or not requested_time:
            flash('Bitte füllen Sie alle Pflichtfelder aus.', 'error')
            return render_template('portal/portal_book.html',
                                   account=account, patient=patient,
                                   templates=templates, employees=employees)

        req_date = datetime.strptime(requested_date, '%Y-%m-%d').date()
        req_time = datetime.strptime(requested_time, '%H:%M').time()

        # Pruefen ob Datum in der Zukunft
        if req_date <= date.today():
            flash('Bitte wählen Sie ein Datum in der Zukunft.', 'error')
            return render_template('portal/portal_book.html',
                                   account=account, patient=patient,
                                   templates=templates, employees=employees)

        # Buchungsanfrage erstellen
        booking = OnlineBookingRequest(
            patient_id=patient.id,
            template_id=template_id,
            preferred_employee_id=employee_id,
            requested_date=req_date,
            requested_time=req_time,
            status='pending',
            notes=notes
        )
        db.session.add(booking)

        # Vorlage laden fuer Aufgabentitel
        template = TreatmentSeriesTemplate.query.get(template_id)
        emp = Employee.query.get(employee_id) if employee_id else None
        emp_name = f'{emp.user.first_name} {emp.user.last_name}' if emp and emp.user else 'Kein Wunsch'

        # Aufgabe fuer die Praxis
        task = Task(
            organization_id=patient.organization_id,
            task_type='portal',
            category='buchung',
            title=f'Online-Buchung: {patient.first_name} {patient.last_name} '
                  f'möchte Termin am {req_date.strftime("%d.%m.%Y")} → Bestätigen/Ablehnen',
            description=f'Patient: {patient.first_name} {patient.last_name}\n'
                        f'Behandlung: {template.name if template else "Unbekannt"}\n'
                        f'Wunschtermin: {req_date.strftime("%d.%m.%Y")} um {req_time.strftime("%H:%M")}\n'
                        f'Therapeut: {emp_name}\n'
                        f'Anmerkungen: {notes or "-"}',
            related_patient_id=patient.id,
            priority='high',
            status='open',
            auto_generated=True
        )
        db.session.add(task)
        db.session.commit()

        flash('Ihre Terminanfrage wurde erfolgreich gesendet. '
              'Sie erhalten eine Bestätigung von Ihrer Praxis.', 'success')
        return redirect(url_for('portal.appointments'))

    return render_template('portal/portal_book.html',
                           account=account, patient=patient,
                           templates=templates, employees=employees)


@portal_bp.route('/api/available-slots')
@portal_login_required
def available_slots():
    """API: Verfuegbare Zeitslots fuer Online-Buchung (Constraint-Solver)"""
    account = get_portal_user()
    patient = account.patient

    date_str = request.args.get('date', '')
    employee_id = request.args.get('employee_id', type=int)
    template_id = request.args.get('template_id', type=int)

    if not date_str or not template_id:
        return jsonify({'slots': []})

    try:
        req_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'slots': []})

    template = TreatmentSeriesTemplate.query.get(template_id)
    if not template:
        return jsonify({'slots': []})

    duration = template.duration_minutes or 30
    day_of_week = req_date.weekday()  # 0=Montag

    # Therapeuten ermitteln
    if employee_id:
        employees = Employee.query.filter_by(
            id=employee_id, organization_id=patient.organization_id, is_active=True
        ).all()
    else:
        employees = Employee.query.filter_by(
            organization_id=patient.organization_id, is_active=True
        ).all()

    slots = []
    for emp in employees:
        # Arbeitszeiten fuer diesen Tag pruefen
        schedules = WorkSchedule.query.filter_by(
            employee_id=emp.id, day_of_week=day_of_week
        ).all()

        # Abwesenheiten pruefen
        absent = Absence.query.filter(
            Absence.employee_id == emp.id,
            Absence.start_date <= req_date,
            Absence.end_date >= req_date,
            Absence.status.in_(['approved', 'pending'])
        ).first()
        if absent:
            continue

        for schedule in schedules:
            # Bestehende Termine an diesem Tag laden
            day_start = datetime.combine(req_date, schedule.start_time)
            day_end = datetime.combine(req_date, schedule.end_time)

            existing = Appointment.query.filter(
                Appointment.employee_id == emp.id,
                Appointment.start_time >= day_start,
                Appointment.end_time <= day_end,
                Appointment.status.in_(['scheduled', 'confirmed'])
            ).all()

            # Belegte Zeiten
            busy = [(a.start_time, a.end_time) for a in existing]

            # Slots in 30-Minuten-Schritten generieren
            current = day_start
            while current + timedelta(minutes=duration) <= day_end:
                slot_end = current + timedelta(minutes=duration)
                is_free = True
                for b_start, b_end in busy:
                    if current < b_end and slot_end > b_start:
                        is_free = False
                        break
                if is_free:
                    emp_name = f'{emp.user.first_name} {emp.user.last_name}' if emp.user else f'Therapeut {emp.id}'
                    slots.append({
                        'time': current.strftime('%H:%M'),
                        'employee_id': emp.id,
                        'employee_name': emp_name
                    })
                current += timedelta(minutes=30)

    # Sortieren nach Uhrzeit
    slots.sort(key=lambda s: s['time'])
    return jsonify({'slots': slots})


# ============================================================
# Dokumente
# ============================================================

@portal_bp.route('/documents')
@portal_login_required
def documents():
    """Freigegebene Dokumente anzeigen"""
    account = get_portal_user()
    patient = account.patient

    docs = PatientDocument.query.filter_by(
        patient_id=patient.id, portal_visible=True
    ).order_by(PatientDocument.created_at.desc()).all()

    # Rechnungen mit PDF
    invoices = Invoice.query.filter_by(patient_id=patient.id) \
        .filter(Invoice.pdf_path.isnot(None)) \
        .order_by(Invoice.created_at.desc()).all()

    return render_template('portal/portal_documents.html',
                           account=account, patient=patient,
                           docs=docs, invoices=invoices)


# ============================================================
# Nachrichten
# ============================================================

@portal_bp.route('/messages')
@portal_login_required
def messages():
    """Nachrichten-Uebersicht"""
    account = get_portal_user()
    patient = account.patient

    all_messages = PortalMessage.query.filter_by(patient_id=patient.id) \
        .order_by(PortalMessage.created_at.desc()).all()

    # Ungelesene Praxis-Nachrichten als gelesen markieren
    unread = PortalMessage.query.filter_by(
        patient_id=patient.id, sender_type='practice'
    ).filter(PortalMessage.read_at.is_(None)).all()
    for msg in unread:
        msg.read_at = datetime.utcnow()
    if unread:
        db.session.commit()

    return render_template('portal/portal_messages.html',
                           account=account, patient=patient,
                           messages=all_messages)


@portal_bp.route('/messages/new', methods=['GET', 'POST'])
@portal_login_required
def new_message():
    """Neue Nachricht an die Praxis senden"""
    account = get_portal_user()
    patient = account.patient

    if request.method == 'POST':
        subject = request.form.get('subject', '').strip()
        body = request.form.get('body', '').strip()

        if not subject or not body:
            flash('Bitte füllen Sie Betreff und Nachricht aus.', 'error')
            return render_template('portal/portal_message_new.html',
                                   account=account, patient=patient)

        msg = PortalMessage(
            patient_id=patient.id,
            sender_type='patient',
            sender_name=f'{patient.first_name} {patient.last_name}',
            subject=subject,
            body=body
        )
        db.session.add(msg)
        # Portal-Nachricht auch im Mailing als Eingang anzeigen
        try:
            email = Email(
                subject=f'[Portal] {subject}',
                body=body,
                sender=f'{patient.first_name} {patient.last_name} (Portal)',
                sender_email=f'portal-{patient.id}@intern',
                recipient='praxis@intern',
                folder='inbox',
                is_read=False,
                organization_id=patient.organization_id
            )
            db.session.add(email)
        except Exception:
            pass
        db.session.commit()

        flash('Ihre Nachricht wurde erfolgreich gesendet.', 'success')
        return redirect(url_for('portal.messages'))

    return render_template('portal/portal_message_new.html',
                           account=account, patient=patient)


# ============================================================
# Profil
# ============================================================

@portal_bp.route('/profile', methods=['GET', 'POST'])
@portal_login_required
def profile():
    """Profil anzeigen und bearbeiten"""
    account = get_portal_user()
    patient = account.patient

    if request.method == 'POST':
        action = request.form.get('action', '')

        if action == 'update_profile':
            patient.phone = request.form.get('phone', '').strip()
            patient.mobile = request.form.get('mobile', '').strip()
            patient.email = request.form.get('email', '').strip()
            patient.address = request.form.get('address', '').strip()
            patient.city = request.form.get('city', '').strip()
            patient.zip_code = request.form.get('zip_code', '').strip()
            patient.preferred_contact_method = request.form.get('preferred_contact_method', 'phone')
            db.session.commit()
            flash('Ihre Daten wurden erfolgreich aktualisiert.', 'success')

        elif action == 'change_password':
            current_pw = request.form.get('current_password', '')
            new_pw = request.form.get('new_password', '')
            confirm_pw = request.form.get('confirm_password', '')

            if not account.check_password(current_pw):
                flash('Das aktuelle Passwort ist ungültig.', 'error')
            elif len(new_pw) < 8:
                flash('Das neue Passwort muss mindestens 8 Zeichen lang sein.', 'error')
            elif new_pw != confirm_pw:
                flash('Die neuen Passwörter stimmen nicht überein.', 'error')
            else:
                account.set_password(new_pw)
                db.session.commit()
                flash('Ihr Passwort wurde erfolgreich geändert.', 'success')

        return redirect(url_for('portal.profile'))

    return render_template('portal/portal_profile.html',
                           account=account, patient=patient)


# ============================================================
# Praxis-Verwaltungsseite: Portal-Info und Statistiken
# ============================================================

@portal_bp.route('/admin')
@login_required
def admin():
    """Portal-Verwaltung (fuer Praxis-Mitarbeiter)"""
    # Statistiken
    org_id = current_user.organization_id
    total_accounts = PortalAccount.query.join(Patient).filter(Patient.organization_id == org_id).count()
    active_accounts = PortalAccount.query.join(Patient).filter(Patient.organization_id == org_id, PortalAccount.is_active == True).count()
    pending_accounts = PortalAccount.query.join(Patient).filter(Patient.organization_id == org_id, PortalAccount.is_active == False).count()
    pending_bookings = OnlineBookingRequest.query.join(Patient).filter(Patient.organization_id == org_id, OnlineBookingRequest.status == 'pending').count()
    total_messages = PortalMessage.query.join(Patient).filter(Patient.organization_id == org_id).count()
    unread_messages = PortalMessage.query.join(Patient).filter(
        Patient.organization_id == org_id,
        PortalMessage.sender_type == 'patient'
    ).filter(PortalMessage.read_at.is_(None)).count()

    # Letzte Buchungsanfragen
    recent_bookings = OnlineBookingRequest.query.join(Patient).filter(
        Patient.organization_id == org_id
    ).order_by(OnlineBookingRequest.created_at.desc()).limit(10).all()

    # Letzte Portal-Nachrichten
    recent_messages = PortalMessage.query.join(Patient).filter(
        Patient.organization_id == org_id,
        PortalMessage.sender_type == 'patient'
    ).order_by(PortalMessage.created_at.desc()).limit(10).all()

    return render_template('portal/portal_admin.html',
                           total_accounts=total_accounts,
                           active_accounts=active_accounts,
                           pending_accounts=pending_accounts,
                           pending_bookings=pending_bookings,
                           total_messages=total_messages,
                           unread_messages=unread_messages,
                           recent_bookings=recent_bookings,
                           recent_messages=recent_messages)


@portal_bp.route('/admin/account/<int:account_id>/toggle', methods=['POST'])
@login_required
def toggle_account(account_id):
    """Portal-Account aktivieren/deaktivieren"""
    account = PortalAccount.query.get_or_404(account_id)
    check_org(account.patient)
    account.is_active = not account.is_active
    account.is_verified = account.is_active
    db.session.commit()

    status = 'aktiviert' if account.is_active else 'deaktiviert'
    flash(f'Portal-Zugang wurde {status}.', 'success')

    # Zurueck zur Quelle
    referer = request.form.get('referer', '')
    if referer:
        return redirect(referer)
    return redirect(url_for('portal.admin'))


@portal_bp.route('/admin/booking/<int:booking_id>/confirm', methods=['POST'])
@login_required
def confirm_booking(booking_id):
    """Online-Buchung bestaetigen"""
    booking = OnlineBookingRequest.query.get_or_404(booking_id)
    check_org(Patient.query.get(booking.patient_id))
    booking.status = 'confirmed'
    db.session.commit()
    flash('Buchungsanfrage wurde bestätigt.', 'success')
    return redirect(url_for('portal.admin'))


@portal_bp.route('/admin/booking/<int:booking_id>/reject', methods=['POST'])
@login_required
def reject_booking(booking_id):
    """Online-Buchung ablehnen"""
    booking = OnlineBookingRequest.query.get_or_404(booking_id)
    check_org(Patient.query.get(booking.patient_id))
    booking.status = 'rejected'
    db.session.commit()
    flash('Buchungsanfrage wurde abgelehnt.', 'success')
    return redirect(url_for('portal.admin'))


@portal_bp.route('/admin/message/<int:patient_id>', methods=['POST'])
@login_required
def send_practice_message(patient_id):
    """Nachricht von Praxis an Patient senden"""
    patient = Patient.query.get_or_404(patient_id)
    check_org(patient)
    subject = request.form.get('subject', '').strip()
    body = request.form.get('body', '').strip()

    if not subject or not body:
        flash('Bitte füllen Sie Betreff und Nachricht aus.', 'error')
        return redirect(url_for('portal.admin'))

    msg = PortalMessage(
        patient_id=patient.id,
        sender_type='practice',
        sender_name='OMNIA Praxisteam',
        subject=subject,
        body=body
    )
    db.session.add(msg)
    db.session.commit()

    flash(f'Nachricht an {patient.first_name} {patient.last_name} gesendet.', 'success')
    return redirect(url_for('portal.admin'))
