"""Routen fuer Fitness: Abonnemente, Vorlagen, Besuche, Check-in, Pausen, Einstellungen, Automatisierungen, Gantner"""
import json
from datetime import datetime, date, timedelta
from flask import render_template, request, jsonify, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from blueprints.fitness import fitness_bp
from models import (db, SubscriptionTemplate, Subscription, FitnessVisit, Patient, Location,
                    Invoice, InvoiceItem, SubscriptionBreak, FitnessConfig, FitnessAutomation,
                    GantnerTrace, AboAction, AboPosition, Employee)
from sqlalchemy import func, or_, and_


def _add_months(source_date, months):
    """Addiert Monate zu einem Datum"""
    month = source_date.month - 1 + months
    year = source_date.year + month // 12
    month = month % 12 + 1
    import calendar
    day = min(source_date.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _log_abo_action(subscription_id, action_type, content=''):
    """Protokolliert eine Abo-Aktion"""
    # Employee per User suchen
    employee = Employee.query.filter_by(user_id=current_user.id).first()
    employee_id = employee.id if employee else current_user.id

    action = AboAction(
        subscription_id=subscription_id,
        employee_id=employee_id,
        action_date=datetime.now(),
        action_type=action_type,
        action_content=content
    )
    db.session.add(action)


# ============================================================
# Fitness-Uebersicht (Dashboard)
# ============================================================

@fitness_bp.route('/')
@login_required
def index():
    """Fitness-Dashboard mit Kennzahlen"""
    org_id = current_user.organization_id
    today = date.today()
    month_start = today.replace(day=1)
    month_end = _add_months(month_start, 1) - timedelta(days=1)

    # Kennzahlen
    aktive_abos = Subscription.query.filter_by(
        organization_id=org_id, status='active'
    ).count()

    pausierte_abos = Subscription.query.filter_by(
        organization_id=org_id, status='paused'
    ).count()

    ablaufende_abos = Subscription.query.filter(
        Subscription.organization_id == org_id,
        Subscription.status == 'active',
        Subscription.end_date != None,
        Subscription.end_date >= today,
        Subscription.end_date <= today + timedelta(days=30)
    ).count()

    besuche_heute = FitnessVisit.query.join(Subscription).filter(
        Subscription.organization_id == org_id,
        func.date(FitnessVisit.check_in) == today
    ).count()

    # Umsatz Fitness aktueller Monat
    umsatz_monat = db.session.query(func.sum(Invoice.amount_total)).filter(
        Invoice.organization_id == org_id,
        Invoice.category == 'fitness',
        Invoice.created_at >= datetime.combine(month_start, datetime.min.time()),
        Invoice.created_at <= datetime.combine(month_end, datetime.max.time())
    ).scalar() or 0

    # Neue Abos diesen Monat
    neue_abos_monat = Subscription.query.filter(
        Subscription.organization_id == org_id,
        Subscription.created_at >= datetime.combine(month_start, datetime.min.time()),
        Subscription.created_at <= datetime.combine(month_end, datetime.max.time())
    ).count()

    # Letzte Besuche
    letzte_besuche = FitnessVisit.query.join(Subscription).filter(
        Subscription.organization_id == org_id
    ).order_by(FitnessVisit.check_in.desc()).limit(10).all()

    return render_template('fitness/index.html',
                           aktive_abos=aktive_abos,
                           pausierte_abos=pausierte_abos,
                           ablaufende_abos=ablaufende_abos,
                           besuche_heute=besuche_heute,
                           umsatz_monat=umsatz_monat,
                           neue_abos_monat=neue_abos_monat,
                           letzte_besuche=letzte_besuche)


# ============================================================
# Abo-Vorlagen
# ============================================================

@fitness_bp.route('/templates')
@login_required
def templates():
    """Liste aller Abo-Vorlagen"""
    org_id = current_user.organization_id
    vorlagen = SubscriptionTemplate.query.filter_by(
        organization_id=org_id, is_deleted=False
    ).order_by(SubscriptionTemplate.sub_position, SubscriptionTemplate.name).all()
    return render_template('fitness/templates.html', vorlagen=vorlagen)


@fitness_bp.route('/templates/new', methods=['GET', 'POST'])
@login_required
def template_new():
    """Neue Abo-Vorlage erstellen"""
    org_id = current_user.organization_id
    locations = Location.query.filter_by(organization_id=org_id).all()
    automations = FitnessAutomation.query.filter_by(organization_id=org_id, is_deleted=False).all()

    if request.method == 'POST':
        vorlage = _save_template(None, org_id)
        db.session.add(vorlage)
        db.session.commit()
        flash('Abo-Vorlage erstellt.', 'success')
        return redirect(url_for('fitness.templates'))

    return render_template('fitness/template_form.html', vorlage=None,
                           locations=locations, automations=automations)


@fitness_bp.route('/templates/<int:template_id>/edit', methods=['GET', 'POST'])
@login_required
def template_edit(template_id):
    """Abo-Vorlage bearbeiten"""
    org_id = current_user.organization_id
    vorlage = SubscriptionTemplate.query.get_or_404(template_id)
    if vorlage.organization_id != org_id:
        abort(403)
    locations = Location.query.filter_by(organization_id=org_id).all()
    automations = FitnessAutomation.query.filter_by(organization_id=org_id, is_deleted=False).all()

    if request.method == 'POST':
        _save_template(vorlage, org_id)
        db.session.commit()
        flash('Abo-Vorlage aktualisiert.', 'success')
        return redirect(url_for('fitness.templates'))

    return render_template('fitness/template_form.html', vorlage=vorlage,
                           locations=locations, automations=automations)


def _save_template(vorlage, org_id):
    """Speichert/aktualisiert eine Abo-Vorlage mit allen Cenplex-Feldern"""
    if vorlage is None:
        vorlage = SubscriptionTemplate(organization_id=org_id, is_active=True)

    # Grunddaten
    vorlage.name = request.form.get('name', vorlage.name if vorlage.id else '')
    vorlage.category = request.form.get('category', 'fitness')
    vorlage.duration_months = int(request.form.get('duration_months', 12))
    vorlage.sub_duration_type = int(request.form.get('sub_duration_type', 0))
    vorlage.price = float(request.form.get('price', 0))
    vorlage.payment_interval = request.form.get('payment_interval', 'monthly')
    vorlage.cancellation_months = int(request.form.get('cancellation_months', 1))
    vorlage.auto_renew = request.form.get('auto_renew') == 'on'
    vorlage.max_visits = int(request.form.get('max_visits', 0))
    vorlage.access_hours_json = request.form.get('access_hours_json', '')
    vorlage.location_id = int(request.form['location_id']) if request.form.get('location_id') else None
    vorlage.sub_position = int(request.form.get('sub_position', 0))
    vorlage.sub_tags = request.form.get('sub_tags', '')

    # Erweiterte Preise (Cenplex)
    vorlage.price_once = float(request.form.get('price_once', 0)) if request.form.get('price_once') else None
    vorlage.price_month = float(request.form.get('price_month', 0)) if request.form.get('price_month') else None
    vorlage.price_rate = float(request.form.get('price_rate', 0)) if request.form.get('price_rate') else None
    vorlage.price_batch_depot = float(request.form.get('price_batch_depot', 0)) if request.form.get('price_batch_depot') else None
    vorlage.price_break_penalty = float(request.form.get('price_break_penalty', 0)) if request.form.get('price_break_penalty') else None
    vorlage.payment_type = int(request.form.get('payment_type', 0))
    vorlage.sub_payment_rates = int(request.form.get('sub_payment_rates', 1))
    vorlage.sub_credit_amount = float(request.form.get('sub_credit_amount', 0)) if request.form.get('sub_credit_amount') else None

    # Training und Besuche
    vorlage.sub_training_controls = int(request.form.get('sub_training_controls', 0))
    vorlage.sub_visits = int(request.form.get('sub_visits', 0)) if request.form.get('sub_visits') else None
    vorlage.one_appointment_per_day = request.form.get('one_appointment_per_day') == 'on'
    vorlage.book_appointment_for_visit = request.form.get('book_appointment_for_visit') == 'on'
    vorlage.use_visits_and_duration = request.form.get('use_visits_and_duration') == 'on'

    # Geraete-Sync
    vorlage.no_sync_egym = request.form.get('no_sync_egym') == 'on'
    vorlage.no_sync_milon = request.form.get('no_sync_milon') == 'on'
    vorlage.no_sync_mywellness = request.form.get('no_sync_mywellness') == 'on'
    vorlage.no_sync_dividat = request.form.get('no_sync_dividat') == 'on'

    # Gantner
    vorlage.gantner_devices = request.form.get('gantner_devices', '')
    vorlage.gantner_locations = request.form.get('gantner_locations', '')
    vorlage.gantner_only_valid_abos = request.form.get('gantner_only_valid_abos') == 'on'

    # Gueltige Zeiten
    vorlage.valid_times = request.form.get('valid_times', '')

    # Aktiv-Status (nur beim Bearbeiten)
    if vorlage.id:
        vorlage.is_active = request.form.get('is_active') != 'off'

    return vorlage


@fitness_bp.route('/templates/<int:template_id>/delete', methods=['POST'])
@login_required
def template_delete(template_id):
    """Abo-Vorlage loeschen (soft delete)"""
    org_id = current_user.organization_id
    vorlage = SubscriptionTemplate.query.get_or_404(template_id)
    if vorlage.organization_id != org_id:
        abort(403)
    vorlage.is_deleted = True
    db.session.commit()
    flash('Abo-Vorlage gelöscht.', 'success')
    return redirect(url_for('fitness.templates'))


# ============================================================
# Abonnemente
# ============================================================

@fitness_bp.route('/subscriptions')
@login_required
def subscriptions():
    """Liste aller Abonnemente"""
    org_id = current_user.organization_id
    search = request.args.get('search', '').strip()
    status_filter = request.args.get('status', '')
    template_filter = request.args.get('template', '', type=str)
    page = request.args.get('page', 1, type=int)
    per_page = 25

    query = Subscription.query.filter(
        Subscription.organization_id == org_id,
        Subscription.is_deleted == False
    )

    if status_filter:
        query = query.filter(Subscription.status == status_filter)

    if template_filter:
        query = query.filter(Subscription.template_id == int(template_filter))

    if search:
        query = query.join(Patient).filter(
            or_(
                Patient.first_name.ilike(f'%{search}%'),
                Patient.last_name.ilike(f'%{search}%'),
                Subscription.subscription_number.ilike(f'%{search}%'),
                Subscription.badge_number.ilike(f'%{search}%')
            )
        )

    query = query.order_by(Subscription.created_at.desc())
    total = query.count()
    abos = query.offset((page - 1) * per_page).limit(per_page).all()
    total_pages = (total + per_page - 1) // per_page

    vorlagen = SubscriptionTemplate.query.filter_by(
        organization_id=org_id, is_deleted=False
    ).order_by(SubscriptionTemplate.name).all()

    return render_template('fitness/subscriptions.html',
                           abos=abos, search=search, status_filter=status_filter,
                           template_filter=template_filter, vorlagen=vorlagen,
                           page=page, total=total, total_pages=total_pages)


@fitness_bp.route('/subscriptions/new', methods=['GET', 'POST'])
@login_required
def subscription_new():
    """Neues Abo erstellen"""
    org_id = current_user.organization_id
    vorlagen = SubscriptionTemplate.query.filter_by(organization_id=org_id, is_active=True, is_deleted=False).all()
    employees = Employee.query.filter_by(organization_id=org_id).all()

    if request.method == 'POST':
        template_id = int(request.form.get('template_id', 0))
        patient_id = int(request.form.get('patient_id', 0))
        start_date_str = request.form.get('start_date', '')
        badge_number = request.form.get('badge_number', '').strip()
        notes = request.form.get('notes', '').strip()
        discount = float(request.form.get('discount', 0))
        supervisor_id = int(request.form.get('supervisor_id', 0)) if request.form.get('supervisor_id') else None

        vorlage = SubscriptionTemplate.query.filter_by(id=template_id, organization_id=org_id).first()
        patient = Patient.query.filter_by(id=patient_id, organization_id=org_id).first()
        if not vorlage or not patient:
            flash('Bitte Vorlage und Patient auswählen.', 'error')
            return redirect(url_for('fitness.subscription_new'))

        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else date.today()

        # Enddatum berechnen
        end_date = None
        if vorlage.duration_months > 0:
            end_date = _add_months(start_date, vorlage.duration_months)

        # Abo-Nummer generieren
        count = Subscription.query.filter_by(organization_id=org_id).count()
        abo_nummer = f'ABO-{count + 1:05d}'

        abo = Subscription(
            organization_id=org_id,
            patient_id=patient_id,
            template_id=template_id,
            subscription_number=abo_nummer,
            badge_number=badge_number if badge_number else None,
            start_date=start_date,
            end_date=end_date,
            status='active',
            visits_used=0,
            notes=notes,
            discount=discount,
            supervisor_id=supervisor_id,
            created_by_id=current_user.id,
            price=vorlage.price,
            apply_vat=False,
            include_vat=False,
        )
        db.session.add(abo)
        db.session.flush()

        # Erste Rechnung automatisch erstellen
        _create_subscription_invoice(abo, vorlage, org_id)

        # Aktion protokollieren
        _log_abo_action(abo.id, 0, f'Abo erstellt: {vorlage.name}')

        db.session.commit()
        flash(f'Abo {abo_nummer} für {patient.first_name} {patient.last_name} erstellt.', 'success')
        return redirect(url_for('fitness.subscription_detail', sub_id=abo.id))

    return render_template('fitness/subscription_form.html', vorlagen=vorlagen, employees=employees)


@fitness_bp.route('/subscriptions/<int:sub_id>')
@login_required
def subscription_detail(sub_id):
    """Abo-Detail-Ansicht"""
    org_id = current_user.organization_id
    abo = Subscription.query.get_or_404(sub_id)
    if abo.organization_id != org_id:
        abort(403)

    vorlage = abo.template
    patient = abo.patient

    # Besuchshistorie (letzte 20)
    besuche = FitnessVisit.query.filter_by(subscription_id=abo.id).order_by(
        FitnessVisit.check_in.desc()
    ).limit(20).all()

    # Restliche Besuche bei Mehrfachkarte
    rest_besuche = None
    if vorlage and vorlage.max_visits > 0:
        rest_besuche = vorlage.max_visits - (abo.visits_used or 0)

    # Rechnungen zu diesem Abo
    rechnungen = Invoice.query.filter_by(
        organization_id=org_id,
        patient_id=abo.patient_id,
        category='fitness'
    ).order_by(Invoice.created_at.desc()).limit(10).all()

    # Pausen (Breaks)
    pausen = SubscriptionBreak.query.filter_by(
        subscription_id=abo.id
    ).order_by(SubscriptionBreak.start_date.desc()).all()

    # Aktions-Log
    aktionen = AboAction.query.filter_by(
        subscription_id=abo.id
    ).order_by(AboAction.action_date.desc()).limit(20).all()

    # Positionen
    positionen = AboPosition.query.filter_by(
        subscription_id=abo.id
    ).order_by(AboPosition.created_at.desc()).all()

    # Betreuer
    betreuer = None
    if abo.supervisor_id:
        betreuer = Employee.query.get(abo.supervisor_id)

    today_str = date.today().strftime('%Y-%m-%d')

    return render_template('fitness/subscription_detail.html',
                           abo=abo, vorlage=vorlage, patient=patient,
                           besuche=besuche, rest_besuche=rest_besuche,
                           rechnungen=rechnungen, pausen=pausen,
                           aktionen=aktionen, positionen=positionen,
                           betreuer=betreuer, today_str=today_str)


@fitness_bp.route('/subscriptions/<int:sub_id>/edit', methods=['GET', 'POST'])
@login_required
def subscription_edit(sub_id):
    """Abo bearbeiten"""
    org_id = current_user.organization_id
    abo = Subscription.query.get_or_404(sub_id)
    if abo.organization_id != org_id:
        abort(403)
    employees = Employee.query.filter_by(organization_id=org_id).all()

    if request.method == 'POST':
        abo.notes = request.form.get('notes', '')
        abo.discount = float(request.form.get('discount', 0))
        abo.supervisor_id = int(request.form.get('supervisor_id', 0)) if request.form.get('supervisor_id') else None
        abo.abo_message = request.form.get('abo_message', '')
        msg_valid = request.form.get('message_valid_until', '')
        abo.message_valid_until = datetime.strptime(msg_valid, '%Y-%m-%d') if msg_valid else None
        abo.stop_reminding = request.form.get('stop_reminding') == 'on'
        abo.apply_vat = request.form.get('apply_vat') == 'on'
        abo.include_vat = request.form.get('include_vat') == 'on'

        _log_abo_action(abo.id, 1, 'Abo bearbeitet')
        db.session.commit()
        flash('Abo aktualisiert.', 'success')
        return redirect(url_for('fitness.subscription_detail', sub_id=sub_id))

    return render_template('fitness/subscription_edit.html', abo=abo, employees=employees)


@fitness_bp.route('/subscriptions/<int:sub_id>/pause', methods=['POST'])
@login_required
def subscription_pause(sub_id):
    """Abo pausieren"""
    org_id = current_user.organization_id
    abo = Subscription.query.get_or_404(sub_id)
    if abo.organization_id != org_id:
        abort(403)

    if abo.status == 'active':
        paused_from_str = request.form.get('paused_from', '')
        paused_until_str = request.form.get('paused_until', '')
        reason = request.form.get('reason', '').strip()
        break_price = float(request.form.get('break_price', 0))

        pause_start = datetime.strptime(paused_from_str, '%Y-%m-%d').date() if paused_from_str else date.today()
        pause_end = datetime.strptime(paused_until_str, '%Y-%m-%d').date() if paused_until_str else None

        abo.status = 'paused'
        abo.paused_from = pause_start
        abo.paused_until = pause_end

        # SubscriptionBreak anlegen
        pause = SubscriptionBreak(
            subscription_id=abo.id,
            start_date=pause_start,
            end_date=pause_end if pause_end else pause_start + timedelta(days=30),
            reason=reason,
            price=break_price
        )
        db.session.add(pause)

        _log_abo_action(abo.id, 2, f'Pausiert ab {pause_start.strftime("%d.%m.%Y")}'
                        + (f' bis {pause_end.strftime("%d.%m.%Y")}' if pause_end else '')
                        + (f' - Grund: {reason}' if reason else ''))
        db.session.commit()
        flash('Abo pausiert.', 'success')
    else:
        flash('Abo kann im aktuellen Status nicht pausiert werden.', 'error')

    return redirect(url_for('fitness.subscription_detail', sub_id=sub_id))


@fitness_bp.route('/subscriptions/<int:sub_id>/resume', methods=['POST'])
@login_required
def subscription_resume(sub_id):
    """Abo fortsetzen"""
    org_id = current_user.organization_id
    abo = Subscription.query.get_or_404(sub_id)
    if abo.organization_id != org_id:
        abort(403)

    if abo.status == 'paused':
        # Enddatum um die Pause-Dauer verlaengern
        if abo.paused_from and abo.end_date:
            pause_tage = (date.today() - abo.paused_from).days
            abo.end_date = abo.end_date + timedelta(days=pause_tage)
        abo.status = 'active'

        _log_abo_action(abo.id, 3, f'Fortgesetzt. Pause-Dauer: {(date.today() - abo.paused_from).days if abo.paused_from else 0} Tage')

        abo.paused_from = None
        abo.paused_until = None
        db.session.commit()
        flash('Abo fortgesetzt.', 'success')
    else:
        flash('Abo ist nicht pausiert.', 'error')

    return redirect(url_for('fitness.subscription_detail', sub_id=sub_id))


@fitness_bp.route('/subscriptions/<int:sub_id>/cancel', methods=['POST'])
@login_required
def subscription_cancel(sub_id):
    """Abo kuendigen"""
    org_id = current_user.organization_id
    abo = Subscription.query.get_or_404(sub_id)
    if abo.organization_id != org_id:
        abort(403)

    if abo.status in ('active', 'paused'):
        reason = request.form.get('reason', '').strip()
        abo.status = 'cancelled'
        _log_abo_action(abo.id, 4, f'Gekündigt' + (f' - Grund: {reason}' if reason else ''))
        db.session.commit()
        flash('Abo gekündigt.', 'success')
    else:
        flash('Abo kann nicht gekündigt werden.', 'error')

    return redirect(url_for('fitness.subscription_detail', sub_id=sub_id))


@fitness_bp.route('/subscriptions/<int:sub_id>/renew', methods=['POST'])
@login_required
def subscription_renew(sub_id):
    """Abo verlaengern"""
    org_id = current_user.organization_id
    abo = Subscription.query.get_or_404(sub_id)
    if abo.organization_id != org_id:
        abort(403)

    vorlage = abo.template
    new_start = abo.end_date if abo.end_date else date.today()
    new_end = None
    if vorlage.duration_months > 0:
        new_end = _add_months(new_start, vorlage.duration_months)

    count = Subscription.query.filter_by(organization_id=org_id).count()
    abo_nummer = f'ABO-{count + 1:05d}'

    neues_abo = Subscription(
        organization_id=org_id,
        patient_id=abo.patient_id,
        template_id=abo.template_id,
        subscription_number=abo_nummer,
        badge_number=abo.badge_number,
        start_date=new_start,
        end_date=new_end,
        status='active',
        visits_used=0,
        notes=f'Verlängerung von {abo.subscription_number}',
        discount=abo.discount,
        supervisor_id=abo.supervisor_id,
        created_by_id=current_user.id,
        price=abo.price or vorlage.price,
        apply_vat=abo.apply_vat,
        include_vat=abo.include_vat,
    )
    db.session.add(neues_abo)
    db.session.flush()

    _create_subscription_invoice(neues_abo, vorlage, org_id)
    _log_abo_action(neues_abo.id, 5, f'Verlängerung von {abo.subscription_number}')
    _log_abo_action(abo.id, 5, f'Verlängert zu {abo_nummer}')
    db.session.commit()

    flash(f'Abo verlängert. Neues Abo: {abo_nummer}', 'success')
    return redirect(url_for('fitness.subscription_detail', sub_id=neues_abo.id))


@fitness_bp.route('/subscriptions/<int:sub_id>/badge', methods=['POST'])
@login_required
def subscription_badge(sub_id):
    """Badge-Nummer zuordnen"""
    org_id = current_user.organization_id
    abo = Subscription.query.get_or_404(sub_id)
    if abo.organization_id != org_id:
        abort(403)

    old_badge = abo.badge_number
    abo.badge_number = request.form.get('badge_number', '').strip()
    _log_abo_action(abo.id, 6, f'Badge geändert: {old_badge or "—"} → {abo.badge_number or "—"}')
    db.session.commit()
    flash('Badge-Nummer aktualisiert.', 'success')
    return redirect(url_for('fitness.subscription_detail', sub_id=sub_id))


@fitness_bp.route('/subscriptions/<int:sub_id>/invoice', methods=['POST'])
@login_required
def subscription_create_invoice(sub_id):
    """Rechnung fuer Abo manuell erstellen"""
    org_id = current_user.organization_id
    abo = Subscription.query.get_or_404(sub_id)
    if abo.organization_id != org_id:
        abort(403)

    vorlage = abo.template
    invoice = _create_subscription_invoice(abo, vorlage, org_id)
    _log_abo_action(abo.id, 7, f'Rechnung erstellt: {invoice.invoice_number}')
    db.session.commit()
    flash('Rechnung erstellt.', 'success')
    return redirect(url_for('fitness.subscription_detail', sub_id=sub_id))


@fitness_bp.route('/subscriptions/<int:sub_id>/delete', methods=['POST'])
@login_required
def subscription_delete(sub_id):
    """Abo loeschen (soft delete)"""
    org_id = current_user.organization_id
    abo = Subscription.query.get_or_404(sub_id)
    if abo.organization_id != org_id:
        abort(403)

    abo.is_deleted = True
    _log_abo_action(abo.id, 8, 'Abo gelöscht')
    db.session.commit()
    flash('Abo gelöscht.', 'success')
    return redirect(url_for('fitness.subscriptions'))


# ============================================================
# Abo-Pausen (Breaks)
# ============================================================

@fitness_bp.route('/subscriptions/<int:sub_id>/breaks/add', methods=['POST'])
@login_required
def break_add(sub_id):
    """Pause hinzufuegen"""
    org_id = current_user.organization_id
    abo = Subscription.query.get_or_404(sub_id)
    if abo.organization_id != org_id:
        abort(403)

    start_str = request.form.get('break_start', '')
    end_str = request.form.get('break_end', '')
    reason = request.form.get('break_reason', '').strip()
    price = float(request.form.get('break_price', 0))

    if not start_str or not end_str:
        flash('Bitte Start- und Enddatum angeben.', 'error')
        return redirect(url_for('fitness.subscription_detail', sub_id=sub_id))

    start_date = datetime.strptime(start_str, '%Y-%m-%d').date()
    end_date = datetime.strptime(end_str, '%Y-%m-%d').date()

    if end_date < start_date:
        flash('Enddatum muss nach Startdatum liegen.', 'error')
        return redirect(url_for('fitness.subscription_detail', sub_id=sub_id))

    pause = SubscriptionBreak(
        subscription_id=abo.id,
        start_date=start_date,
        end_date=end_date,
        reason=reason,
        price=price
    )
    db.session.add(pause)

    # Enddatum um Pause-Tage verlaengern
    pause_tage = (end_date - start_date).days + 1
    if abo.end_date:
        abo.end_date = abo.end_date + timedelta(days=pause_tage)

    _log_abo_action(abo.id, 2, f'Pause hinzugefügt: {start_date.strftime("%d.%m.%Y")} - {end_date.strftime("%d.%m.%Y")} ({pause_tage} Tage)')
    db.session.commit()
    flash(f'Pause hinzugefügt ({pause_tage} Tage). Enddatum angepasst.', 'success')
    return redirect(url_for('fitness.subscription_detail', sub_id=sub_id))


@fitness_bp.route('/breaks/<int:break_id>/delete', methods=['POST'])
@login_required
def break_delete(break_id):
    """Pause loeschen"""
    pause = SubscriptionBreak.query.get_or_404(break_id)
    abo = Subscription.query.get(pause.subscription_id)
    if not abo or abo.organization_id != current_user.organization_id:
        abort(403)

    # Enddatum zuruecksetzen
    pause_tage = (pause.end_date - pause.start_date).days + 1
    if abo.end_date:
        abo.end_date = abo.end_date - timedelta(days=pause_tage)

    _log_abo_action(abo.id, 3, f'Pause gelöscht: {pause.start_date.strftime("%d.%m.%Y")} - {pause.end_date.strftime("%d.%m.%Y")}')
    db.session.delete(pause)
    db.session.commit()
    flash('Pause gelöscht. Enddatum angepasst.', 'success')
    return redirect(url_for('fitness.subscription_detail', sub_id=abo.id))


# ============================================================
# Abo-Positionen
# ============================================================

@fitness_bp.route('/subscriptions/<int:sub_id>/positions/add', methods=['POST'])
@login_required
def position_add(sub_id):
    """Position hinzufuegen"""
    org_id = current_user.organization_id
    abo = Subscription.query.get_or_404(sub_id)
    if abo.organization_id != org_id:
        abort(403)

    pos = AboPosition(
        subscription_id=abo.id,
        name=request.form.get('pos_name', ''),
        quantity=int(request.form.get('pos_quantity', 1)),
        unit_price_netto=float(request.form.get('pos_price', 0)),
        vat_rate=float(request.form.get('pos_vat', 0)),
        created_by_id=current_user.id
    )
    db.session.add(pos)
    _log_abo_action(abo.id, 9, f'Position hinzugefügt: {pos.name}')
    db.session.commit()
    flash('Position hinzugefügt.', 'success')
    return redirect(url_for('fitness.subscription_detail', sub_id=sub_id))


@fitness_bp.route('/positions/<int:pos_id>/delete', methods=['POST'])
@login_required
def position_delete(pos_id):
    """Position loeschen"""
    pos = AboPosition.query.get_or_404(pos_id)
    abo = Subscription.query.get(pos.subscription_id)
    if not abo or abo.organization_id != current_user.organization_id:
        abort(403)

    _log_abo_action(abo.id, 9, f'Position gelöscht: {pos.name}')
    db.session.delete(pos)
    db.session.commit()
    flash('Position gelöscht.', 'success')
    return redirect(url_for('fitness.subscription_detail', sub_id=abo.id))


# ============================================================
# Besuche
# ============================================================

@fitness_bp.route('/visits')
@login_required
def visits():
    """Besuchsuebersicht"""
    org_id = current_user.organization_id
    date_filter = request.args.get('date', '')
    page = request.args.get('page', 1, type=int)
    per_page = 50

    query = FitnessVisit.query.join(Subscription).filter(
        Subscription.organization_id == org_id
    )

    if date_filter:
        filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
        query = query.filter(func.date(FitnessVisit.check_in) == filter_date)

    query = query.order_by(FitnessVisit.check_in.desc())
    total = query.count()
    besuche = query.offset((page - 1) * per_page).limit(per_page).all()
    total_pages = (total + per_page - 1) // per_page

    # Statistik: Besuche pro Tag der letzten 30 Tage
    thirty_days_ago = datetime.now() - timedelta(days=30)
    visit_stats = db.session.query(
        func.date(FitnessVisit.check_in).label('tag'),
        func.count(FitnessVisit.id).label('anzahl')
    ).join(Subscription).filter(
        Subscription.organization_id == org_id,
        FitnessVisit.check_in >= thirty_days_ago
    ).group_by(func.date(FitnessVisit.check_in)).order_by(
        func.date(FitnessVisit.check_in)
    ).all()

    chart_labels = [str(s.tag) for s in visit_stats]
    chart_data = [s.anzahl for s in visit_stats]

    return render_template('fitness/visits.html',
                           besuche=besuche, date_filter=date_filter,
                           page=page, total=total, total_pages=total_pages,
                           chart_labels=json.dumps(chart_labels),
                           chart_data=json.dumps(chart_data))


# ============================================================
# Check-in
# ============================================================

@fitness_bp.route('/checkin')
@login_required
def checkin():
    """Check-in Seite (Tablet-optimiert)"""
    org_id = current_user.organization_id

    # Letzte 10 Check-ins
    letzte_checkins = FitnessVisit.query.join(Subscription).filter(
        Subscription.organization_id == org_id,
        func.date(FitnessVisit.check_in) == date.today()
    ).order_by(FitnessVisit.check_in.desc()).limit(10).all()

    return render_template('fitness/checkin.html', letzte_checkins=letzte_checkins)


@fitness_bp.route('/api/checkin', methods=['POST'])
@login_required
def api_checkin():
    """Check-in API: Badge-Nummer oder Patientenname"""
    org_id = current_user.organization_id
    data = request.get_json() or {}
    eingabe = data.get('eingabe', '').strip()

    if not eingabe:
        return jsonify({'success': False, 'message': 'Bitte Badge-Nummer oder Name eingeben.'})

    # Abo suchen: zuerst per Badge, dann per Patientenname
    abo = Subscription.query.filter(
        Subscription.organization_id == org_id,
        Subscription.badge_number == eingabe,
        Subscription.status == 'active',
        Subscription.is_deleted == False
    ).first()

    if not abo:
        patient = Patient.query.filter(
            Patient.organization_id == org_id,
            or_(
                Patient.last_name.ilike(f'%{eingabe}%'),
                Patient.first_name.ilike(f'%{eingabe}%')
            )
        ).first()
        if patient:
            abo = Subscription.query.filter(
                Subscription.organization_id == org_id,
                Subscription.patient_id == patient.id,
                Subscription.status == 'active',
                Subscription.is_deleted == False
            ).first()

    if not abo:
        return jsonify({
            'success': False,
            'message': 'Kein gültiges Abo gefunden.',
            'grund': 'Kein aktives Abonnement für diese Eingabe vorhanden.'
        })

    # Abo-Gueltigkeitspruefung
    vorlage = abo.template
    today = date.today()

    if abo.end_date and abo.end_date < today:
        return jsonify({
            'success': False,
            'message': 'Abo abgelaufen.',
            'grund': f'Das Abo ist am {abo.end_date.strftime("%d.%m.%Y")} abgelaufen.'
        })

    if abo.status == 'paused':
        return jsonify({
            'success': False,
            'message': 'Abo pausiert.',
            'grund': 'Das Abonnement ist momentan pausiert.'
        })

    # Pause-Zeitraum pruefen
    aktive_pause = SubscriptionBreak.query.filter(
        SubscriptionBreak.subscription_id == abo.id,
        SubscriptionBreak.start_date <= today,
        SubscriptionBreak.end_date >= today
    ).first()
    if aktive_pause:
        return jsonify({
            'success': False,
            'message': 'Abo pausiert.',
            'grund': f'Pause bis {aktive_pause.end_date.strftime("%d.%m.%Y")}' +
                     (f' ({aktive_pause.reason})' if aktive_pause.reason else '')
        })

    # Mehrfachkarte: Besuche pruefen
    if vorlage and vorlage.max_visits > 0 and (abo.visits_used or 0) >= vorlage.max_visits:
        return jsonify({
            'success': False,
            'message': 'Alle Besuche aufgebraucht.',
            'grund': f'{abo.visits_used} von {vorlage.max_visits} Besuchen verwendet.'
        })

    # Zugangszeiten pruefen (valid_times)
    if vorlage and vorlage.valid_times:
        try:
            valid_times = json.loads(vorlage.valid_times)
            # Vereinfachte Pruefung: aktueller Wochentag
            now = datetime.now()
            weekday_names = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']
            current_day = weekday_names[now.weekday()]
            # Pruefen ob Zeitfenster existiert
            if valid_times and isinstance(valid_times, list):
                valid = False
                for slot in valid_times:
                    if slot.get('day') == now.weekday():
                        start_h, start_m = (slot.get('start', '00:00') or '00:00').split(':')
                        end_h, end_m = (slot.get('end', '23:59') or '23:59').split(':')
                        if int(start_h) * 60 + int(start_m) <= now.hour * 60 + now.minute <= int(end_h) * 60 + int(end_m):
                            valid = True
                            break
                if not valid and len(valid_times) > 0:
                    return jsonify({
                        'success': False,
                        'message': 'Ausserhalb der gültigen Zeiten.',
                        'grund': f'Aktuell: {current_day} {now.strftime("%H:%M")}'
                    })
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

    # Check-in registrieren
    besuch = FitnessVisit(
        subscription_id=abo.id,
        patient_id=abo.patient_id,
        location_id=None,
        check_in=datetime.now()
    )
    db.session.add(besuch)
    abo.visits_used = (abo.visits_used or 0) + 1

    # Gantner-Trace
    if abo.badge_number:
        trace = GantnerTrace(
            patient_id=abo.patient_id,
            abo_id=abo.id,
            batch_id=abo.badge_number,
            access_granted=True
        )
        db.session.add(trace)

    db.session.commit()

    patient = abo.patient
    result = {
        'success': True,
        'message': f'Willkommen, {patient.first_name} {patient.last_name}!',
        'patient_name': f'{patient.first_name} {patient.last_name}',
        'abo_typ': vorlage.name if vorlage else '',
        'abo_nummer': abo.subscription_number,
        'visit_id': besuch.id
    }

    # Patient-Nachricht anzeigen
    if abo.abo_message and (not abo.message_valid_until or abo.message_valid_until >= datetime.now()):
        result['patient_message'] = abo.abo_message

    if vorlage and vorlage.max_visits > 0:
        rest = vorlage.max_visits - abo.visits_used
        result['rest_besuche'] = rest
        result['max_besuche'] = vorlage.max_visits
        result['message'] += f' (Noch {rest} Besuche übrig)'

    return jsonify(result)


@fitness_bp.route('/api/checkout', methods=['POST'])
@login_required
def api_checkout():
    """Check-out API"""
    org_id = current_user.organization_id
    data = request.get_json() or {}
    visit_id = data.get('visit_id')

    if not visit_id:
        return jsonify({'success': False, 'message': 'Besuch-ID fehlt.'})

    besuch = FitnessVisit.query.get(visit_id)
    if not besuch or besuch.subscription.organization_id != org_id:
        return jsonify({'success': False, 'message': 'Besuch nicht gefunden.'})

    besuch.check_out = datetime.now()
    db.session.commit()
    return jsonify({'success': True, 'message': 'Check-out erfolgreich.'})


# ============================================================
# Fitness-Einstellungen (Konfiguration)
# ============================================================

@fitness_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    """Fitness-Einstellungen pro Standort"""
    org_id = current_user.organization_id
    locations = Location.query.filter_by(organization_id=org_id).all()
    location_id = request.args.get('location_id', type=int)

    if not location_id and locations:
        location_id = locations[0].id

    config = FitnessConfig.query.filter_by(
        organization_id=org_id, location_id=location_id
    ).first() if location_id else None

    if request.method == 'POST' and location_id:
        if not config:
            config = FitnessConfig(organization_id=org_id, location_id=location_id)
            db.session.add(config)

        # Allgemein
        config.contract_text = request.form.get('contract_text', '')
        config.depot_price = float(request.form.get('depot_price', 0)) if request.form.get('depot_price') else None
        config.nfc_writer = request.form.get('nfc_writer', '')
        config.payment_due_days = int(request.form.get('payment_due_days', 30))
        config.zsr = request.form.get('zsr', '')

        # eGym
        config.egym_id = request.form.get('egym_id', '')
        config.egym_token = request.form.get('egym_token', '')
        egym_settings = {
            'sync_patients': request.form.get('egym_sync_patients') == 'on',
            'sync_batches': request.form.get('egym_sync_batches') == 'on',
            'sync_visits': request.form.get('egym_sync_visits') == 'on',
        }
        config.egym_settings_json = json.dumps(egym_settings)

        # Milon
        config.milon_id = request.form.get('milon_id', '')
        config.milon_token = request.form.get('milon_token', '')
        milon_settings = {
            'sync_patients': request.form.get('milon_sync_patients') == 'on',
            'sync_batches': request.form.get('milon_sync_batches') == 'on',
            'sync_visits': request.form.get('milon_sync_visits') == 'on',
        }
        config.milon_settings_json = json.dumps(milon_settings)

        # MyWellness
        config.mywellness_api_key = request.form.get('mywellness_api_key', '')
        config.mywellness_url = request.form.get('mywellness_url', '')
        config.mywellness_facility_id = request.form.get('mywellness_facility_id', '')
        mywellness_settings = {
            'sync_patients': request.form.get('mywellness_sync_patients') == 'on',
            'sync_batches': request.form.get('mywellness_sync_batches') == 'on',
            'sync_visits': request.form.get('mywellness_sync_visits') == 'on',
            'device_type': request.form.get('mywellness_device_type', 'TGS'),
        }
        config.mywellness_settings_json = json.dumps(mywellness_settings)

        # Gantner
        gantner_config = {
            'use_badge_as_visit': request.form.get('gantner_use_badge_as_visit') == 'on',
            'track_badge_outs': request.form.get('gantner_track_badge_outs') == 'on',
            'custom_opening_times': request.form.get('gantner_opening_times', ''),
        }
        config.gantner_config_json = json.dumps(gantner_config)

        # Sonstiges
        config.use_start_as_due_date = request.form.get('use_start_as_due_date') == 'on'
        config.hide_qualicert = request.form.get('hide_qualicert') == 'on'

        db.session.commit()
        flash('Fitness-Einstellungen gespeichert.', 'success')
        return redirect(url_for('fitness.settings', location_id=location_id))

    # JSON-Settings parsen fuer Template
    egym_settings = {}
    milon_settings = {}
    mywellness_settings = {}
    gantner_config_parsed = {}
    if config:
        try:
            egym_settings = json.loads(config.egym_settings_json) if config.egym_settings_json else {}
        except (json.JSONDecodeError, TypeError):
            pass
        try:
            milon_settings = json.loads(config.milon_settings_json) if config.milon_settings_json else {}
        except (json.JSONDecodeError, TypeError):
            pass
        try:
            mywellness_settings = json.loads(config.mywellness_settings_json) if config.mywellness_settings_json else {}
        except (json.JSONDecodeError, TypeError):
            pass
        try:
            gantner_config_parsed = json.loads(config.gantner_config_json) if config.gantner_config_json else {}
        except (json.JSONDecodeError, TypeError):
            pass

    return render_template('fitness/settings.html',
                           locations=locations, location_id=location_id,
                           config=config,
                           egym_settings=egym_settings,
                           milon_settings=milon_settings,
                           mywellness_settings=mywellness_settings,
                           gantner_config=gantner_config_parsed)


# ============================================================
# Automatisierungen
# ============================================================

@fitness_bp.route('/automations')
@login_required
def automations():
    """Liste aller Automatisierungen"""
    org_id = current_user.organization_id
    automations_list = FitnessAutomation.query.filter_by(
        organization_id=org_id, is_deleted=False
    ).order_by(FitnessAutomation.created_at.desc()).all()

    # Regeln parsen fuer Anzeige
    action_labels = {0: 'Nach Start', 1: 'Nach Ende', 2: 'Vor Start', 3: 'Vor Ende',
                     4: 'Nach Besuch', 5: 'Ohne Besuch', 6: 'Geburtstag'}
    for a in automations_list:
        try:
            rules = json.loads(a.rules_json) if a.rules_json else {}
            action = rules.get('action', -1)
            days = rules.get('days_or_visits', 0)
            a._trigger_label = action_labels.get(action, '—')
            if days > 0:
                a._trigger_label += f' ({days} Tage)'
        except (json.JSONDecodeError, TypeError):
            a._trigger_label = '—'

    return render_template('fitness/automations.html', automations=automations_list)


@fitness_bp.route('/automations/new', methods=['GET', 'POST'])
@login_required
def automation_new():
    """Neue Automatisierung erstellen"""
    org_id = current_user.organization_id
    vorlagen = SubscriptionTemplate.query.filter_by(organization_id=org_id, is_deleted=False, is_active=True).all()

    if request.method == 'POST':
        auto = _save_automation(None, org_id)
        db.session.add(auto)
        db.session.commit()
        flash('Automatisierung erstellt.', 'success')
        return redirect(url_for('fitness.automations'))

    return render_template('fitness/automation_form.html', automation=None, vorlagen=vorlagen)


@fitness_bp.route('/automations/<int:auto_id>/edit', methods=['GET', 'POST'])
@login_required
def automation_edit(auto_id):
    """Automatisierung bearbeiten"""
    org_id = current_user.organization_id
    auto = FitnessAutomation.query.get_or_404(auto_id)
    if auto.organization_id != org_id:
        abort(403)
    vorlagen = SubscriptionTemplate.query.filter_by(organization_id=org_id, is_deleted=False, is_active=True).all()

    if request.method == 'POST':
        _save_automation(auto, org_id)
        db.session.commit()
        flash('Automatisierung aktualisiert.', 'success')
        return redirect(url_for('fitness.automations'))

    # Regeln parsen
    rules = {}
    try:
        rules = json.loads(auto.rules_json) if auto.rules_json else {}
    except (json.JSONDecodeError, TypeError):
        pass

    return render_template('fitness/automation_form.html', automation=auto, vorlagen=vorlagen, rules=rules)


@fitness_bp.route('/automations/<int:auto_id>/delete', methods=['POST'])
@login_required
def automation_delete(auto_id):
    """Automatisierung loeschen (soft delete)"""
    org_id = current_user.organization_id
    auto = FitnessAutomation.query.get_or_404(auto_id)
    if auto.organization_id != org_id:
        abort(403)
    auto.is_deleted = True
    db.session.commit()
    flash('Automatisierung gelöscht.', 'success')
    return redirect(url_for('fitness.automations'))


def _save_automation(auto, org_id):
    """Speichert eine Automatisierung"""
    if auto is None:
        auto = FitnessAutomation(organization_id=org_id, created_by_id=current_user.id)

    auto.title = request.form.get('title', '')
    auto.automation_type = int(request.form.get('automation_type', 0))

    # Regeln als JSON
    rules = {
        'action': int(request.form.get('action', 0)),
        'days_or_visits': int(request.form.get('days_or_visits', 0)),
        'send_once_per_patient': request.form.get('send_once_per_patient') == 'on',
        'send_once_per_abo': request.form.get('send_once_per_abo') == 'on',
        'only_send_without_extension': request.form.get('only_send_without_extension') == 'on',
        'send_via_mail': request.form.get('send_via_mail') == 'on',
    }
    auto.rules_json = json.dumps(rules)

    auto.extend_with_template_id = int(request.form.get('extend_with_template_id', 0)) if request.form.get('extend_with_template_id') else None

    return auto


# ============================================================
# Gantner Zugangsprotokoll
# ============================================================

@fitness_bp.route('/gantner')
@login_required
def gantner_log():
    """Gantner Zugangsprotokoll"""
    org_id = current_user.organization_id
    page = request.args.get('page', 1, type=int)
    per_page = 50
    date_filter = request.args.get('date', '')
    access_filter = request.args.get('access', '')

    query = GantnerTrace.query.join(Patient).filter(
        Patient.organization_id == org_id
    )

    if date_filter:
        filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
        query = query.filter(func.date(GantnerTrace.created_at) == filter_date)

    if access_filter == 'granted':
        query = query.filter(GantnerTrace.access_granted == True)
    elif access_filter == 'denied':
        query = query.filter(GantnerTrace.access_granted == False)

    query = query.order_by(GantnerTrace.created_at.desc())
    total = query.count()
    traces = query.offset((page - 1) * per_page).limit(per_page).all()
    total_pages = (total + per_page - 1) // per_page

    # Statistik
    today = date.today()
    zutritte_heute = GantnerTrace.query.join(Patient).filter(
        Patient.organization_id == org_id,
        func.date(GantnerTrace.created_at) == today,
        GantnerTrace.access_granted == True
    ).count()

    abgelehnt_heute = GantnerTrace.query.join(Patient).filter(
        Patient.organization_id == org_id,
        func.date(GantnerTrace.created_at) == today,
        GantnerTrace.access_granted == False
    ).count()

    return render_template('fitness/gantner.html',
                           traces=traces, date_filter=date_filter,
                           access_filter=access_filter,
                           page=page, total=total, total_pages=total_pages,
                           zutritte_heute=zutritte_heute,
                           abgelehnt_heute=abgelehnt_heute)


# ============================================================
# API-Endpunkte
# ============================================================

@fitness_bp.route('/api/patients/search')
@login_required
def api_patient_search():
    """Patient suchen fuer Autocomplete"""
    org_id = current_user.organization_id
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify([])

    patients = Patient.query.filter(
        Patient.organization_id == org_id,
        or_(
            Patient.first_name.ilike(f'%{q}%'),
            Patient.last_name.ilike(f'%{q}%')
        )
    ).limit(10).all()

    return jsonify([{
        'id': p.id,
        'name': f'{p.first_name} {p.last_name}',
        'geburtsdatum': p.date_of_birth.strftime('%d.%m.%Y') if p.date_of_birth else ''
    } for p in patients])


@fitness_bp.route('/api/template/<int:template_id>')
@login_required
def api_template_detail(template_id):
    """Vorlage-Details fuer Abo-Formular"""
    vorlage = SubscriptionTemplate.query.get_or_404(template_id)
    if vorlage.organization_id != current_user.organization_id:
        abort(403)

    return jsonify({
        'id': vorlage.id,
        'name': vorlage.name,
        'category': vorlage.category,
        'duration_months': vorlage.duration_months,
        'price': float(vorlage.price) if vorlage.price else 0,
        'payment_interval': vorlage.payment_interval,
        'max_visits': vorlage.max_visits,
        'auto_renew': vorlage.auto_renew,
        'price_once': float(vorlage.price_once) if vorlage.price_once else None,
        'price_month': float(vorlage.price_month) if vorlage.price_month else None,
        'price_rate': float(vorlage.price_rate) if vorlage.price_rate else None,
        'price_batch_depot': float(vorlage.price_batch_depot) if vorlage.price_batch_depot else None,
    })


@fitness_bp.route('/api/stats')
@login_required
def api_stats():
    """Fitness-Statistiken als JSON"""
    org_id = current_user.organization_id
    today = date.today()

    aktive = Subscription.query.filter_by(organization_id=org_id, status='active').filter(
        Subscription.is_deleted == False).count()
    pausiert = Subscription.query.filter_by(organization_id=org_id, status='paused').filter(
        Subscription.is_deleted == False).count()
    besuche_heute = FitnessVisit.query.join(Subscription).filter(
        Subscription.organization_id == org_id,
        func.date(FitnessVisit.check_in) == today
    ).count()

    return jsonify({
        'aktive_abos': aktive,
        'pausierte_abos': pausiert,
        'besuche_heute': besuche_heute
    })


# ============================================================
# Hilfsfunktionen
# ============================================================

def _create_subscription_invoice(abo, vorlage, org_id):
    """Erstellt eine Rechnung fuer ein Abo"""
    count = Invoice.query.filter_by(organization_id=org_id).count()
    invoice_number = f'RE-{count + 1:05d}'

    # Preis mit Rabatt berechnen
    basis_preis = float(abo.price or vorlage.price or 0)
    rabatt = float(abo.discount or 0)

    if vorlage.payment_interval == 'monthly':
        betrag = basis_preis
        beschreibung = f'{vorlage.name} - Monatsbeitrag'
    elif vorlage.payment_interval == 'quarterly':
        betrag = basis_preis * 3
        beschreibung = f'{vorlage.name} - Quartalsbeitrag'
    elif vorlage.payment_interval == 'yearly':
        betrag = basis_preis * 12
        beschreibung = f'{vorlage.name} - Jahresbeitrag'
    else:  # once
        betrag = basis_preis
        beschreibung = f'{vorlage.name} - Einmalzahlung'

    # Rabatt anwenden
    if rabatt > 0:
        betrag = betrag * (1 - rabatt / 100)
        beschreibung += f' (Rabatt: {rabatt}%)'

    invoice = Invoice(
        organization_id=org_id,
        patient_id=abo.patient_id,
        invoice_number=invoice_number,
        due_date=date.today() + timedelta(days=30),
        amount_total=round(betrag, 2),
        amount_open=round(betrag, 2),
        status='sent',
        category='fitness',
        notes=f'Abo {abo.subscription_number}: {beschreibung}'
    )
    db.session.add(invoice)
    db.session.flush()

    item = InvoiceItem(
        invoice_id=invoice.id,
        description=beschreibung,
        quantity=1,
        amount=round(betrag, 2)
    )
    db.session.add(item)

    return invoice
