# OMNIA Praxissoftware - App Factory
# Hauptdatei: Erstellt und konfiguriert die Flask-Anwendung

import os
from datetime import datetime, date, time, timedelta
from flask import Flask, redirect, url_for
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from config import Config
from models import db

login_manager = LoginManager()
csrf = CSRFProtect()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Erweiterungen initialisieren
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Bitte melde dich an.'
    login_manager.login_message_category = 'warning'
    csrf.init_app(app)

    # CSRF für API-Endpunkte deaktivieren
    @app.before_request
    def csrf_exempt_api():
        from flask import request
        if request.path.startswith('/api/'):
            csrf._exempt_views.add(request.endpoint)

    # User-Loader für Flask-Login
    @login_manager.user_loader
    def load_user(user_id):
        from models import User
        return User.query.get(int(user_id))

    # Blueprints registrieren
    from blueprints.auth import auth_bp
    from blueprints.dashboard import dashboard_bp
    from blueprints.patients import patients_bp
    from blueprints.calendar import calendar_bp
    from blueprints.employees import employees_bp
    from blueprints.treatment import treatment_bp
    from blueprints.resources import resources_bp
    from blueprints.billing import billing_bp
    from blueprints.cost_approvals import cost_approvals_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(patients_bp, url_prefix='/patients')
    app.register_blueprint(calendar_bp, url_prefix='/calendar')
    app.register_blueprint(employees_bp, url_prefix='/employees')
    app.register_blueprint(treatment_bp, url_prefix='/treatment')
    app.register_blueprint(resources_bp, url_prefix='/resources')
    app.register_blueprint(billing_bp, url_prefix='/billing')
    app.register_blueprint(cost_approvals_bp, url_prefix='/cost-approvals')

    # API-Routen umleiten (Dashboard-Chat-API global verfügbar machen)
    @app.route('/api/chat', methods=['POST'])
    def api_chat():
        from blueprints.dashboard.routes import chat
        return chat()

    @app.route('/api/chat/history')
    def api_chat_history():
        from blueprints.dashboard.routes import chat_history
        return chat_history()

    @app.route('/api/chat/clear', methods=['POST'])
    def api_chat_clear():
        from blueprints.dashboard.routes import chat_clear
        return chat_clear()

    @app.route('/api/calendar/appointments')
    def api_calendar_appointments():
        from blueprints.calendar.routes import api_appointments
        return api_appointments()

    @app.route('/api/calendar/appointments', methods=['POST'])
    def api_calendar_create():
        from blueprints.calendar.routes import api_create_appointment
        return api_create_appointment()

    @app.route('/api/calendar/appointments/<int:id>', methods=['PUT'])
    def api_calendar_update(id):
        from blueprints.calendar.routes import api_update_appointment
        return api_update_appointment(id)

    @app.route('/api/calendar/appointments/<int:id>', methods=['DELETE'])
    def api_calendar_delete(id):
        from blueprints.calendar.routes import api_delete_appointment
        return api_delete_appointment(id)

    # Wurzel-Route
    @app.route('/')
    def index():
        return redirect(url_for('dashboard.index'))

    # Template-Hilfsfunktionen für den Kalender
    @app.context_processor
    def utility_functions():
        return {
            'import_timedelta': lambda **kwargs: timedelta(**kwargs),
            'import_date_today': date.today,
        }

    # Datenbank erstellen und Demo-Daten laden
    with app.app_context():
        db.create_all()
        _seed_demo_data_if_needed()

    return app


def _seed_demo_data_if_needed():
    """Erstellt Demo-Daten beim ersten Start."""
    from models import (Organization, Location, User, Employee, WorkSchedule,
                        Patient, Appointment, Resource, InsuranceProvider,
                        Doctor, TreatmentSeriesTemplate, TreatmentSeries,
                        TreatmentGoal, TreatmentMeasurement,
                        Invoice, InvoiceItem, Payment, CostApproval,
                        TaxPointValue, DunningConfig)

    # Prüfen ob bereits Daten vorhanden
    if Organization.query.first():
        return

    print('Erstelle Demo-Daten...')

    # === Organisation ===
    org = Organization(
        name='OMNIA Health Services AG',
        address='Bahnhofstrasse 42, 8001 Zürich',
        phone='+41 44 123 45 67',
        email='info@omnia-health.ch',
        zsr_number='H121234',
        gln_number='7601000000001',
    )
    db.session.add(org)
    db.session.flush()

    # === Standorte ===
    loc_zh = Location(
        organization_id=org.id,
        name='Zürich Zentrum',
        address='Bahnhofstrasse 42, 8001 Zürich',
        phone='+41 44 123 45 67',
        opening_hours_json={
            '0': {'open': '07:30', 'close': '18:30'},
            '1': {'open': '07:30', 'close': '18:30'},
            '2': {'open': '07:30', 'close': '18:30'},
            '3': {'open': '07:30', 'close': '18:30'},
            '4': {'open': '07:30', 'close': '17:00'},
        }
    )
    loc_wt = Location(
        organization_id=org.id,
        name='Winterthur',
        address='Marktgasse 15, 8400 Winterthur',
        phone='+41 52 234 56 78',
        opening_hours_json={
            '0': {'open': '08:00', 'close': '17:00'},
            '1': {'open': '08:00', 'close': '17:00'},
            '2': {'open': '08:00', 'close': '17:00'},
            '3': {'open': '08:00', 'close': '17:00'},
            '4': {'open': '08:00', 'close': '16:00'},
        }
    )
    db.session.add_all([loc_zh, loc_wt])
    db.session.flush()

    # === Ressourcen (3 Räume pro Standort + 2 Geräte) ===
    res_zh1 = Resource(location_id=loc_zh.id, name='Behandlungsraum 1', type='room')
    res_zh2 = Resource(location_id=loc_zh.id, name='Behandlungsraum 2', type='room')
    res_zh3 = Resource(location_id=loc_zh.id, name='Behandlungsraum 3', type='room')
    res_wt1 = Resource(location_id=loc_wt.id, name='Behandlungsraum 1', type='room')
    res_wt2 = Resource(location_id=loc_wt.id, name='Behandlungsraum 2', type='room')
    res_wt3 = Resource(location_id=loc_wt.id, name='Behandlungsraum 3', type='room')
    res_emr1 = Resource(location_id=loc_zh.id, name='Ultraschallgerät', type='equipment')
    res_emr2 = Resource(location_id=loc_zh.id, name='Elektrotherapiegerät', type='equipment')
    db.session.add_all([res_zh1, res_zh2, res_zh3, res_wt1, res_wt2, res_wt3, res_emr1, res_emr2])

    # === Versicherungen ===
    ins_css = InsuranceProvider(name='CSS Versicherung', gln_number='7601003000015', supports_electronic_billing=True)
    ins_swica = InsuranceProvider(name='Swica', gln_number='7601003000022', supports_electronic_billing=True)
    ins_helsana = InsuranceProvider(name='Helsana', gln_number='7601003000039', supports_electronic_billing=True)
    ins_suva = InsuranceProvider(name='Suva', gln_number='7601003000046', supports_electronic_billing=True)
    db.session.add_all([ins_css, ins_swica, ins_helsana, ins_suva])
    db.session.flush()

    # === Ärzte ===
    dr_mueller = Doctor(name='Dr. med. Peter Müller', specialty='Allgemeinmedizin', gln_number='7601000000501', zsr_number='A123456')
    dr_schmidt = Doctor(name='Dr. med. Eva Schmidt', specialty='Orthopädie', gln_number='7601000000502', zsr_number='A234567')
    dr_weber = Doctor(name='Dr. med. Hans Weber', specialty='Rheumatologie', gln_number='7601000000503', zsr_number='A345678')
    db.session.add_all([dr_mueller, dr_schmidt, dr_weber])
    db.session.flush()

    # === Benutzer & Mitarbeiter ===
    # Admin
    admin_user = User(username='admin', name='Admin', email='admin@omnia-health.ch', role='admin')
    admin_user.set_password('admin')
    db.session.add(admin_user)
    db.session.flush()
    admin_emp = Employee(
        user_id=admin_user.id, organization_id=org.id,
        pensum_percent=100, color_code='#6c757d',
    )
    db.session.add(admin_emp)

    # Therapeut 1: Thomas
    thomas_user = User(username='thomas', name='Thomas Meier', email='thomas@omnia-health.ch', role='therapist')
    thomas_user.set_password('thomas')
    db.session.add(thomas_user)
    db.session.flush()
    thomas_emp = Employee(
        user_id=thomas_user.id, organization_id=org.id,
        qualifications=['Physiotherapie', 'Manuelle Therapie', 'Sportphysiotherapie'],
        pensum_percent=100, color_code='#4a90d9',
        zsr_number='T123456', gln_number='7601000000101',
    )
    db.session.add(thomas_emp)
    db.session.flush()

    # Arbeitszeiten Thomas (Mo-Fr 08:00-12:00, 13:00-17:00)
    for day in range(5):
        db.session.add(WorkSchedule(
            employee_id=thomas_emp.id, location_id=loc_zh.id,
            day_of_week=day, start_time=time(8, 0), end_time=time(12, 0), work_type='working'
        ))
        db.session.add(WorkSchedule(
            employee_id=thomas_emp.id, location_id=loc_zh.id,
            day_of_week=day, start_time=time(12, 0), end_time=time(13, 0), work_type='break'
        ))
        db.session.add(WorkSchedule(
            employee_id=thomas_emp.id, location_id=loc_zh.id,
            day_of_week=day, start_time=time(13, 0), end_time=time(17, 0), work_type='working'
        ))

    # Therapeutin 2: Sarah
    sarah_user = User(username='sarah', name='Sarah Brunner', email='sarah@omnia-health.ch', role='therapist')
    sarah_user.set_password('sarah')
    db.session.add(sarah_user)
    db.session.flush()
    sarah_emp = Employee(
        user_id=sarah_user.id, organization_id=org.id,
        qualifications=['Physiotherapie', 'Lymphdrainage', 'Beckenboden'],
        pensum_percent=80, color_code='#e74c3c',
        zsr_number='T234567', gln_number='7601000000201',
    )
    db.session.add(sarah_emp)
    db.session.flush()

    # Arbeitszeiten Sarah (Mo-Do 08:00-16:00)
    for day in range(4):
        db.session.add(WorkSchedule(
            employee_id=sarah_emp.id, location_id=loc_zh.id,
            day_of_week=day, start_time=time(8, 0), end_time=time(12, 0), work_type='working'
        ))
        db.session.add(WorkSchedule(
            employee_id=sarah_emp.id, location_id=loc_zh.id,
            day_of_week=day, start_time=time(12, 0), end_time=time(13, 0), work_type='break'
        ))
        db.session.add(WorkSchedule(
            employee_id=sarah_emp.id, location_id=loc_zh.id,
            day_of_week=day, start_time=time(13, 0), end_time=time(16, 0), work_type='working'
        ))

    # Therapeut 3: Marco (Winterthur)
    marco_user = User(username='marco', name='Marco Keller', email='marco@omnia-health.ch', role='therapist')
    marco_user.set_password('marco')
    db.session.add(marco_user)
    db.session.flush()
    marco_emp = Employee(
        user_id=marco_user.id, organization_id=org.id,
        qualifications=['Physiotherapie', 'Triggerpunkt-Therapie'],
        pensum_percent=100, color_code='#27ae60',
        zsr_number='T345678', gln_number='7601000000301',
    )
    db.session.add(marco_emp)
    db.session.flush()

    # Arbeitszeiten Marco (Mo-Fr 08:00-17:00, Winterthur)
    for day in range(5):
        db.session.add(WorkSchedule(
            employee_id=marco_emp.id, location_id=loc_wt.id,
            day_of_week=day, start_time=time(8, 0), end_time=time(12, 0), work_type='working'
        ))
        db.session.add(WorkSchedule(
            employee_id=marco_emp.id, location_id=loc_wt.id,
            day_of_week=day, start_time=time(12, 0), end_time=time(13, 0), work_type='break'
        ))
        db.session.add(WorkSchedule(
            employee_id=marco_emp.id, location_id=loc_wt.id,
            day_of_week=day, start_time=time(13, 0), end_time=time(17, 0), work_type='working'
        ))

    # Empfang: Lisa
    lisa_user = User(username='lisa', name='Lisa Weber', email='lisa@omnia-health.ch', role='reception')
    lisa_user.set_password('lisa')
    db.session.add(lisa_user)
    db.session.flush()
    lisa_emp = Employee(
        user_id=lisa_user.id, organization_id=org.id,
        pensum_percent=100, color_code='#9b59b6',
    )
    db.session.add(lisa_emp)

    db.session.flush()

    # === Patienten (10 Schweizer Patienten) ===
    patienten_daten = [
        ('Anna', 'Müller', date(1985, 3, 15), 'f', '+41 44 111 22 33', '+41 79 111 22 33', 'anna.mueller@bluewin.ch', 'Seestrasse 12, 8002 Zürich', ins_css.id, '756.1234.5678.01'),
        ('Peter', 'Schmid', date(1972, 8, 22), 'm', '+41 44 222 33 44', '+41 78 222 33 44', 'peter.schmid@gmail.com', 'Limmatquai 78, 8001 Zürich', ins_swica.id, '756.2345.6789.02'),
        ('Maria', 'Bianchi', date(1990, 11, 5), 'f', '+41 44 333 44 55', '+41 76 333 44 55', 'maria.bianchi@outlook.com', 'Langstrasse 45, 8004 Zürich', ins_helsana.id, '756.3456.7890.03'),
        ('Hans', 'Keller', date(1960, 1, 30), 'm', '+41 44 444 55 66', None, None, 'Rämistrasse 101, 8006 Zürich', ins_css.id, '756.4567.8901.04'),
        ('Sandra', 'Fischer', date(1988, 6, 18), 'f', None, '+41 79 555 66 77', 'sandra.fischer@gmx.ch', 'Birmensdorferstrasse 200, 8003 Zürich', ins_swica.id, '756.5678.9012.05'),
        ('Markus', 'Huber', date(1975, 4, 10), 'm', '+41 52 666 77 88', '+41 78 666 77 88', 'markus.huber@sunrise.ch', 'Stadthausstrasse 30, 8400 Winterthur', ins_helsana.id, '756.6789.0123.06'),
        ('Erika', 'Wyss', date(1955, 12, 25), 'f', '+41 52 777 88 99', None, None, 'Marktgasse 55, 8400 Winterthur', ins_css.id, '756.7890.1234.07'),
        ('Daniel', 'Steiner', date(1995, 9, 3), 'm', None, '+41 76 888 99 00', 'daniel.steiner@icloud.com', 'Forchstrasse 88, 8008 Zürich', ins_suva.id, '756.8901.2345.08'),
        ('Claudia', 'Baumann', date(1982, 7, 14), 'f', '+41 44 999 00 11', '+41 79 999 00 11', 'claudia.baumann@bluewin.ch', 'Talstrasse 22, 8001 Zürich', ins_swica.id, '756.9012.3456.09'),
        ('René', 'Gerber', date(1968, 2, 28), 'm', '+41 44 100 20 30', None, 'rene.gerber@hispeed.ch', 'Kasernenstrasse 10, 8004 Zürich', ins_helsana.id, '756.0123.4567.10'),
    ]

    patienten = []
    for vorname, nachname, geb, geschlecht, tel, mobile, email, adresse, ins_id, ahv in patienten_daten:
        p = Patient(
            organization_id=org.id,
            first_name=vorname,
            last_name=nachname,
            date_of_birth=geb,
            gender=geschlecht,
            phone=tel,
            mobile=mobile,
            email=email,
            address=adresse,
            insurance_provider_id=ins_id,
            ahv_number=ahv,
        )
        db.session.add(p)
        patienten.append(p)

    db.session.flush()

    # === Behandlungsserien-Templates (3 Demo-Templates) ===
    tpl_physio = TreatmentSeriesTemplate(
        organization_id=org.id,
        name='Physiotherapie KVG Standard',
        tariff_type='311',
        num_appointments=9,
        duration_minutes=30,
        min_interval_days=2,
        requires_resource=True,
    )
    tpl_ergo = TreatmentSeriesTemplate(
        organization_id=org.id,
        name='Ergotherapie Standard',
        tariff_type='338',
        num_appointments=9,
        duration_minutes=45,
        min_interval_days=3,
        requires_resource=True,
    )
    tpl_emr = TreatmentSeriesTemplate(
        organization_id=org.id,
        name='EMR Komplementärmedizin',
        tariff_type='590',
        num_appointments=6,
        duration_minutes=60,
        min_interval_days=7,
        requires_resource=False,
    )
    db.session.add_all([tpl_physio, tpl_ergo, tpl_emr])
    db.session.flush()

    # === Termine (20 Termine über die nächsten 2 Wochen) ===
    heute = date.today()
    naechster_montag = heute + timedelta(days=(7 - heute.weekday()) % 7)
    if naechster_montag == heute and heute.weekday() == 0:
        naechster_montag = heute

    termin_daten = [
        # Woche 1
        (patienten[0], thomas_emp, naechster_montag, time(8, 0), 30),
        (patienten[1], thomas_emp, naechster_montag, time(9, 0), 45),
        (patienten[2], sarah_emp, naechster_montag, time(8, 30), 30),
        (patienten[3], thomas_emp, naechster_montag, time(10, 0), 30),
        (patienten[4], sarah_emp, naechster_montag, time(10, 0), 30),
        (patienten[5], marco_emp, naechster_montag, time(9, 0), 45),
        (patienten[0], thomas_emp, naechster_montag + timedelta(days=1), time(8, 0), 30),
        (patienten[6], marco_emp, naechster_montag + timedelta(days=1), time(10, 0), 30),
        (patienten[7], sarah_emp, naechster_montag + timedelta(days=2), time(9, 0), 30),
        (patienten[8], thomas_emp, naechster_montag + timedelta(days=2), time(14, 0), 45),
        (patienten[9], thomas_emp, naechster_montag + timedelta(days=3), time(8, 0), 30),
        (patienten[1], sarah_emp, naechster_montag + timedelta(days=3), time(14, 0), 30),
        (patienten[3], marco_emp, naechster_montag + timedelta(days=4), time(8, 0), 30),
        # Woche 2
        (patienten[2], thomas_emp, naechster_montag + timedelta(days=7), time(9, 0), 30),
        (patienten[4], sarah_emp, naechster_montag + timedelta(days=7), time(11, 0), 30),
        (patienten[5], marco_emp, naechster_montag + timedelta(days=8), time(9, 0), 45),
        (patienten[6], thomas_emp, naechster_montag + timedelta(days=8), time(15, 0), 30),
        (patienten[7], sarah_emp, naechster_montag + timedelta(days=9), time(8, 0), 30),
        (patienten[8], marco_emp, naechster_montag + timedelta(days=9), time(14, 0), 30),
        (patienten[9], thomas_emp, naechster_montag + timedelta(days=10), time(10, 0), 45),
    ]

    alle_termine = []
    for patient, therapeut, datum, uhrzeit, dauer in termin_daten:
        start_dt = datetime.combine(datum, uhrzeit)
        end_dt = start_dt + timedelta(minutes=dauer)
        termin = Appointment(
            patient_id=patient.id,
            employee_id=therapeut.id,
            location_id=therapeut.work_schedules.first().location_id if therapeut.work_schedules.first() else loc_zh.id,
            start_time=start_dt,
            end_time=end_dt,
            status='scheduled',
            type='treatment',
        )
        db.session.add(termin)
        alle_termine.append(termin)

    db.session.flush()

    # === Behandlungsserien (5 Demo-Serien) ===
    # Serie 1: Anna Müller - Physio bei Thomas (aktiv, 3 von 9 Terminen)
    serie1 = TreatmentSeries(
        patient_id=patienten[0].id,
        template_id=tpl_physio.id,
        therapist_id=thomas_emp.id,
        prescribing_doctor_id=dr_schmidt.id,
        diagnosis='Lumbalgie, chronische Rückenschmerzen',
        prescription_date=date.today() - timedelta(days=14),
        prescription_type='initial',
        status='active',
        insurance_type='KVG',
        billing_model='tiers_garant',
        healing_phase='treatment',
    )
    db.session.add(serie1)
    db.session.flush()

    # Termine der Serie 1 zuweisen (die ersten 2 Anna-Termine)
    for t in alle_termine:
        if t.patient_id == patienten[0].id and t.employee_id == thomas_emp.id:
            t.series_id = serie1.id

    # Ziele für Serie 1
    ziel1 = TreatmentGoal(
        series_id=serie1.id, title='Schmerzreduktion auf VAS 3',
        target_value='VAS 3', current_value='VAS 7', phase='treatment',
    )
    ziel2 = TreatmentGoal(
        series_id=serie1.id, title='Rumpfstabilität verbessern',
        description='Core-Muskulatur aufbauen für Alltagsbelastung',
        target_value='30s Plank', current_value='10s Plank', phase='treatment',
    )
    db.session.add_all([ziel1, ziel2])

    # Serie 2: Peter Schmid - Physio bei Thomas (aktiv)
    serie2 = TreatmentSeries(
        patient_id=patienten[1].id,
        template_id=tpl_physio.id,
        therapist_id=thomas_emp.id,
        prescribing_doctor_id=dr_mueller.id,
        diagnosis='Gonarthrose rechts',
        prescription_date=date.today() - timedelta(days=7),
        prescription_type='initial',
        status='active',
        insurance_type='KVG',
        billing_model='tiers_garant',
        healing_phase='initial',
    )
    db.session.add(serie2)
    db.session.flush()

    for t in alle_termine:
        if t.patient_id == patienten[1].id:
            t.series_id = serie2.id

    # Serie 3: Markus Huber - Physio bei Marco (aktiv)
    serie3 = TreatmentSeries(
        patient_id=patienten[5].id,
        template_id=tpl_physio.id,
        therapist_id=marco_emp.id,
        prescribing_doctor_id=dr_schmidt.id,
        diagnosis='Schulterimpingement links',
        prescription_date=date.today() - timedelta(days=21),
        prescription_type='initial',
        status='active',
        insurance_type='UVG',
        billing_model='tiers_payant',
        healing_phase='treatment',
    )
    db.session.add(serie3)
    db.session.flush()

    for t in alle_termine:
        if t.patient_id == patienten[5].id:
            t.series_id = serie3.id

    # Serie 4: Daniel Steiner - UVG bei Sarah (aktiv)
    serie4 = TreatmentSeries(
        patient_id=patienten[7].id,
        template_id=tpl_physio.id,
        therapist_id=sarah_emp.id,
        prescribing_doctor_id=dr_weber.id,
        diagnosis='Distorsion OSG rechts (Sportunfall)',
        prescription_date=date.today() - timedelta(days=5),
        prescription_type='initial',
        status='active',
        insurance_type='UVG',
        billing_model='tiers_payant',
        healing_phase='initial',
    )
    db.session.add(serie4)
    db.session.flush()

    for t in alle_termine:
        if t.patient_id == patienten[7].id:
            t.series_id = serie4.id

    # Serie 5: René Gerber - EMR (abgeschlossen)
    serie5 = TreatmentSeries(
        patient_id=patienten[9].id,
        template_id=tpl_emr.id,
        therapist_id=thomas_emp.id,
        diagnosis='Spannungskopfschmerzen',
        prescription_date=date.today() - timedelta(days=60),
        prescription_type='initial',
        status='completed',
        insurance_type='private',
        billing_model='tiers_garant',
        healing_phase='autonomy',
    )
    db.session.add(serie5)
    db.session.flush()

    # Messungen für Serie 1
    messung1 = TreatmentMeasurement(
        series_id=serie1.id, measurement_type='single',
        label='Schmerzskala VAS', value='7', unit='VAS 0-10',
        notes='Erstbefund',
        measured_at=datetime.now() - timedelta(days=14),
    )
    messung2 = TreatmentMeasurement(
        series_id=serie1.id, measurement_type='single',
        label='Schmerzskala VAS', value='5', unit='VAS 0-10',
        notes='Nach 2 Behandlungen',
        measured_at=datetime.now() - timedelta(days=7),
    )
    messung3 = TreatmentMeasurement(
        series_id=serie1.id, measurement_type='pair',
        label='Rumpfflexion', value_pair_left='', value_pair_right='',
        unit='cm',
        notes='Finger-Boden-Abstand',
    )
    db.session.add_all([messung1, messung2, messung3])

    # === Phase 3: Abrechnungs-Demo-Daten ===

    # --- Taxpunktwerte (Zürich und Winterthur) ---
    tp_values = [
        # Tarif 311 - Physiotherapie UVG/IVG/MVG
        TaxPointValue(tariff_type='311', canton='ZH', value=1.0, notes='Physiotherapie UVG/IVG/MVG Zürich'),
        TaxPointValue(tariff_type='311', canton='AG', value=0.98, notes='Physiotherapie UVG/IVG/MVG Winterthur/AG'),
        # Tarif 312 - Physiotherapie KVG
        TaxPointValue(tariff_type='312', canton='ZH', value=1.0, notes='Physiotherapie KVG Zürich'),
        TaxPointValue(tariff_type='312', canton='AG', value=0.97, notes='Physiotherapie KVG Winterthur/AG'),
        # Tarif 338 - Ergotherapie
        TaxPointValue(tariff_type='338', canton='ZH', value=1.0, notes='Ergotherapie Zürich'),
        # Tarif 590 - EMR Komplementärmedizin
        TaxPointValue(tariff_type='590', canton='ZH', value=1.0, notes='EMR Komplementärmedizin Zürich'),
    ]
    db.session.add_all(tp_values)

    # --- Mahnwesen-Konfiguration ---
    dunning_configs = [
        DunningConfig(organization_id=org.id, level=1, days_after_due=30, fee=0,
                      text_template='Sehr geehrte/r {patient_name}, wir erinnern Sie freundlich an die offene Rechnung {invoice_number} über CHF {amount}. Bitte begleichen Sie den Betrag innert 10 Tagen.'),
        DunningConfig(organization_id=org.id, level=2, days_after_due=60, fee=10.0,
                      text_template='Sehr geehrte/r {patient_name}, trotz unserer Zahlungserinnerung ist die Rechnung {invoice_number} über CHF {amount} weiterhin offen. Wir belasten Ihnen eine Mahngebühr von CHF 10.00. Bitte begleichen Sie den Betrag innert 10 Tagen.'),
        DunningConfig(organization_id=org.id, level=3, days_after_due=90, fee=20.0,
                      text_template='Sehr geehrte/r {patient_name}, letzte Mahnung vor Einleitung des Inkassoverfahrens. Rechnung {invoice_number} über CHF {amount} ist seit über 90 Tagen überfällig. Mahngebühr: CHF 20.00.'),
    ]
    db.session.add_all(dunning_configs)

    db.session.flush()

    # --- 5 Rechnungen (verschiedene Status) ---

    # Rechnung 1: Anna Müller - Serie 1, offen (Tiers Garant, KVG)
    inv1 = Invoice(
        invoice_number='RE-2026-0001',
        series_id=serie1.id,
        patient_id=patienten[0].id,
        insurance_provider_id=ins_css.id,
        therapist_id=thomas_emp.id,
        doctor_id=dr_schmidt.id,
        amount=96.00,
        status='sent',
        billing_type='KVG',
        billing_model='tiers_garant',
        tariff_type='312',
        due_date=date.today() - timedelta(days=5),
        sent_at=datetime.utcnow() - timedelta(days=25),
        qr_reference='00000000000000000000000011',
    )
    db.session.add(inv1)
    db.session.flush()
    # 2 Positionen für 2 Termine
    db.session.add(InvoiceItem(invoice_id=inv1.id, tariff_code='312',
                               description='Physiotherapie KVG Standard (30 Min.)',
                               quantity=1, tax_points=48.0, tax_point_value=1.0,
                               amount=48.00, position=1))
    db.session.add(InvoiceItem(invoice_id=inv1.id, tariff_code='312',
                               description='Physiotherapie KVG Standard (30 Min.)',
                               quantity=1, tax_points=48.0, tax_point_value=1.0,
                               amount=48.00, position=2))

    # Rechnung 2: Peter Schmid - Serie 2, bezahlt (Tiers Garant, KVG)
    inv2 = Invoice(
        invoice_number='RE-2026-0002',
        series_id=serie2.id,
        patient_id=patienten[1].id,
        insurance_provider_id=ins_swica.id,
        therapist_id=thomas_emp.id,
        doctor_id=dr_mueller.id,
        amount=48.00,
        status='paid',
        billing_type='KVG',
        billing_model='tiers_garant',
        tariff_type='312',
        due_date=date.today() - timedelta(days=15),
        sent_at=datetime.utcnow() - timedelta(days=40),
        paid_at=datetime.utcnow() - timedelta(days=10),
        qr_reference='00000000000000000000000022',
    )
    db.session.add(inv2)
    db.session.flush()
    db.session.add(InvoiceItem(invoice_id=inv2.id, tariff_code='312',
                               description='Physiotherapie KVG Standard (30 Min.)',
                               quantity=1, tax_points=48.0, tax_point_value=1.0,
                               amount=48.00, position=1))
    # Zahlung für Rechnung 2
    db.session.add(Payment(invoice_id=inv2.id, amount=48.00,
                           payment_date=date.today() - timedelta(days=10),
                           reference='VESR-20260313', source='vesr'))

    # Rechnung 3: Markus Huber - Serie 3, UVG Tiers Payant, gesendet
    inv3 = Invoice(
        invoice_number='RE-2026-0003',
        series_id=serie3.id,
        patient_id=patienten[5].id,
        insurance_provider_id=ins_helsana.id,
        therapist_id=marco_emp.id,
        doctor_id=dr_schmidt.id,
        amount=144.00,
        status='sent',
        billing_type='UVG',
        billing_model='tiers_payant',
        tariff_type='311',
        due_date=date.today() + timedelta(days=20),
        sent_at=datetime.utcnow() - timedelta(days=10),
        tp_copy_sent=True,
        qr_reference='00000000000000000000000033',
    )
    db.session.add(inv3)
    db.session.flush()
    for i in range(3):
        db.session.add(InvoiceItem(invoice_id=inv3.id, tariff_code='311',
                                   description='Physiotherapie UVG (30 Min.)',
                                   quantity=1, tax_points=48.0, tax_point_value=1.0,
                                   amount=48.00, position=i + 1))

    # Rechnung 4: Daniel Steiner - Serie 4, UVG Tiers Payant, teilbezahlt
    inv4 = Invoice(
        invoice_number='RE-2026-0004',
        series_id=serie4.id,
        patient_id=patienten[7].id,
        insurance_provider_id=ins_suva.id,
        therapist_id=sarah_emp.id,
        doctor_id=dr_weber.id,
        amount=96.00,
        status='partially_paid',
        billing_type='UVG',
        billing_model='tiers_payant',
        tariff_type='311',
        due_date=date.today() + timedelta(days=10),
        sent_at=datetime.utcnow() - timedelta(days=20),
        tp_copy_sent=True,
        qr_reference='00000000000000000000000044',
    )
    db.session.add(inv4)
    db.session.flush()
    db.session.add(InvoiceItem(invoice_id=inv4.id, tariff_code='311',
                               description='Physiotherapie UVG (30 Min.)',
                               quantity=1, tax_points=48.0, tax_point_value=1.0,
                               amount=48.00, position=1))
    db.session.add(InvoiceItem(invoice_id=inv4.id, tariff_code='311',
                               description='Physiotherapie UVG (30 Min.)',
                               quantity=1, tax_points=48.0, tax_point_value=1.0,
                               amount=48.00, position=2))
    # Teilzahlung
    db.session.add(Payment(invoice_id=inv4.id, amount=48.00,
                           payment_date=date.today() - timedelta(days=5),
                           reference='MediData-001', source='medidata'))

    # Rechnung 5: René Gerber - Serie 5, EMR Privat, offen (überfällig)
    inv5 = Invoice(
        invoice_number='RE-2026-0005',
        series_id=serie5.id,
        patient_id=patienten[9].id,
        insurance_provider_id=ins_helsana.id,
        therapist_id=thomas_emp.id,
        amount=324.00,
        status='sent',
        billing_type='private',
        billing_model='tiers_garant',
        tariff_type='590',
        due_date=date.today() - timedelta(days=35),
        sent_at=datetime.utcnow() - timedelta(days=60),
        dunning_level=1,
        last_dunning_date=date.today() - timedelta(days=5),
        qr_reference='00000000000000000000000055',
    )
    db.session.add(inv5)
    db.session.flush()
    for i in range(6):
        db.session.add(InvoiceItem(invoice_id=inv5.id, tariff_code='590',
                                   description='EMR Komplementärmedizin (60 Min.)',
                                   quantity=1, tax_points=108.0, tax_point_value=0.5,
                                   amount=54.00, position=i + 1))

    # --- 2 Gutsprachen ---

    # Gutsprache 1: Markus Huber - UVG, genehmigt
    gs1 = CostApproval(
        patient_id=patienten[5].id,
        insurance_provider_id=ins_helsana.id,
        doctor_id=dr_schmidt.id,
        series_id=serie3.id,
        diagnosis='Schulterimpingement links',
        treatment_type='Physiotherapie',
        status='approved',
        approved_sessions=9,
        approved_amount=432.00,
        valid_until=date.today() + timedelta(days=60),
        sent_at=datetime.utcnow() - timedelta(days=30),
        answered_at=datetime.utcnow() - timedelta(days=20),
    )
    db.session.add(gs1)

    # Gutsprache 2: Daniel Steiner - UVG, ausstehend
    gs2 = CostApproval(
        patient_id=patienten[7].id,
        insurance_provider_id=ins_suva.id,
        doctor_id=dr_weber.id,
        series_id=serie4.id,
        diagnosis='Distorsion OSG rechts (Sportunfall)',
        treatment_type='Physiotherapie',
        status='sent',
        approved_sessions=9,
        valid_until=date.today() + timedelta(days=90),
        sent_at=datetime.utcnow() - timedelta(days=7),
    )
    db.session.add(gs2)

    db.session.commit()
    print(f'Demo-Daten erstellt: 1 Organisation, 2 Standorte, 8 Ressourcen, 5 Mitarbeiter, '
          f'{len(patienten)} Patienten, {len(termin_daten)} Termine, '
          f'3 Templates, 5 Behandlungsserien, 3 Ärzte, '
          f'5 Rechnungen, 3 Zahlungen, 2 Gutsprachen, 6 Taxpunktwerte')


# App erstellen
app = create_app()

if __name__ == '__main__':
    app.run(debug=True, port=5000)
