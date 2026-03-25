import json
from datetime import datetime, timedelta, date, time
from flask import render_template, request, jsonify
from flask_login import login_required, current_user
from blueprints.dashboard import dashboard_bp
from models import (db, Appointment, Patient, Employee, Task, ChatMessage,
                    TreatmentSeries, CostApproval, Email, Invoice, WorkSchedule,
                    Absence, User)
from ai.coordinator import Coordinator
from sqlalchemy import func, case
from sqlalchemy.orm import joinedload, selectinload
from utils.auth import check_org
from app import limiter


# === Standard-Widget-Konfigurationen pro Rolle ===
DEFAULT_WIDGET_CONFIG = {
    'admin': [
        'ki_tagesuebersicht', 'heutige_termine', 'offene_aufgaben',
        'patientenverlauf', 'umsatzuebersicht', 'geburtstage',
        'schnellaktionen', 'auslastung', 'offene_rechnungen',
        'ungelesene_emails', 'absenzen'
    ],
    'therapist': [
        'ki_tagesuebersicht', 'heutige_termine', 'offene_aufgaben',
        'patientenverlauf', 'schnellaktionen', 'auslastung'
    ],
    'reception': [
        'heutige_termine', 'offene_aufgaben', 'ungelesene_emails',
        'schnellaktionen', 'geburtstage', 'absenzen'
    ]
}


def get_user_widget_config():
    """Widget-Konfiguration des aktuellen Benutzers laden"""
    if current_user.dashboard_config_json:
        try:
            return json.loads(current_user.dashboard_config_json)
        except (json.JSONDecodeError, TypeError):
            pass
    # Standard-Konfiguration fuer Rolle
    return DEFAULT_WIDGET_CONFIG.get(current_user.role, DEFAULT_WIDGET_CONFIG['therapist'])


@dashboard_bp.route('/')
@login_required
def index():
    widget_config = get_user_widget_config()
    return render_template('dashboard/index.html', widget_config=widget_config)


# === Dashboard API-Endpunkte ===

@dashboard_bp.route('/api/dashboard/stats', methods=['GET'])
@login_required
def dashboard_stats():
    """Alle Basiszahlen fuer die Dashboard-Widgets"""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today.replace(hour=23, minute=59, second=59)
    org_id = current_user.organization_id
    employee = Employee.query.filter_by(user_id=current_user.id).first()

    # Termine heute, Ersttermine, Patienten — eine einzige Aggregations-Query
    termine_base = db.session.query(
        func.count(Appointment.id).label('total'),
        func.count(case(
            (Appointment.appointment_type == 'initial', Appointment.id),
        )).label('ersttermine'),
        func.count(func.distinct(Appointment.patient_id)).label('patienten')
    ).join(
        Employee, Appointment.employee_id == Employee.id
    ).filter(
        Employee.organization_id == org_id,
        Appointment.start_time >= today,
        Appointment.start_time <= today_end,
        Appointment.status.in_(['scheduled', 'confirmed'])
    )
    if employee and current_user.role == 'therapist':
        termine_base = termine_base.filter(Appointment.employee_id == employee.id)

    stats_row = termine_base.one()
    termine_heute = stats_row.total
    ersttermine = stats_row.ersttermine
    patienten_heute = stats_row.patienten

    # Offene Aufgaben
    aufgaben_query = Task.query.filter(
        Task.organization_id == org_id,
        Task.status.in_(['open', 'in_progress'])
    )
    if current_user.role == 'therapist':
        aufgaben_query = aufgaben_query.filter(Task.assigned_to_id == current_user.id)
    offene_aufgaben = aufgaben_query.count()

    # Warteliste (ueber Patient filtern)
    try:
        from models import WaitingList
        warteliste = WaitingList.query.join(
            Patient, WaitingList.patient_id == Patient.id
        ).filter(
            Patient.organization_id == org_id,
            WaitingList.status == 'waiting'
        ).count()
    except Exception:
        warteliste = 0

    # Ungelesene E-Mails
    ungelesene_emails = Email.query.filter_by(
        organization_id=org_id,
        folder='inbox'
    ).filter(Email.read_at.is_(None)).count()

    # Ueberfaellige Rechnungen
    ueberfaellige = Invoice.query.filter(
        Invoice.organization_id == org_id,
        db.or_(
            Invoice.status == 'overdue',
            db.and_(
                Invoice.status.in_(['sent', 'partially_paid']),
                Invoice.due_date < date.today(),
                Invoice.amount_open > 0
            )
        )
    ).count()

    return jsonify({
        'termine_heute': termine_heute,
        'ersttermine': ersttermine,
        'patienten_heute': patienten_heute,
        'offene_aufgaben': offene_aufgaben,
        'warteliste': warteliste,
        'ungelesene_emails': ungelesene_emails,
        'ueberfaellige_rechnungen': ueberfaellige
    })


@dashboard_bp.route('/api/dashboard/termine-heute', methods=['GET'])
@login_required
def dashboard_termine_heute():
    """Heutige Termine fuer das Dashboard-Widget"""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today.replace(hour=23, minute=59, second=59)
    org_id = current_user.organization_id
    employee = Employee.query.filter_by(user_id=current_user.id).first()

    query = Appointment.query.options(
        joinedload(Appointment.patient),
        joinedload(Appointment.employee).joinedload(Employee.user),
        joinedload(Appointment.resource)
    ).join(
        Employee, Appointment.employee_id == Employee.id
    ).filter(
        Employee.organization_id == org_id,
        Appointment.start_time >= today,
        Appointment.start_time <= today_end,
        Appointment.status.in_(['scheduled', 'confirmed'])
    )
    if employee and current_user.role == 'therapist':
        query = query.filter(Appointment.employee_id == employee.id)

    termine = query.order_by(Appointment.start_time).limit(8).all()

    result = []
    for t in termine:
        emp = t.employee
        emp_user = emp.user if emp else None
        result.append({
            'id': t.id,
            'start_time': t.start_time.strftime('%H:%M'),
            'end_time': t.end_time.strftime('%H:%M'),
            'patient_name': f'{t.patient.first_name} {t.patient.last_name}',
            'patient_id': t.patient_id,
            'therapeut': f'{emp_user.first_name} {emp_user.last_name}' if emp_user else '-',
            'therapeut_farbe': emp.color_code if emp else '#4a90d9',
            'terminart': t.title or t.appointment_type or 'Behandlung',
            'raum': t.resource.name if t.resource else '-',
            'status': t.status
        })

    return jsonify({'termine': result})


@dashboard_bp.route('/api/dashboard/aufgaben', methods=['GET'])
@login_required
def dashboard_aufgaben():
    """Top offene Aufgaben fuer das Dashboard-Widget"""
    org_id = current_user.organization_id

    # Prioritaet-Sortierung: urgent > high > normal > low
    priority_order = case(
        (Task.priority == 'urgent', 1),
        (Task.priority == 'high', 2),
        (Task.priority == 'normal', 3),
        (Task.priority == 'low', 4),
        else_=5
    )

    query = Task.query.filter(
        Task.organization_id == org_id,
        Task.status.in_(['open', 'in_progress'])
    )
    if current_user.role == 'therapist':
        query = query.filter(Task.assigned_to_id == current_user.id)

    aufgaben = query.order_by(priority_order, Task.due_date.asc().nullslast()).limit(5).all()

    gesamt = query.count()

    result = []
    for a in aufgaben:
        result.append({
            'id': a.id,
            'title': a.title,
            'priority': a.priority,
            'status': a.status,
            'due_date': a.due_date.strftime('%d.%m.%Y') if a.due_date else None,
            'ueberfaellig': a.due_date < date.today() if a.due_date else False
        })

    return jsonify({'aufgaben': result, 'gesamt': gesamt})


@dashboard_bp.route('/api/dashboard/umsatz', methods=['GET'])
@login_required
def dashboard_umsatz():
    """Umsatzuebersicht: aktueller Monat + 6-Monate-Verlauf"""
    org_id = current_user.organization_id
    heute = date.today()
    erster_des_monats = heute.replace(day=1)

    # Aktueller Monat
    umsatz_aktuell = db.session.query(
        func.coalesce(func.sum(Invoice.amount_total), 0)
    ).filter(
        Invoice.organization_id == org_id,
        Invoice.status.in_(['sent', 'paid', 'partially_paid', 'overdue']),
        Invoice.created_at >= erster_des_monats
    ).scalar() or 0

    # Vormonat
    if erster_des_monats.month == 1:
        vormonat_start = erster_des_monats.replace(year=erster_des_monats.year - 1, month=12)
    else:
        vormonat_start = erster_des_monats.replace(month=erster_des_monats.month - 1)
    vormonat_end = erster_des_monats - timedelta(days=1)

    umsatz_vormonat = db.session.query(
        func.coalesce(func.sum(Invoice.amount_total), 0)
    ).filter(
        Invoice.organization_id == org_id,
        Invoice.status.in_(['sent', 'paid', 'partially_paid', 'overdue']),
        Invoice.created_at >= vormonat_start,
        Invoice.created_at <= datetime.combine(vormonat_end, time(23, 59, 59))
    ).scalar() or 0

    # Veraenderung in Prozent
    if umsatz_vormonat > 0:
        veraenderung = round(((umsatz_aktuell - umsatz_vormonat) / umsatz_vormonat) * 100, 1)
    else:
        veraenderung = 100.0 if umsatz_aktuell > 0 else 0

    # 6-Monate-Verlauf
    verlauf = []
    monate_namen = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun',
                    'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']
    for i in range(5, -1, -1):
        m_date = heute.replace(day=1)
        for _ in range(i):
            m_date = (m_date - timedelta(days=1)).replace(day=1)
        m_end = (m_date.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)

        betrag = db.session.query(
            func.coalesce(func.sum(Invoice.amount_total), 0)
        ).filter(
            Invoice.organization_id == org_id,
            Invoice.status.in_(['sent', 'paid', 'partially_paid', 'overdue']),
            Invoice.created_at >= m_date,
            Invoice.created_at <= datetime.combine(m_end, time(23, 59, 59))
        ).scalar() or 0

        verlauf.append({
            'monat': monate_namen[m_date.month - 1],
            'betrag': round(float(betrag), 2)
        })

    # Offene Posten
    offene_posten = db.session.query(
        func.coalesce(func.sum(Invoice.amount_open), 0)
    ).filter(
        Invoice.organization_id == org_id,
        Invoice.status.in_(['sent', 'partially_paid', 'overdue']),
        Invoice.amount_open > 0
    ).scalar() or 0

    return jsonify({
        'umsatz_aktuell': round(float(umsatz_aktuell), 2),
        'umsatz_vormonat': round(float(umsatz_vormonat), 2),
        'veraenderung': veraenderung,
        'verlauf': verlauf,
        'offene_posten': round(float(offene_posten), 2)
    })


@dashboard_bp.route('/api/dashboard/auslastung', methods=['GET'])
@login_required
def dashboard_auslastung():
    """Auslastung pro Therapeut heute in Prozent"""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today.replace(hour=23, minute=59, second=59)
    wochentag = today.weekday()  # 0=Montag

    therapeuten = Employee.query.options(
        joinedload(Employee.user),
        selectinload(Employee.work_schedules)
    ).filter_by(organization_id=current_user.organization_id, is_active=True).all()
    result = []

    for emp in therapeuten:
        emp_user = emp.user
        if not emp_user:
            continue

        # Arbeitszeit heute (aus vorgeladenen WorkSchedules filtern)
        arbeitszeit_minuten = 0
        for ws in emp.work_schedules:
            if ws.day_of_week != wochentag:
                continue
            start_dt = datetime.combine(date.today(), ws.start_time)
            end_dt = datetime.combine(date.today(), ws.end_time)
            arbeitszeit_minuten += (end_dt - start_dt).total_seconds() / 60

        if arbeitszeit_minuten == 0:
            continue  # kein Arbeitstag

        # Gebuchte Minuten
        gebuchte_minuten = db.session.query(
            func.coalesce(func.sum(Appointment.duration_minutes), 0)
        ).filter(
            Appointment.employee_id == emp.id,
            Appointment.start_time >= today,
            Appointment.start_time <= today_end,
            Appointment.status.in_(['scheduled', 'confirmed'])
        ).scalar() or 0

        prozent = round((gebuchte_minuten / arbeitszeit_minuten) * 100)

        result.append({
            'name': f'{emp_user.first_name} {emp_user.last_name}',
            'farbe': emp.color_code or '#4a90d9',
            'prozent': min(prozent, 100),
            'gebuchte_minuten': int(gebuchte_minuten),
            'arbeitszeit_minuten': int(arbeitszeit_minuten)
        })

    return jsonify({'auslastung': result})


@dashboard_bp.route('/api/dashboard/geburtstage', methods=['GET'])
@login_required
def dashboard_geburtstage():
    """Patienten-Geburtstage heute und naechste 7 Tage"""
    org_id = current_user.organization_id
    heute = date.today()
    result = []

    # Alle aktiven Patienten mit Geburtsdatum
    patienten = Patient.query.filter(
        Patient.organization_id == org_id,
        Patient.is_active == True,
        Patient.date_of_birth.isnot(None)
    ).all()

    for p in patienten:
        geb = p.date_of_birth
        # Geburtstag dieses Jahr
        try:
            geb_dieses_jahr = geb.replace(year=heute.year)
        except ValueError:
            # 29. Februar in Nicht-Schaltjahr
            geb_dieses_jahr = geb.replace(year=heute.year, day=28)

        diff = (geb_dieses_jahr - heute).days

        if -1 <= diff <= 7:
            alter = heute.year - geb.year
            if (heute.month, heute.day) < (geb.month, geb.day):
                alter -= 1

            result.append({
                'id': p.id,
                'name': f'{p.first_name} {p.last_name}',
                'datum': geb_dieses_jahr.strftime('%d.%m.'),
                'alter': alter + 1 if diff >= 0 else alter,
                'ist_heute': diff == 0,
                'tage_bis': diff
            })

    # Sortieren: heute zuerst, dann nach Tagen
    result.sort(key=lambda x: (not x['ist_heute'], x['tage_bis']))

    return jsonify({'geburtstage': result})


@dashboard_bp.route('/api/dashboard/absenzen', methods=['GET'])
@login_required
def dashboard_absenzen():
    """Absenzen heute und morgen"""
    heute = date.today()
    morgen = heute + timedelta(days=1)
    org_id = current_user.organization_id

    def get_absenzen(tag):
        absenzen = Absence.query.options(
            joinedload(Absence.employee).joinedload(Employee.user)
        ).join(
            Employee, Absence.employee_id == Employee.id
        ).filter(
            Employee.organization_id == org_id,
            Absence.start_date <= tag,
            Absence.end_date >= tag,
            Absence.status.in_(['approved', 'pending'])
        ).all()
        result = []
        for a in absenzen:
            emp = a.employee
            emp_user = emp.user if emp else None
            if emp_user:
                grund_map = {
                    'vacation': 'Ferien',
                    'sick': 'Krank',
                    'training': 'Weiterbildung',
                    'other': 'Abwesend',
                    'maternity': 'Mutterschaftsurlaub',
                    'paternity': 'Vaterschaftsurlaub',
                    'military': 'Militär',
                    'accident': 'Unfall'
                }
                result.append({
                    'name': f'{emp_user.first_name} {emp_user.last_name}',
                    'grund': grund_map.get(a.absence_type, a.absence_type or 'Abwesend'),
                    'halbtags': a.half_day
                })
        return result

    absenzen_heute = get_absenzen(heute)
    absenzen_morgen = get_absenzen(morgen)

    return jsonify({
        'heute': absenzen_heute,
        'morgen': absenzen_morgen
    })


@dashboard_bp.route('/api/dashboard/patientenverlauf', methods=['GET'])
@login_required
def dashboard_patientenverlauf():
    """Letzte 5 besuchte/bearbeitete Patienten"""
    employee = Employee.query.filter_by(user_id=current_user.id).first()

    # Letzte Termine des Benutzers (absteigend, Multi-Tenancy)
    query = Appointment.query.options(
        joinedload(Appointment.patient)
    ).join(
        Employee, Appointment.employee_id == Employee.id
    ).filter(
        Employee.organization_id == current_user.organization_id,
        Appointment.start_time <= datetime.now(),
        Appointment.status.in_(['completed', 'confirmed', 'scheduled'])
    )
    if employee:
        query = query.filter(Appointment.employee_id == employee.id)

    letzte_termine = query.order_by(Appointment.start_time.desc()).limit(20).all()

    # Eindeutige Patienten extrahieren
    gesehene_patienten = set()
    result = []
    for t in letzte_termine:
        if t.patient_id not in gesehene_patienten and len(result) < 5:
            gesehene_patienten.add(t.patient_id)
            result.append({
                'id': t.patient_id,
                'name': f'{t.patient.first_name} {t.patient.last_name}',
                'letzte_aktion': t.title or t.appointment_type or 'Behandlung',
                'datum': t.start_time.strftime('%d.%m.%Y')
            })

    return jsonify({'patienten': result})


@dashboard_bp.route('/api/dashboard/offene-rechnungen', methods=['GET'])
@login_required
def dashboard_offene_rechnungen():
    """Offene und ueberfaellige Rechnungen"""
    org_id = current_user.organization_id
    heute = date.today()

    # Offene: count + sum in einer Query
    offen_row = db.session.query(
        func.count(Invoice.id),
        func.coalesce(func.sum(Invoice.amount_open), 0)
    ).filter(
        Invoice.organization_id == org_id,
        Invoice.status.in_(['sent', 'partially_paid']),
        Invoice.amount_open > 0
    ).one()
    anzahl_offen = offen_row[0]
    betrag_offen = offen_row[1]

    # Ueberfaellige: count + sum in einer Query
    ueberfaellig_filter = db.or_(
        Invoice.status == 'overdue',
        db.and_(
            Invoice.status.in_(['sent', 'partially_paid']),
            Invoice.due_date < heute,
            Invoice.amount_open > 0
        )
    )
    ueberfaellig_row = db.session.query(
        func.count(Invoice.id),
        func.coalesce(func.sum(Invoice.amount_open), 0)
    ).filter(
        Invoice.organization_id == org_id,
        ueberfaellig_filter
    ).one()
    anzahl_ueberfaellig = ueberfaellig_row[0]
    betrag_ueberfaellig = ueberfaellig_row[1]

    return jsonify({
        'anzahl_offen': anzahl_offen,
        'betrag_offen': round(float(betrag_offen), 2),
        'anzahl_ueberfaellig': anzahl_ueberfaellig,
        'betrag_ueberfaellig': round(float(betrag_ueberfaellig), 2)
    })


@dashboard_bp.route('/api/dashboard/ungelesene-emails', methods=['GET'])
@login_required
def dashboard_ungelesene_emails():
    """Ungelesene E-Mails fuer Dashboard-Widget"""
    org_id = current_user.organization_id

    anzahl = Email.query.filter_by(
        organization_id=org_id,
        folder='inbox'
    ).filter(Email.read_at.is_(None)).count()

    letzte = Email.query.filter_by(
        organization_id=org_id,
        folder='inbox'
    ).filter(Email.read_at.is_(None)).order_by(
        Email.created_at.desc()
    ).limit(3).all()

    emails = []
    for e in letzte:
        emails.append({
            'id': e.id,
            'absender': e.from_address or '-',
            'betreff': e.subject or '(Kein Betreff)',
            'kurztext': (e.body_text or '')[:80] + ('...' if e.body_text and len(e.body_text) > 80 else ''),
            'datum': e.created_at.strftime('%d.%m. %H:%M') if e.created_at else ''
        })

    return jsonify({'anzahl': anzahl, 'emails': emails})


@dashboard_bp.route('/api/dashboard/ki-tagesuebersicht', methods=['GET'])
@login_required
def dashboard_ki_tagesuebersicht():
    """KI-generierte Tageszusammenfassung (statisch generiert ohne API-Call)"""
    org_id = current_user.organization_id
    heute = date.today()
    today_start = datetime.combine(heute, time(0, 0))
    today_end = datetime.combine(heute, time(23, 59, 59))
    employee = Employee.query.filter_by(user_id=current_user.id).first()

    # Daten sammeln — Termine + Ersttermine in einer Query
    ki_termine_base = db.session.query(
        func.count(Appointment.id).label('total'),
        func.count(case(
            (Appointment.appointment_type == 'initial', Appointment.id),
        )).label('ersttermine')
    ).join(
        Employee, Appointment.employee_id == Employee.id
    ).filter(
        Employee.organization_id == org_id,
        Appointment.start_time >= today_start,
        Appointment.start_time <= today_end,
        Appointment.status.in_(['scheduled', 'confirmed'])
    )
    if employee and current_user.role == 'therapist':
        ki_termine_base = ki_termine_base.filter(Appointment.employee_id == employee.id)

    ki_stats = ki_termine_base.one()
    termine_heute = ki_stats.total
    ersttermine = ki_stats.ersttermine

    # Warteliste (ueber Patient filtern)
    try:
        from models import WaitingList
        warteliste = WaitingList.query.join(
            Patient, WaitingList.patient_id == Patient.id
        ).filter(
            Patient.organization_id == org_id,
            WaitingList.status == 'waiting'
        ).count()
    except Exception:
        warteliste = 0

    # Offene Aufgaben
    aufgaben_query = Task.query.filter(
        Task.organization_id == org_id,
        Task.status.in_(['open', 'in_progress'])
    )
    if current_user.role == 'therapist':
        aufgaben_query = aufgaben_query.filter(Task.assigned_to_id == current_user.id)
    offene_aufgaben = aufgaben_query.count()

    # Ueberfaellige Rechnungen
    ueberfaellige = Invoice.query.filter(
        Invoice.organization_id == org_id,
        db.or_(
            Invoice.status == 'overdue',
            db.and_(
                Invoice.status.in_(['sent', 'partially_paid']),
                Invoice.due_date < heute,
                Invoice.amount_open > 0
            )
        )
    ).count()

    # Absenzen morgen (nur eigene Organisation) — joinedload statt N+1
    morgen = heute + timedelta(days=1)
    absenzen_morgen = Absence.query.options(
        joinedload(Absence.employee).joinedload(Employee.user)
    ).join(
        Employee, Absence.employee_id == Employee.id
    ).filter(
        Employee.organization_id == org_id,
        Absence.start_date <= morgen,
        Absence.end_date >= morgen,
        Absence.status.in_(['approved', 'pending'])
    ).all()

    # Zusammenfassung bauen
    zusammenfassung = f'Heute: {termine_heute} Termine'
    if ersttermine > 0:
        zusammenfassung += f', davon {ersttermine} Ersttermine'
    zusammenfassung += '.'

    if warteliste > 0:
        zusammenfassung += f' {warteliste} Patienten auf der Warteliste.'
    if offene_aufgaben > 0:
        zusammenfassung += f' {offene_aufgaben} offene Aufgaben.'

    hinweise = []
    if ueberfaellige > 0:
        hinweise.append(f'Achtung: {ueberfaellige} Rechnungen überfällig')

    for a in absenzen_morgen:
        emp = a.employee
        emp_user = emp.user if emp else None
        if emp_user:
            hinweise.append(f'{emp_user.first_name} ist morgen abwesend')

    return jsonify({
        'zusammenfassung': zusammenfassung,
        'hinweise': hinweise
    })


@dashboard_bp.route('/api/dashboard/config', methods=['POST'])
@login_required
def dashboard_config_save():
    """Widget-Konfiguration speichern"""
    data = request.get_json()
    widgets = data.get('widgets', [])

    current_user.dashboard_config_json = json.dumps(widgets)
    db.session.commit()

    return jsonify({'status': 'ok'})


@dashboard_bp.route('/api/dashboard/config', methods=['GET'])
@login_required
def dashboard_config_get():
    """Widget-Konfiguration laden"""
    config = get_user_widget_config()
    return jsonify({
        'widgets': config,
        'available': [
            {'id': 'ki_tagesuebersicht', 'name': 'KI-Tagesübersicht', 'icon': 'brain'},
            {'id': 'heutige_termine', 'name': 'Heutige Termine', 'icon': 'calendar'},
            {'id': 'offene_aufgaben', 'name': 'Offene Aufgaben', 'icon': 'tasks'},
            {'id': 'patientenverlauf', 'name': 'Patientenverlauf', 'icon': 'history'},
            {'id': 'umsatzuebersicht', 'name': 'Umsatzübersicht', 'icon': 'chart'},
            {'id': 'geburtstage', 'name': 'Geburtstage', 'icon': 'cake'},
            {'id': 'schnellaktionen', 'name': 'Schnellaktionen', 'icon': 'bolt'},
            {'id': 'auslastung', 'name': 'Auslastung', 'icon': 'gauge'},
            {'id': 'offene_rechnungen', 'name': 'Offene Rechnungen', 'icon': 'invoice'},
            {'id': 'ungelesene_emails', 'name': 'Ungelesene E-Mails', 'icon': 'mail'},
            {'id': 'absenzen', 'name': 'Absenzen', 'icon': 'absence'},
        ]
    })


# === Chat API (bestehend) ===

@dashboard_bp.route('/api/chat', methods=['POST'])
@limiter.limit("20 per hour")
@login_required
def chat():
    data = request.get_json()
    message = data.get('message', '').strip()

    if not message:
        return jsonify({'error': 'Nachricht darf nicht leer sein.'}), 400

    # Benutzer-Nachricht speichern
    user_msg = ChatMessage(
        user_id=current_user.id,
        role='user',
        content=message
    )
    db.session.add(user_msg)
    db.session.commit()

    # KI-Antwort generieren
    coordinator = Coordinator()
    try:
        response_text = coordinator.process(message, current_user)
    except Exception as e:
        response_text = f'Es ist ein Fehler aufgetreten. Bitte versuchen Sie es erneut.'

    # KI-Antwort speichern
    ai_msg = ChatMessage(
        user_id=current_user.id,
        role='assistant',
        content=response_text
    )
    db.session.add(ai_msg)
    db.session.commit()

    return jsonify({
        'response': response_text,
        'timestamp': ai_msg.created_at.strftime('%H:%M')
    })


@dashboard_bp.route('/api/chat/history', methods=['GET'])
@login_required
def chat_history():
    messages = ChatMessage.query.filter_by(
        user_id=current_user.id
    ).order_by(ChatMessage.created_at.asc()).limit(100).all()

    return jsonify({
        'messages': [{
            'role': msg.role,
            'content': msg.content,
            'timestamp': msg.created_at.strftime('%H:%M')
        } for msg in messages]
    })


@dashboard_bp.route('/api/chat/clear', methods=['POST'])
@login_required
def chat_clear():
    ChatMessage.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    return jsonify({'status': 'ok'})


@dashboard_bp.route('/api/search', methods=['GET'])
@login_required
def global_search():
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify({'results': []})

    results = []

    # Patienten suchen
    patients = Patient.query.filter(
        db.or_(
            Patient.first_name.ilike(f'%{q}%'),
            Patient.last_name.ilike(f'%{q}%'),
            Patient.patient_number.ilike(f'%{q}%'),
            (Patient.first_name + ' ' + Patient.last_name).ilike(f'%{q}%')
        ),
        Patient.is_active == True,
        Patient.organization_id == current_user.organization_id
    ).limit(5).all()

    for p in patients:
        results.append({
            'type': 'patient',
            'label': f'{p.first_name} {p.last_name}',
            'sublabel': f'Pat.-Nr. {p.patient_number}',
            'url': '#',
            'icon': 'person'
        })

    # Mitarbeiter suchen
    from models import User as UserModel
    employees = UserModel.query.filter(
        db.or_(
            UserModel.first_name.ilike(f'%{q}%'),
            UserModel.last_name.ilike(f'%{q}%')
        ),
        UserModel.is_active == True,
        UserModel.organization_id == current_user.organization_id
    ).limit(3).all()

    for e in employees:
        results.append({
            'type': 'employee',
            'label': f'{e.first_name} {e.last_name}',
            'sublabel': e.role,
            'url': '#',
            'icon': 'badge'
        })

    return jsonify({'results': results})
