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

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(patients_bp, url_prefix='/patients')
    app.register_blueprint(calendar_bp, url_prefix='/calendar')
    app.register_blueprint(employees_bp, url_prefix='/employees')

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
                        Patient, Appointment, Resource, InsuranceProvider)

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

    # === Ressourcen (Behandlungsräume) ===
    res1 = Resource(location_id=loc_zh.id, name='Behandlungsraum 1', type='room')
    res2 = Resource(location_id=loc_zh.id, name='Behandlungsraum 2', type='room')
    res3 = Resource(location_id=loc_wt.id, name='Behandlungsraum 1', type='room')
    db.session.add_all([res1, res2, res3])

    # === Versicherungen ===
    ins_css = InsuranceProvider(name='CSS Versicherung', gln_number='7601003000015', supports_electronic_billing=True)
    ins_swica = InsuranceProvider(name='Swica', gln_number='7601003000022', supports_electronic_billing=True)
    ins_helsana = InsuranceProvider(name='Helsana', gln_number='7601003000039', supports_electronic_billing=True)
    ins_suva = InsuranceProvider(name='Suva', gln_number='7601003000046', supports_electronic_billing=True)
    db.session.add_all([ins_css, ins_swica, ins_helsana, ins_suva])
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

    # === Termine (20 Termine über die nächsten 2 Wochen) ===
    heute = date.today()
    # Nächsten Montag finden
    naechster_montag = heute + timedelta(days=(7 - heute.weekday()) % 7)
    if naechster_montag == heute and heute.weekday() == 0:
        naechster_montag = heute

    # Termine verteilen
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

    db.session.commit()
    print(f'Demo-Daten erstellt: 1 Organisation, 2 Standorte, 5 Mitarbeiter, {len(patienten)} Patienten, {len(termin_daten)} Termine')


# App erstellen
app = create_app()

if __name__ == '__main__':
    app.run(debug=True, port=5000)
