"""Routen fuer Fitness: Abonnemente, Vorlagen, Besuche, Check-in"""
import json
from datetime import datetime, date, timedelta
from flask import render_template, request, jsonify, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from blueprints.fitness import fitness_bp
from models import db, SubscriptionTemplate, Subscription, FitnessVisit, Patient, Location, Invoice, InvoiceItem
from sqlalchemy import func, or_


def _add_months(source_date, months):
    """Addiert Monate zu einem Datum"""
    month = source_date.month - 1 + months
    year = source_date.year + month // 12
    month = month % 12 + 1
    import calendar
    day = min(source_date.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


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

    ablaufende_abos = Subscription.query.filter(
        Subscription.organization_id == org_id,
        Subscription.status == 'active',
        Subscription.end_date != None,
        Subscription.end_date >= month_start,
        Subscription.end_date <= month_end
    ).count()

    besuche_heute = FitnessVisit.query.join(Subscription).filter(
        Subscription.organization_id == org_id,
        func.date(FitnessVisit.check_in) == today
    ).count()

    # Umsatz Fitness aktueller Monat (Summe aller Abo-Rechnungen im Monat)
    umsatz_monat = db.session.query(func.sum(Invoice.amount_total)).filter(
        Invoice.organization_id == org_id,
        Invoice.category == 'fitness',
        Invoice.created_at >= datetime.combine(month_start, datetime.min.time()),
        Invoice.created_at <= datetime.combine(month_end, datetime.max.time())
    ).scalar() or 0

    # Letzte Besuche
    letzte_besuche = FitnessVisit.query.join(Subscription).filter(
        Subscription.organization_id == org_id
    ).order_by(FitnessVisit.check_in.desc()).limit(10).all()

    return render_template('fitness/index.html',
                           aktive_abos=aktive_abos,
                           ablaufende_abos=ablaufende_abos,
                           besuche_heute=besuche_heute,
                           umsatz_monat=umsatz_monat,
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
        organization_id=org_id
    ).order_by(SubscriptionTemplate.name).all()
    return render_template('fitness/templates.html', vorlagen=vorlagen)


@fitness_bp.route('/templates/new', methods=['GET', 'POST'])
@login_required
def template_new():
    """Neue Abo-Vorlage erstellen"""
    org_id = current_user.organization_id
    locations = Location.query.filter_by(organization_id=org_id).all()

    if request.method == 'POST':
        vorlage = SubscriptionTemplate(
            organization_id=org_id,
            name=request.form.get('name', ''),
            category=request.form.get('category', 'fitness'),
            duration_months=int(request.form.get('duration_months', 12)),
            price=float(request.form.get('price', 0)),
            payment_interval=request.form.get('payment_interval', 'monthly'),
            cancellation_months=int(request.form.get('cancellation_months', 1)),
            auto_renew=request.form.get('auto_renew') == 'on',
            max_visits=int(request.form.get('max_visits', 0)),
            access_hours_json=request.form.get('access_hours_json', ''),
            location_id=int(request.form['location_id']) if request.form.get('location_id') else None,
            is_active=True
        )
        db.session.add(vorlage)
        db.session.commit()
        flash('Abo-Vorlage erstellt.', 'success')
        return redirect(url_for('fitness.templates'))

    return render_template('fitness/template_form.html', vorlage=None, locations=locations)


@fitness_bp.route('/templates/<int:template_id>/edit', methods=['GET', 'POST'])
@login_required
def template_edit(template_id):
    """Abo-Vorlage bearbeiten"""
    org_id = current_user.organization_id
    vorlage = SubscriptionTemplate.query.get_or_404(template_id)
    if vorlage.organization_id != org_id:
        abort(403)
    locations = Location.query.filter_by(organization_id=org_id).all()

    if request.method == 'POST':
        vorlage.name = request.form.get('name', vorlage.name)
        vorlage.category = request.form.get('category', vorlage.category)
        vorlage.duration_months = int(request.form.get('duration_months', vorlage.duration_months))
        vorlage.price = float(request.form.get('price', vorlage.price))
        vorlage.payment_interval = request.form.get('payment_interval', vorlage.payment_interval)
        vorlage.cancellation_months = int(request.form.get('cancellation_months', vorlage.cancellation_months))
        vorlage.auto_renew = request.form.get('auto_renew') == 'on'
        vorlage.max_visits = int(request.form.get('max_visits', vorlage.max_visits))
        vorlage.access_hours_json = request.form.get('access_hours_json', '')
        vorlage.location_id = int(request.form['location_id']) if request.form.get('location_id') else None
        vorlage.is_active = request.form.get('is_active') != 'off'
        db.session.commit()
        flash('Abo-Vorlage aktualisiert.', 'success')
        return redirect(url_for('fitness.templates'))

    return render_template('fitness/template_form.html', vorlage=vorlage, locations=locations)


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
    page = request.args.get('page', 1, type=int)
    per_page = 25

    query = Subscription.query.filter_by(organization_id=org_id)

    if status_filter:
        query = query.filter(Subscription.status == status_filter)

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

    return render_template('fitness/subscriptions.html',
                           abos=abos, search=search, status_filter=status_filter,
                           page=page, total=total, total_pages=total_pages)


@fitness_bp.route('/subscriptions/new', methods=['GET', 'POST'])
@login_required
def subscription_new():
    """Neues Abo erstellen"""
    org_id = current_user.organization_id
    vorlagen = SubscriptionTemplate.query.filter_by(organization_id=org_id, is_active=True).all()

    if request.method == 'POST':
        template_id = int(request.form.get('template_id', 0))
        patient_id = int(request.form.get('patient_id', 0))
        start_date_str = request.form.get('start_date', '')
        badge_number = request.form.get('badge_number', '').strip()
        notes = request.form.get('notes', '').strip()

        vorlage = SubscriptionTemplate.query.get(template_id)
        patient = Patient.query.get(patient_id)
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
            notes=notes
        )
        db.session.add(abo)
        db.session.flush()

        # Erste Rechnung automatisch erstellen
        _create_subscription_invoice(abo, vorlage, org_id)

        db.session.commit()
        flash(f'Abo {abo_nummer} für {patient.first_name} {patient.last_name} erstellt.', 'success')
        return redirect(url_for('fitness.subscription_detail', sub_id=abo.id))

    return render_template('fitness/subscription_form.html', vorlagen=vorlagen)


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
    if vorlage.max_visits > 0:
        rest_besuche = vorlage.max_visits - abo.visits_used

    # Rechnungen zu diesem Abo
    rechnungen = Invoice.query.filter_by(
        organization_id=org_id,
        patient_id=abo.patient_id,
        category='fitness'
    ).order_by(Invoice.created_at.desc()).limit(10).all()

    return render_template('fitness/subscription_detail.html',
                           abo=abo, vorlage=vorlage, patient=patient,
                           besuche=besuche, rest_besuche=rest_besuche,
                           rechnungen=rechnungen)


@fitness_bp.route('/subscriptions/<int:sub_id>/pause', methods=['POST'])
@login_required
def subscription_pause(sub_id):
    """Abo pausieren"""
    org_id = current_user.organization_id
    abo = Subscription.query.get_or_404(sub_id)
    if abo.organization_id != org_id:
        abort(403)

    if abo.status == 'active':
        abo.status = 'paused'
        abo.paused_from = date.today()
        paused_until_str = request.form.get('paused_until', '')
        if paused_until_str:
            abo.paused_until = datetime.strptime(paused_until_str, '%Y-%m-%d').date()
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
        abo.status = 'cancelled'
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
        notes=f'Verlängerung von {abo.subscription_number}'
    )
    db.session.add(neues_abo)
    db.session.flush()

    _create_subscription_invoice(neues_abo, vorlage, org_id)
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

    abo.badge_number = request.form.get('badge_number', '').strip()
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
    _create_subscription_invoice(abo, vorlage, org_id)
    db.session.commit()
    flash('Rechnung erstellt.', 'success')
    return redirect(url_for('fitness.subscription_detail', sub_id=sub_id))


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
        Subscription.status == 'active'
    ).first()

    if not abo:
        # Per Patientenname suchen
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
                Subscription.status == 'active'
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

    # Mehrfachkarte: Besuche pruefen
    if vorlage.max_visits > 0 and abo.visits_used >= vorlage.max_visits:
        return jsonify({
            'success': False,
            'message': 'Alle Besuche aufgebraucht.',
            'grund': f'{abo.visits_used} von {vorlage.max_visits} Besuchen verwendet.'
        })

    # Check-in registrieren
    besuch = FitnessVisit(
        subscription_id=abo.id,
        patient_id=abo.patient_id,
        location_id=None,
        check_in=datetime.now()
    )
    db.session.add(besuch)
    abo.visits_used = (abo.visits_used or 0) + 1
    db.session.commit()

    patient = abo.patient
    result = {
        'success': True,
        'message': f'Willkommen, {patient.first_name} {patient.last_name}!',
        'patient_name': f'{patient.first_name} {patient.last_name}',
        'abo_typ': vorlage.name,
        'abo_nummer': abo.subscription_number
    }

    if vorlage.max_visits > 0:
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
        'price': vorlage.price,
        'payment_interval': vorlage.payment_interval,
        'max_visits': vorlage.max_visits,
        'auto_renew': vorlage.auto_renew
    })


@fitness_bp.route('/api/stats')
@login_required
def api_stats():
    """Fitness-Statistiken als JSON"""
    org_id = current_user.organization_id
    today = date.today()

    aktive = Subscription.query.filter_by(organization_id=org_id, status='active').count()
    pausiert = Subscription.query.filter_by(organization_id=org_id, status='paused').count()
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
    # Rechnungsnummer generieren
    count = Invoice.query.filter_by(organization_id=org_id).count()
    invoice_number = f'RE-{count + 1:05d}'

    # Betrag berechnen
    if vorlage.payment_interval == 'monthly':
        betrag = vorlage.price
        beschreibung = f'{vorlage.name} - Monatsbeitrag'
    elif vorlage.payment_interval == 'quarterly':
        betrag = vorlage.price * 3
        beschreibung = f'{vorlage.name} - Quartalsbeitrag'
    elif vorlage.payment_interval == 'yearly':
        betrag = vorlage.price * 12
        beschreibung = f'{vorlage.name} - Jahresbeitrag'
    else:  # once
        betrag = vorlage.price
        beschreibung = f'{vorlage.name} - Einmalzahlung'

    invoice = Invoice(
        organization_id=org_id,
        patient_id=abo.patient_id,
        invoice_number=invoice_number,
        due_date=date.today() + timedelta(days=30),
        amount_total=betrag,
        amount_open=betrag,
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
        amount=betrag
    )
    db.session.add(item)

    return invoice
