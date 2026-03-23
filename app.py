import os
import json
from datetime import datetime, timedelta, date, time
from flask import Flask
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from models import db, Organization, Location, User, Employee, WorkSchedule, Patient, \
    InsuranceProvider, Doctor, Resource, TreatmentSeriesTemplate, TreatmentSeries, \
    Appointment, AISettings, Product, MaintenanceRecord, BankAccount, Holiday, TaxPointValue, \
    Certificate, AbsenceQuota, Absence, PatientDocument, Contact, WaitingList, \
    TherapyGoal, Milestone, Measurement, HealingPhase, \
    SystemSetting, EmailTemplate, PrintTemplate, Permission
from config import config


login_manager = LoginManager()
csrf = CSRFProtect()


def create_app(config_name=None):
    """App-Factory: Erstellt und konfiguriert die Flask-Anwendung"""
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'default')

    app = Flask(__name__)
    app.config.from_object(config.get(config_name, config['default']))

    # Erweiterungen initialisieren
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Bitte melden Sie sich an.'
    login_manager.login_message_category = 'info'
    csrf.init_app(app)

    # CSRF fuer API-Routen deaktivieren
    @app.before_request
    def csrf_exempt_api():
        pass

    # Blueprints registrieren
    from blueprints.auth import auth_bp
    from blueprints.dashboard import dashboard_bp
    from blueprints.products import products_bp
    from blueprints.resources import resources_bp
    from blueprints.practice import practice_bp
    from blueprints.employees import employees_bp
    from blueprints.patients import patients_bp
    from blueprints.addresses import addresses_bp
    from blueprints.calendar import calendar_bp
    from blueprints.treatment import treatment_bp
    from blueprints.settings import settings_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(products_bp, url_prefix='/products')
    app.register_blueprint(resources_bp, url_prefix='/resources')
    app.register_blueprint(practice_bp, url_prefix='/practice')
    app.register_blueprint(employees_bp, url_prefix='/employees')
    app.register_blueprint(patients_bp, url_prefix='/patients')
    app.register_blueprint(addresses_bp, url_prefix='/addresses')
    app.register_blueprint(calendar_bp, url_prefix='/calendar')
    app.register_blueprint(treatment_bp, url_prefix='/treatment')
    app.register_blueprint(settings_bp, url_prefix='/settings')

    # CSRF-Exempt fuer API-Routen
    csrf.exempt(dashboard_bp)
    csrf.exempt(products_bp)
    csrf.exempt(resources_bp)
    csrf.exempt(practice_bp)
    csrf.exempt(employees_bp)
    csrf.exempt(patients_bp)
    csrf.exempt(addresses_bp)
    csrf.exempt(calendar_bp)
    csrf.exempt(treatment_bp)
    csrf.exempt(settings_bp)

    # Kontext-Prozessoren
    @app.context_processor
    def inject_globals():
        now = datetime.now()
        hour = now.hour
        if hour < 12:
            tageszeit = 'Morgen'
        elif hour < 17:
            tageszeit = 'Nachmittag'
        else:
            tageszeit = 'Abend'

        return {
            'app_name': app.config['APP_NAME'],
            'current_year': now.year,
            'current_datetime': now,
            'tageszeit': tageszeit,
            'timedelta': timedelta,
            'today': date.today()
        }

    # Datenbank erstellen und Demo-Daten laden
    with app.app_context():
        db.create_all()
        seed_demo_data()

    return app


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def seed_demo_data():
    """Erstellt Demo-Daten beim ersten Start"""
    if Organization.query.first() is not None:
        return

    # === Organisation ===
    org = Organization(
        name='OMNIA Health Services AG',
        address='Bahnhofstrasse 1',
        city='Zuerich',
        zip_code='8001',
        phone='+41 44 123 45 67',
        email='info@omnia-health.ch',
        uid_number='CHE-123.456.789',
        gln_number='7601000000000',
        zsr_number='A000000'
    )
    db.session.add(org)
    db.session.flush()

    # === Standorte ===
    oeffnungszeiten = json.dumps({
        'montag': {'von': '07:00', 'bis': '19:00'},
        'dienstag': {'von': '07:00', 'bis': '19:00'},
        'mittwoch': {'von': '07:00', 'bis': '19:00'},
        'donnerstag': {'von': '07:00', 'bis': '19:00'},
        'freitag': {'von': '07:00', 'bis': '19:00'},
        'samstag': None,
        'sonntag': None
    })

    loc_zh = Location(
        organization_id=org.id,
        name='OMNIA Zuerich',
        address='Bahnhofstrasse 42',
        city='Zuerich',
        zip_code='8001',
        phone='+41 44 123 45 67',
        email='zuerich@omnia-health.ch',
        opening_hours_json=oeffnungszeiten
    )
    loc_wt = Location(
        organization_id=org.id,
        name='OMNIA Winterthur',
        address='Marktgasse 15',
        city='Winterthur',
        zip_code='8400',
        phone='+41 52 234 56 78',
        email='winterthur@omnia-health.ch',
        opening_hours_json=oeffnungszeiten
    )
    db.session.add_all([loc_zh, loc_wt])
    db.session.flush()

    # === Benutzer & Mitarbeiter ===
    users_data = [
        {
            'username': 'admin', 'password': 'admin', 'first_name': 'Thomas',
            'last_name': 'Balke', 'role': 'admin', 'email': 'admin@omnia-health.ch',
            'employee': True, 'color': '#2c3e50', 'location': loc_zh
        },
        {
            'username': 'thomas', 'password': 'thomas', 'first_name': 'Thomas',
            'last_name': 'Meier', 'role': 'therapist', 'email': 'thomas.meier@omnia-health.ch',
            'employee': True, 'color': '#4a90d9', 'location': loc_zh
        },
        {
            'username': 'sarah', 'password': 'sarah', 'first_name': 'Sarah',
            'last_name': 'Weber', 'role': 'therapist', 'email': 'sarah.weber@omnia-health.ch',
            'employee': True, 'color': '#e74c3c', 'location': loc_wt
        },
        {
            'username': 'lisa', 'password': 'lisa', 'first_name': 'Lisa',
            'last_name': 'Brunner', 'role': 'reception', 'email': 'lisa.brunner@omnia-health.ch',
            'employee': True, 'color': '#27ae60', 'location': loc_zh
        }
    ]

    employees = {}
    created_users = {}
    for ud in users_data:
        user = User(
            organization_id=org.id,
            username=ud['username'],
            first_name=ud['first_name'],
            last_name=ud['last_name'],
            name=f"{ud['first_name']} {ud['last_name']}",
            email=ud['email'],
            role=ud['role']
        )
        user.set_password(ud['password'])
        db.session.add(user)
        db.session.flush()
        created_users[ud['username']] = user

        if ud.get('employee'):
            emp = Employee(
                user_id=user.id,
                organization_id=org.id,
                employee_number=f'MA{user.id:03d}',
                color_code=ud['color'],
                default_location_id=ud['location'].id,
                pensum_percent=100 if ud['role'] != 'reception' else 80,
                employment_model='Festanstellung'
            )
            db.session.add(emp)
            db.session.flush()
            employees[ud['username']] = emp

    # === Arbeitszeiten (Mo-Fr) fuer Therapeuten ===
    for username in ['thomas', 'sarah']:
        emp = employees[username]
        for day in range(5):  # Mo-Fr
            # Vormittag
            db.session.add(WorkSchedule(
                employee_id=emp.id,
                location_id=emp.default_location_id,
                day_of_week=day,
                start_time=time(8, 0),
                end_time=time(12, 0),
                work_type='treatment'
            ))
            # Nachmittag
            db.session.add(WorkSchedule(
                employee_id=emp.id,
                location_id=emp.default_location_id,
                day_of_week=day,
                start_time=time(13, 0),
                end_time=time(17, 0),
                work_type='treatment'
            ))

    # === Raeume & Geraete ===
    for loc in [loc_zh, loc_wt]:
        for i in range(1, 4):
            db.session.add(Resource(
                organization_id=org.id,
                location_id=loc.id,
                name=f'Behandlungsraum {i}',
                resource_type='room',
                description=f'Behandlungsraum {i} am Standort {loc.name}',
                capacity=1
            ))

    db.session.add(Resource(
        organization_id=org.id,
        location_id=loc_zh.id,
        name='Ultraschall',
        resource_type='device',
        description='Ultraschallgeraet fuer therapeutische Anwendungen'
    ))
    db.session.add(Resource(
        organization_id=org.id,
        location_id=loc_zh.id,
        name='Stosswellengeraet',
        resource_type='device',
        description='Stosswellengeraet fuer Schmerztherapie'
    ))

    # === Versicherungen ===
    insurances = [
        InsuranceProvider(
            name='Helsana', gln_number='7601003000015',
            address='Postfach', city='Zuerich', zip_code='8081',
            phone='+41 58 340 00 00', email='info@helsana.ch',
            supports_electronic_billing=True
        ),
        InsuranceProvider(
            name='CSS Versicherung', gln_number='7601003000022',
            address='Tribschenstrasse 21', city='Luzern', zip_code='6002',
            phone='+41 58 277 11 11', email='info@css.ch',
            supports_electronic_billing=True
        ),
        InsuranceProvider(
            name='Swica', gln_number='7601003000039',
            address='Roeoeslistrasse 15', city='Winterthur', zip_code='8401',
            phone='+41 52 244 22 33', email='info@swica.ch',
            supports_electronic_billing=True
        )
    ]
    db.session.add_all(insurances)
    db.session.flush()

    # === Aerzte ===
    doctors = [
        Doctor(salutation='Dr. med.', first_name='Peter', last_name='Mueller',
               specialty='Allgemeinmedizin', gln_number='7601000000101',
               zsr_number='B000001', address='Seestrasse 10', city='Zuerich',
               zip_code='8002', phone='+41 44 201 00 01'),
        Doctor(salutation='Dr. med.', first_name='Anna', last_name='Schmidt',
               specialty='Orthopaedie', gln_number='7601000000102',
               zsr_number='B000002', address='Bahnhofplatz 5', city='Winterthur',
               zip_code='8400', phone='+41 52 212 00 02'),
        Doctor(salutation='Dr. med.', first_name='Marco', last_name='Rossi',
               specialty='Rheumatologie', gln_number='7601000000103',
               zsr_number='B000003', address='Langstrasse 88', city='Zuerich',
               zip_code='8004', phone='+41 44 241 00 03'),
        Doctor(salutation='Dr. med.', first_name='Claudia', last_name='Bianchi',
               specialty='Neurologie', gln_number='7601000000104',
               zsr_number='B000004', address='Marktplatz 3', city='Winterthur',
               zip_code='8400', phone='+41 52 222 00 04'),
        Doctor(salutation='Dr. med.', first_name='Stefan', last_name='Keller',
               specialty='Chirurgie', gln_number='7601000000105',
               zsr_number='B000005', address='Limmatquai 12', city='Zuerich',
               zip_code='8001', phone='+41 44 251 00 05')
    ]
    db.session.add_all(doctors)
    db.session.flush()

    # === Patienten ===
    patienten_data = [
        ('Herr', 'Max', 'Huber', '1985-03-15', 'maennlich', '+41 79 100 10 01', 'max.huber@gmail.com', 'Muehlegasse 5', 'Zuerich', '8001', 0),
        ('Frau', 'Sandra', 'Meier', '1990-07-22', 'weiblich', '+41 79 100 10 02', 'sandra.meier@bluewin.ch', 'Rosenweg 12', 'Winterthur', '8400', 1),
        ('Herr', 'Bruno', 'Keller', '1978-11-03', 'maennlich', '+41 79 100 10 03', 'b.keller@gmx.ch', 'Hauptstrasse 8', 'Zuerich', '8003', 2),
        ('Frau', 'Maria', 'Fischer', '1965-01-28', 'weiblich', '+41 79 100 10 04', 'maria.fischer@outlook.com', 'Seeweg 22', 'Winterthur', '8400', 0),
        ('Herr', 'Lukas', 'Zimmermann', '1992-09-10', 'maennlich', '+41 79 100 10 05', 'lukas.z@gmail.com', 'Bergstrasse 3', 'Zuerich', '8002', 1),
        ('Frau', 'Nina', 'Brunner', '1988-04-17', 'weiblich', '+41 79 100 10 06', 'nina.b@sunrise.ch', 'Wiesenstrasse 7', 'Zuerich', '8001', 2),
        ('Herr', 'Daniel', 'Schmid', '1975-12-05', 'maennlich', '+41 79 100 10 07', 'daniel.schmid@gmail.com', 'Kirchgasse 15', 'Winterthur', '8400', 0),
        ('Frau', 'Petra', 'Schneider', '1982-06-20', 'weiblich', '+41 79 100 10 08', 'p.schneider@bluewin.ch', 'Schulstrasse 9', 'Zuerich', '8004', 1),
        ('Herr', 'Andreas', 'Widmer', '1970-08-14', 'maennlich', '+41 79 100 10 09', 'a.widmer@gmx.ch', 'Dorfstrasse 33', 'Winterthur', '8400', 2),
        ('Frau', 'Claudia', 'Baumann', '1995-02-08', 'weiblich', '+41 79 100 10 10', 'claudia.b@gmail.com', 'Gartenstrasse 11', 'Zuerich', '8002', 0),
        ('Herr', 'Thomas', 'Gerber', '1960-05-25', 'maennlich', '+41 79 100 10 11', 't.gerber@outlook.com', 'Altstadt 6', 'Winterthur', '8400', 1),
        ('Frau', 'Monika', 'Steiner', '1987-10-30', 'weiblich', '+41 79 100 10 12', 'm.steiner@sunrise.ch', 'Talstrasse 18', 'Zuerich', '8001', 2),
        ('Herr', 'Rolf', 'Frei', '1972-03-12', 'maennlich', '+41 79 100 10 13', 'rolf.frei@gmail.com', 'Sonnenhof 4', 'Zuerich', '8003', 0),
        ('Frau', 'Eva', 'Buergi', '1993-08-07', 'weiblich', '+41 79 100 10 14', 'eva.b@bluewin.ch', 'Lindenstrasse 25', 'Winterthur', '8400', 1),
        ('Herr', 'Martin', 'Wenger', '1980-12-19', 'maennlich', '+41 79 100 10 15', 'm.wenger@gmx.ch', 'Bachweg 2', 'Zuerich', '8005', 2)
    ]

    patients = []
    for i, (sal, fn, ln, dob, gen, phone, email, addr, city, zc, ins_idx) in enumerate(patienten_data):
        p = Patient(
            organization_id=org.id,
            patient_number=f'P{i+1:05d}',
            salutation=sal,
            first_name=fn,
            last_name=ln,
            date_of_birth=datetime.strptime(dob, '%Y-%m-%d').date(),
            gender=gen,
            mobile=phone,
            email=email,
            address=addr,
            city=city,
            zip_code=zc,
            country='CH',
            insurance_provider_id=insurances[ins_idx].id,
            insurance_number=f'KV{80000000 + i + 1}',
            insurance_type='KVG',
            ahv_number=f'756.{1234+i:04d}.{5678+i:04d}.{10+i:02d}'
        )
        db.session.add(p)
        patients.append(p)

    db.session.flush()

    # === Serienvorlagen ===
    tpl_physio_kvg = TreatmentSeriesTemplate(
        organization_id=org.id,
        name='Physiotherapie KVG',
        short_name='PT-KVG',
        tariff_type='TarReha',
        num_appointments=9,
        duration_minutes=30,
        min_interval_days=1,
        default_location_id=loc_zh.id
    )
    tpl_physio_uvg = TreatmentSeriesTemplate(
        organization_id=org.id,
        name='Physiotherapie UVG',
        short_name='PT-UVG',
        tariff_type='TarReha',
        num_appointments=9,
        duration_minutes=30,
        min_interval_days=1,
        default_location_id=loc_zh.id
    )
    tpl_manuell = TreatmentSeriesTemplate(
        organization_id=org.id,
        name='Manuelle Therapie',
        short_name='MT',
        tariff_type='Physiotarif',
        num_appointments=6,
        duration_minutes=45,
        min_interval_days=3,
        default_location_id=loc_zh.id
    )
    db.session.add_all([tpl_physio_kvg, tpl_physio_uvg, tpl_manuell])
    db.session.flush()

    # === Behandlungsserien ===
    serien = [
        TreatmentSeries(
            patient_id=patients[0].id, template_id=tpl_physio_kvg.id,
            therapist_id=employees['thomas'].id, location_id=loc_zh.id,
            prescribing_doctor_id=doctors[0].id,
            diagnosis_code='M54.5', diagnosis_text='Kreuzschmerz',
            prescription_date=date.today() - timedelta(days=14),
            status='active', insurance_type='KVG', billing_model='tiers_garant'
        ),
        TreatmentSeries(
            patient_id=patients[1].id, template_id=tpl_physio_kvg.id,
            therapist_id=employees['sarah'].id, location_id=loc_wt.id,
            prescribing_doctor_id=doctors[1].id,
            diagnosis_code='M75.1', diagnosis_text='Impingement-Syndrom Schulter',
            prescription_date=date.today() - timedelta(days=7),
            status='active', insurance_type='KVG', billing_model='tiers_garant'
        ),
        TreatmentSeries(
            patient_id=patients[2].id, template_id=tpl_physio_uvg.id,
            therapist_id=employees['thomas'].id, location_id=loc_zh.id,
            prescribing_doctor_id=doctors[4].id,
            diagnosis_code='S82.1', diagnosis_text='Fraktur proximale Tibia',
            prescription_date=date.today() - timedelta(days=21),
            status='active', insurance_type='UVG', billing_model='tiers_payant'
        ),
        TreatmentSeries(
            patient_id=patients[3].id, template_id=tpl_manuell.id,
            therapist_id=employees['sarah'].id, location_id=loc_wt.id,
            prescribing_doctor_id=doctors[3].id,
            diagnosis_code='M53.1', diagnosis_text='Zervikobrachiales Syndrom',
            prescription_date=date.today() - timedelta(days=30),
            status='completed', insurance_type='KVG', billing_model='tiers_garant',
            completed_at=datetime.now() - timedelta(days=2)
        ),
        TreatmentSeries(
            patient_id=patients[4].id, template_id=tpl_physio_kvg.id,
            therapist_id=employees['thomas'].id, location_id=loc_zh.id,
            prescribing_doctor_id=doctors[0].id,
            diagnosis_code='M25.5', diagnosis_text='Gelenkschmerz Knie',
            prescription_date=date.today() - timedelta(days=3),
            status='active', insurance_type='KVG', billing_model='tiers_garant'
        )
    ]
    db.session.add_all(serien)
    db.session.flush()

    # === Termine (20 verteilt ueber 2 Wochen) ===
    today = date.today()
    thomas_emp = employees['thomas']
    sarah_emp = employees['sarah']

    termin_daten = [
        # Woche 1
        (today + timedelta(days=0), time(8, 0), 30, patients[0], thomas_emp, loc_zh, serien[0], 'Physiotherapie'),
        (today + timedelta(days=0), time(9, 0), 30, patients[2], thomas_emp, loc_zh, serien[2], 'Physiotherapie UVG'),
        (today + timedelta(days=0), time(10, 0), 30, patients[4], thomas_emp, loc_zh, serien[4], 'Physiotherapie'),
        (today + timedelta(days=0), time(8, 30), 45, patients[1], sarah_emp, loc_wt, serien[1], 'Physiotherapie'),
        (today + timedelta(days=1), time(8, 0), 30, patients[5], thomas_emp, loc_zh, None, 'Ersttermin'),
        (today + timedelta(days=1), time(9, 30), 30, patients[0], thomas_emp, loc_zh, serien[0], 'Physiotherapie'),
        (today + timedelta(days=1), time(14, 0), 45, patients[6], sarah_emp, loc_wt, None, 'Ersttermin'),
        (today + timedelta(days=2), time(10, 0), 30, patients[7], thomas_emp, loc_zh, None, 'Physiotherapie'),
        (today + timedelta(days=2), time(8, 0), 30, patients[1], sarah_emp, loc_wt, serien[1], 'Physiotherapie'),
        (today + timedelta(days=3), time(8, 0), 30, patients[2], thomas_emp, loc_zh, serien[2], 'Physiotherapie UVG'),
        (today + timedelta(days=3), time(14, 0), 30, patients[8], sarah_emp, loc_wt, None, 'Physiotherapie'),
        (today + timedelta(days=4), time(9, 0), 30, patients[4], thomas_emp, loc_zh, serien[4], 'Physiotherapie'),
        # Woche 2
        (today + timedelta(days=7), time(8, 0), 30, patients[0], thomas_emp, loc_zh, serien[0], 'Physiotherapie'),
        (today + timedelta(days=7), time(10, 0), 30, patients[9], thomas_emp, loc_zh, None, 'Ersttermin'),
        (today + timedelta(days=8), time(8, 0), 45, patients[1], sarah_emp, loc_wt, serien[1], 'Physiotherapie'),
        (today + timedelta(days=8), time(14, 0), 30, patients[10], sarah_emp, loc_wt, None, 'Physiotherapie'),
        (today + timedelta(days=9), time(9, 0), 30, patients[2], thomas_emp, loc_zh, serien[2], 'Physiotherapie UVG'),
        (today + timedelta(days=9), time(11, 0), 30, patients[11], thomas_emp, loc_zh, None, 'Physiotherapie'),
        (today + timedelta(days=10), time(8, 0), 30, patients[12], sarah_emp, loc_wt, None, 'Physiotherapie'),
        (today + timedelta(days=11), time(10, 0), 30, patients[4], thomas_emp, loc_zh, serien[4], 'Physiotherapie'),
    ]

    for td, start_t, dauer, pat, emp, loc, serie, titel in termin_daten:
        start_dt = datetime.combine(td, start_t)
        end_dt = start_dt + timedelta(minutes=dauer)
        appt = Appointment(
            series_id=serie.id if serie else None,
            patient_id=pat.id,
            employee_id=emp.id,
            location_id=loc.id,
            start_time=start_dt,
            end_time=end_dt,
            duration_minutes=dauer,
            status='scheduled',
            appointment_type='treatment',
            title=titel
        )
        db.session.add(appt)

    # === Produkte ===
    produkte_data = [
        ('Theraband Rot (leicht)', 'Therapiematerial', 8.50, 8.1, 'Stueck', 25, 5, 'Thera-Band GmbH', 'Thera-Band', 'TB-ROT-001'),
        ('Theraband Gruen (mittel)', 'Therapiematerial', 8.50, 8.1, 'Stueck', 20, 5, 'Thera-Band GmbH', 'Thera-Band', 'TB-GRN-002'),
        ('Theraband Blau (stark)', 'Therapiematerial', 8.50, 8.1, 'Stueck', 15, 5, 'Thera-Band GmbH', 'Thera-Band', 'TB-BLU-003'),
        ('Faszienrolle Standard', 'Therapiematerial', 32.00, 8.1, 'Stueck', 10, 3, 'Blackroll AG', 'Blackroll', 'FR-STD-001'),
        ('Kinesio-Tape 5m', 'Verbrauchsmaterial', 12.90, 8.1, 'Stueck', 30, 10, 'K-Tape AG', 'K-Tape', 'KT-5M-001'),
        ('Ultraschall-Gel 250ml', 'Verbrauchsmaterial', 6.50, 8.1, 'Stueck', 8, 10, 'Sono Swiss AG', 'SonoGel', 'UG-250-001'),
        ('Einweg-Handschuhe Box (100)', 'Verbrauchsmaterial', 9.90, 8.1, 'Packung', 12, 5, 'MediSupply AG', 'SafeGrip', 'EH-100-001'),
        ('Gymnastikball 65cm', 'Therapiematerial', 28.00, 8.1, 'Stueck', 6, 2, 'TOGU GmbH', 'TOGU', 'GB-65-001'),
        ('Kuehlung Spray 150ml', 'Verbrauchsmaterial', 11.50, 8.1, 'Stueck', 15, 5, 'Perskindol AG', 'Perskindol', 'KS-150-001'),
        ('Igelball Set (2 Stueck)', 'Retail', 14.90, 8.1, 'Stueck', 18, 5, 'Sissel GmbH', 'Sissel', 'IB-SET-001'),
    ]

    for name, cat, price, vat, unit, stock, min_s, supplier, manufacturer, artnr in produkte_data:
        db.session.add(Product(
            organization_id=org.id,
            name=name,
            category=cat,
            net_price=price,
            vat_rate=vat,
            unit_type=unit,
            stock_quantity=stock,
            min_stock=min_s,
            supplier=supplier,
            manufacturer=manufacturer,
            article_number=artnr
        ))

    db.session.flush()

    # === Wartungseintraege fuer Geraete ===
    # Ultraschall und Stosswellengeraet finden
    ultraschall = Resource.query.filter_by(name='Ultraschall').first()
    stosswelle = Resource.query.filter_by(name='Stosswellengeraet').first()

    if ultraschall:
        db.session.add(MaintenanceRecord(
            resource_id=ultraschall.id,
            maintenance_type='regular',
            description='Jaehrliche Wartung und Kalibrierung',
            performed_at=date.today() - timedelta(days=90),
            performed_by='MedTech Service AG',
            next_due=date.today() + timedelta(days=275),
            interval_months=12
        ))

    if stosswelle:
        db.session.add(MaintenanceRecord(
            resource_id=stosswelle.id,
            maintenance_type='regular',
            description='Halbjaehrliche Wartung',
            performed_at=date.today() - timedelta(days=210),
            performed_by='MedTech Service AG',
            next_due=date.today() - timedelta(days=27),
            interval_months=6
        ))

    # === Oeffnungszeiten der Organisation ===
    org.opening_hours_json = oeffnungszeiten
    org.contact_person = 'Thomas Balke'
    org.default_language = 'de'

    # === Bankkonten ===
    bank_ubs = BankAccount(
        organization_id=org.id,
        bank_name='UBS Switzerland AG',
        iban='CH9300762011623852957',
        qr_iban='CH4431999123000889012',
        bic_swift='UBSWCHZH80A',
        account_name='Hauptkonto UBS Zürich',
        is_default=True
    )
    bank_zkb = BankAccount(
        organization_id=org.id,
        bank_name='Zürcher Kantonalbank',
        iban='CH3600700110002069411',
        bic_swift='ZKBKCHZZ80A',
        account_name='Lohnkonto ZKB Winterthur',
        is_default=False
    )
    db.session.add_all([bank_ubs, bank_zkb])

    # === Feiertage 2026 Kanton Zuerich ===
    # Ostersonntag 2026: 5. April
    feiertage_2026 = [
        ('Neujahr', date(2026, 1, 1)),
        ('Karfreitag', date(2026, 4, 3)),
        ('Ostermontag', date(2026, 4, 6)),
        ('Tag der Arbeit', date(2026, 5, 1)),
        ('Auffahrt', date(2026, 5, 14)),
        ('Pfingstmontag', date(2026, 5, 25)),
        ('Bundesfeiertag', date(2026, 8, 1)),
        ('Weihnachten', date(2026, 12, 25)),
        ('Stephanstag', date(2026, 12, 26)),
    ]
    for name, d in feiertage_2026:
        db.session.add(Holiday(
            organization_id=org.id,
            name=name,
            date=d,
            canton='zh'
        ))

    # === Taxpunktwerte ===
    db.session.add(TaxPointValue(
        organization_id=org.id,
        tariff_type='Tarif 312',
        value=1.00,
        valid_from=date(2025, 1, 1)
    ))
    db.session.add(TaxPointValue(
        organization_id=org.id,
        tariff_type='Tarif 311',
        value=0.89,
        valid_from=date(2025, 1, 1)
    ))
    db.session.add(TaxPointValue(
        organization_id=org.id,
        tariff_type='Tarif 590',
        value=1.00,
        valid_from=date(2025, 1, 1)
    ))

    # === Absenzen-Kontingente ===
    thomas_emp = employees['thomas']
    sarah_emp = employees['sarah']
    admin_emp = employees['admin']
    lisa_emp = employees['lisa']

    # Ferienkontingente 2026
    db.session.add(AbsenceQuota(
        employee_id=thomas_emp.id, year=2026, absence_type='vacation',
        total_days=20, used_days=5, carryover_days=0
    ))
    db.session.add(AbsenceQuota(
        employee_id=sarah_emp.id, year=2026, absence_type='vacation',
        total_days=20, used_days=3, carryover_days=0
    ))
    db.session.add(AbsenceQuota(
        employee_id=admin_emp.id, year=2026, absence_type='vacation',
        total_days=20, used_days=2, carryover_days=2
    ))
    db.session.add(AbsenceQuota(
        employee_id=lisa_emp.id, year=2026, absence_type='vacation',
        total_days=16, used_days=1, carryover_days=0  # 80% Pensum = 16 Tage
    ))

    # === Absenzen ===
    # Thomas: 1 Woche Ferien im April
    db.session.add(Absence(
        employee_id=thomas_emp.id, absence_type='vacation',
        start_date=date(2026, 4, 13), end_date=date(2026, 4, 17),
        status='approved', notes='Osterferien'
    ))
    # Sarah: 2 Tage krank letzte Woche
    db.session.add(Absence(
        employee_id=sarah_emp.id, absence_type='sick',
        start_date=today - timedelta(days=today.weekday() + 4),
        end_date=today - timedelta(days=today.weekday() + 3),
        status='approved', notes='Grippe'
    ))
    # Lisa: 1 Tag Weiterbildung naechste Woche
    db.session.add(Absence(
        employee_id=lisa_emp.id, absence_type='training',
        start_date=today + timedelta(days=7 - today.weekday() + 2),  # Mittwoch naechste Woche
        end_date=today + timedelta(days=7 - today.weekday() + 2),
        status='approved', notes='Fortbildung Praxismanagement'
    ))

    # === Zertifikate ===
    db.session.add(Certificate(
        employee_id=thomas_emp.id, name='Manuelle Therapie (OMT)',
        issued_date=date(2022, 3, 15), expiry_date=date(2027, 3, 15)
    ))
    db.session.add(Certificate(
        employee_id=sarah_emp.id, name='Sportphysiotherapie SPT',
        issued_date=date(2023, 6, 1), expiry_date=date(2026, 6, 1)
    ))
    db.session.add(Certificate(
        employee_id=thomas_emp.id, name='Dry Needling Level 2',
        issued_date=date(2024, 1, 20), expiry_date=date(2029, 1, 20)
    ))

    # === Qualifikationen ===
    import json as _json
    thomas_emp.qualifications_json = _json.dumps(['Manuelle Therapie', 'Sportphysiotherapie', 'Dry Needling', 'Triggerpunkttherapie'])
    thomas_emp.specializations_json = _json.dumps(['Kniereha', 'Schulterchirurgie-Nachbehandlung'])
    sarah_emp.qualifications_json = _json.dumps(['Sportphysiotherapie', 'Tape-Anwendungen', 'Medizinische Trainingstherapie'])
    sarah_emp.specializations_json = _json.dumps(['Sportrehabilitation', 'Laufsportanalyse'])

    # === Erweiterte Patientendaten ===
    # Bevorzugte Terminzeiten fuer 5 Patienten
    patients[0].preferred_appointment_times_json = json.dumps({
        'times': ['morgen', 'vormittag'], 'days': ['montag', 'mittwoch', 'freitag']
    })
    patients[1].preferred_appointment_times_json = json.dumps({
        'times': ['nachmittag'], 'days': ['dienstag', 'donnerstag']
    })
    patients[2].preferred_appointment_times_json = json.dumps({
        'times': ['morgen', 'vormittag', 'nachmittag'], 'days': ['montag', 'dienstag', 'mittwoch', 'donnerstag', 'freitag']
    })
    patients[4].preferred_appointment_times_json = json.dumps({
        'times': ['abend'], 'days': ['montag', 'mittwoch']
    })
    patients[7].preferred_appointment_times_json = json.dumps({
        'times': ['vormittag', 'nachmittag'], 'days': ['dienstag', 'freitag']
    })

    # Arbeitgeber fuer 3 Patienten (UVG-Faelle)
    patients[2].employer_name = 'Baumeister AG'
    patients[2].employer_address = 'Industriestrasse 25, 8005 Zuerich'
    patients[2].employer_contact = 'Hans Gruber'
    patients[2].employer_phone = '+41 44 300 50 50'
    patients[2].insurance_type = 'UVG'
    patients[2].case_number = 'UVG-2026-00123'
    patients[2].accident_date = date(2025, 12, 15)

    patients[6].employer_name = 'Swisscom AG'
    patients[6].employer_address = 'Alte Tiefenaustrasse 6, 3048 Worblaufen'
    patients[6].employer_contact = 'Maria Tanner'
    patients[6].employer_phone = '+41 58 221 00 00'

    patients[9].employer_name = 'UBS Switzerland AG'
    patients[9].employer_address = 'Bahnhofstrasse 45, 8001 Zuerich'
    patients[9].employer_contact = 'Peter Aeschbacher'
    patients[9].employer_phone = '+41 44 234 11 11'

    # 2 Patienten mit Zusatzversicherung
    patients[0].supplementary_insurance_name = 'Helsana Completa'
    patients[0].supplementary_insurance_number = 'ZV-2024-001234'

    patients[4].supplementary_insurance_name = 'CSS myFlex Balance'
    patients[4].supplementary_insurance_number = 'ZV-2025-005678'

    # Bevorzugte Sprache bei einigen Patienten
    patients[0].preferred_language = 'Deutsch'
    patients[5].preferred_language = 'Französisch'
    patients[8].preferred_language = 'Italienisch'

    # Festnetz-Nummern
    patients[0].phone = '+41 44 100 20 01'
    patients[3].phone = '+41 52 100 20 04'
    patients[6].phone = '+41 52 100 20 07'

    # Bevorzugter Therapeut
    patients[0].preferred_therapist_id = employees['thomas'].id
    patients[1].preferred_therapist_id = employees['sarah'].id

    # Blacklist-Patient
    patients[14].blacklisted = True
    patients[14].blacklist_reason = 'Mehrfach ohne Absage nicht erschienen. Rechnungen offen.'

    # === Patientendokumente (Platzhalter) ===
    doc_daten = [
        (patients[0].id, 'verordnung', 'Verordnung Physiotherapie KVG', 'verordnung_huber.pdf'),
        (patients[1].id, 'verordnung', 'Verordnung Physiotherapie Schulter', 'verordnung_meier.pdf'),
        (patients[2].id, 'arztbericht', 'OP-Bericht Tibiafraktur', 'op_bericht_keller.pdf'),
        (patients[2].id, 'verordnung', 'Verordnung Physiotherapie UVG', 'verordnung_keller_uvg.pdf'),
        (patients[3].id, 'befund', 'MRI-Befund HWS', 'mri_befund_fischer.pdf'),
    ]
    for pat_id, doc_type, notes, filename in doc_daten:
        db.session.add(PatientDocument(
            patient_id=pat_id,
            filename=filename,
            original_filename=filename,
            file_path=f'/uploads/patients/{pat_id}/{filename}',
            file_size=125000,
            file_type='pdf',
            document_type=doc_type,
            notes=notes,
            uploaded_by_id=created_users['admin'].id
        ))

    # === Allgemeine Kontakte ===
    kontakte = [
        Contact(
            organization_id=org.id,
            company_name='MedTech Service AG',
            first_name='Kurt', last_name='Pfister',
            category='Lieferant',
            address='Technopark 3', city='Zuerich', zip_code='8005',
            phone='+41 44 350 60 60', email='service@medtech-service.ch',
            notes='Wartung aller medizinischen Geraete'
        ),
        Contact(
            organization_id=org.id,
            company_name='Kantonsaerztlicher Dienst Zuerich',
            category='Behoerde',
            address='Stampfenbachstrasse 30', city='Zuerich', zip_code='8090',
            phone='+41 43 259 24 00', email='kad@gd.zh.ch'
        ),
        Contact(
            organization_id=org.id,
            company_name='physioswiss - Schweizer Physiotherapie Verband',
            category='Verband',
            address='Stadthof', city='Sursee', zip_code='6210',
            phone='+41 41 926 69 69', email='info@physioswiss.ch'
        )
    ]
    db.session.add_all(kontakte)

    # === Abgesagte Termine ===
    # Termin 1: Patient hat abgesagt (gestern)
    cancel_date = today - timedelta(days=1)
    if cancel_date.weekday() < 5:  # Nur an Werktagen
        cancel_start = datetime.combine(cancel_date, time(14, 0))
        cancel_end = cancel_start + timedelta(minutes=30)
        appt_cancelled1 = Appointment(
            patient_id=patients[5].id,
            employee_id=thomas_emp.id,
            location_id=loc_zh.id,
            start_time=cancel_start,
            end_time=cancel_end,
            duration_minutes=30,
            status='cancelled',
            appointment_type='treatment',
            title='Physiotherapie',
            cancellation_reason='Patient hat telefonisch abgesagt (Grippe)',
            cancellation_fee=0
        )
        db.session.add(appt_cancelled1)

    # Termin 2: Praxis hat abgesagt (vorgestern), mit Stornogebuehr
    cancel_date2 = today - timedelta(days=2)
    if cancel_date2.weekday() < 5:
        cancel_start2 = datetime.combine(cancel_date2, time(10, 30))
        cancel_end2 = cancel_start2 + timedelta(minutes=30)
        appt_cancelled2 = Appointment(
            patient_id=patients[8].id,
            employee_id=sarah_emp.id,
            location_id=loc_wt.id,
            start_time=cancel_start2,
            end_time=cancel_end2,
            duration_minutes=30,
            status='cancelled',
            appointment_type='treatment',
            title='Physiotherapie',
            cancellation_reason='Patient hat weniger als 24h vorher abgesagt',
            cancellation_fee=30.00
        )
        db.session.add(appt_cancelled2)

    # === No-Show Termin ===
    noshow_date = today - timedelta(days=3)
    if noshow_date.weekday() < 5:
        noshow_start = datetime.combine(noshow_date, time(9, 0))
        noshow_end = noshow_start + timedelta(minutes=30)
        appt_noshow = Appointment(
            patient_id=patients[13].id,
            employee_id=thomas_emp.id,
            location_id=loc_zh.id,
            start_time=noshow_start,
            end_time=noshow_end,
            duration_minutes=30,
            status='no_show',
            appointment_type='treatment',
            title='Physiotherapie',
            notes='Patient nicht erschienen, telefonisch nicht erreichbar'
        )
        db.session.add(appt_noshow)

    # === Warteliste ===
    db.session.add(WaitingList(
        patient_id=patients[10].id,
        template_id=tpl_physio_kvg.id,
        preferred_employee_id=thomas_emp.id,
        preferred_days_json=json.dumps([0, 2, 4]),  # Mo, Mi, Fr
        preferred_times_json=json.dumps(['08:00-12:00']),
        priority=2,
        notes='Patient moechte moeglichst frueh morgens',
        status='waiting'
    ))
    db.session.add(WaitingList(
        patient_id=patients[11].id,
        template_id=tpl_manuell.id,
        preferred_employee_id=sarah_emp.id,
        preferred_days_json=json.dumps([1, 3]),  # Di, Do
        preferred_times_json=json.dumps(['14:00-17:00']),
        priority=1,
        notes='Wartet auf Folgeverordnung vom Arzt',
        status='waiting'
    ))
    db.session.add(WaitingList(
        patient_id=patients[13].id,
        template_id=tpl_physio_kvg.id,
        preferred_days_json=json.dumps([0, 1, 2, 3, 4]),
        preferred_times_json=json.dumps(['08:00-12:00', '13:00-17:00']),
        priority=0,
        notes='Flexible Zeiten, kein bevorzugter Therapeut',
        status='waiting'
    ))

    # === Behandlungsplan: Therapieziele ===
    # 3 Ziele fuer Serie 1 (Max Huber, Kreuzschmerz)
    ziel1 = TherapyGoal(
        series_id=serien[0].id,
        patient_id=patients[0].id,
        description='Schmerzreduktion auf NPRS ≤ 3',
        target_value='NPRS ≤ 3',
        current_value='NPRS 4',
        achievement_percent=60,
        status='in_progress'
    )
    ziel2 = TherapyGoal(
        series_id=serien[0].id,
        patient_id=patients[0].id,
        description='Volle Beweglichkeit LWS',
        target_value='ROM Flexion 60°, Extension 25°',
        current_value='Flexion 45°, Extension 15°',
        achievement_percent=40,
        status='in_progress'
    )
    ziel3 = TherapyGoal(
        series_id=serien[0].id,
        patient_id=patients[0].id,
        description='Rückkehr zur Arbeit',
        target_value='Volle Arbeitsfähigkeit',
        current_value='50% Arbeitsfähigkeit',
        achievement_percent=20,
        status='open'
    )
    db.session.add_all([ziel1, ziel2, ziel3])

    # === Behandlungsplan: NPRS-Messungen fuer Max Huber ===
    messung1 = Measurement(
        patient_id=patients[0].id,
        series_id=serien[0].id,
        measurement_type='nprs',
        name='NPRS (Schmerzskala)',
        value_json=json.dumps({'value': 7}),
        unit='Punkte',
        measured_at=datetime.combine(today - timedelta(days=14), time(8, 30)),
        measured_by_id=thomas_emp.id
    )
    messung2 = Measurement(
        patient_id=patients[0].id,
        series_id=serien[0].id,
        measurement_type='nprs',
        name='NPRS (Schmerzskala)',
        value_json=json.dumps({'value': 6}),
        unit='Punkte',
        measured_at=datetime.combine(today - timedelta(days=9), time(9, 0)),
        measured_by_id=thomas_emp.id
    )
    messung3 = Measurement(
        patient_id=patients[0].id,
        series_id=serien[0].id,
        measurement_type='nprs',
        name='NPRS (Schmerzskala)',
        value_json=json.dumps({'value': 4}),
        unit='Punkte',
        measured_at=datetime.combine(today - timedelta(days=4), time(8, 30)),
        measured_by_id=thomas_emp.id
    )
    messung4 = Measurement(
        patient_id=patients[0].id,
        series_id=serien[0].id,
        measurement_type='nprs',
        name='NPRS (Schmerzskala)',
        value_json=json.dumps({'value': 3}),
        unit='Punkte',
        measured_at=datetime.combine(today, time(8, 30)),
        measured_by_id=thomas_emp.id
    )
    db.session.add_all([messung1, messung2, messung3, messung4])

    # === Behandlungsplan: Meilensteine fuer Serie 1 ===
    ms1 = Milestone(
        series_id=serien[0].id,
        patient_id=patients[0].id,
        name='Schmerzfrei im Alltag',
        description='Patient kann Alltagsaktivitäten ohne relevante Schmerzen durchführen',
        target_date=today - timedelta(days=3),
        achieved_date=today - timedelta(days=3),
        criteria='NPRS ≤ 3 bei Alltagsbelastung',
        status='achieved',
        sort_order=0
    )
    ms2 = Milestone(
        series_id=serien[0].id,
        patient_id=patients[0].id,
        name='Sport möglich',
        description='Patient kann leichte sportliche Aktivitäten aufnehmen',
        target_date=today + timedelta(days=14),
        criteria='Volle ROM, NPRS ≤ 2 bei Belastung',
        status='open',
        sort_order=1
    )
    db.session.add_all([ms1, ms2])

    # === Behandlungsplan: Heilungsphasen fuer Serie 1 ===
    phase_initial = HealingPhase(
        series_id=serien[0].id,
        phase_type='initial',
        start_date=today - timedelta(days=14),
        end_date=today - timedelta(days=7),
        notes='Schmerzlinderung und Entzündungshemmung'
    )
    phase_behandlung = HealingPhase(
        series_id=serien[0].id,
        phase_type='treatment',
        start_date=today - timedelta(days=7),
        notes='Aktive Mobilisation und Kräftigung'
    )
    db.session.add_all([phase_initial, phase_behandlung])

    # Heilungsphase auf der Serie setzen
    serien[0].healing_phase = 'treatment'

    # === Behandlungsplan: SOAP-Notes fuer 3 abgeschlossene Termine ===
    # Termine der Serie 1 (Max Huber) updaten
    serie1_termine = Appointment.query.filter_by(series_id=serien[0].id).order_by(Appointment.start_time).limit(3).all()
    soap_daten = [
        {
            'soap_subjective': 'Patient berichtet über starke Schmerzen im unteren Rücken, besonders beim Bücken. Schmerzausstrahlung ins linke Bein. Schlaf gestört.',
            'soap_objective': 'LWS Flexion eingeschränkt (ca. 40°), Extension schmerzhaft. Druckdolenz L4/L5. Lasègue links positiv bei 60°. NPRS 7/10.',
            'soap_assessment': 'Akute Lumbalgie mit radikulärer Symptomatik L5 links. Deutliche Funktionseinschränkung.',
            'soap_plan': 'Manuelle Mobilisation L4/L5, Nervenmobilisation, Edukation. Nächster Termin in 2 Tagen.',
            'status': 'completed'
        },
        {
            'soap_subjective': 'Patient gibt leichte Besserung an. Beinschmerz hat nachgelassen. Schlaf etwas besser. NPRS 6/10.',
            'soap_objective': 'LWS Flexion verbessert (ca. 50°). Lasègue links negativ. Muskeltonus paravertebral noch erhöht.',
            'soap_assessment': 'Positive Entwicklung. Radikuläre Symptomatik rückläufig. Beweglichkeit verbessert sich.',
            'soap_plan': 'Weiter manuelle Therapie, Beginn aktive Übungen. Heimübungsprogramm: 3x täglich Beckenkippen.',
            'status': 'completed'
        },
        {
            'soap_subjective': 'Deutliche Verbesserung. Kann wieder normal gehen. Nur noch Beschwerden bei längerem Sitzen. NPRS 4/10.',
            'soap_objective': 'LWS Flexion fast normalisiert (55°). Kein radikuläres Zeichen. Kernstabilität noch defizitär.',
            'soap_assessment': 'Guter Fortschritt. Übergang in aktive Rehabilitationsphase möglich.',
            'soap_plan': 'Schwerpunkt auf Kernstabilität und Haltungsschulung. MTT-Programm aufbauen. Arbeitsplatzergonomie besprechen.',
            'status': 'completed'
        }
    ]
    for i, termin in enumerate(serie1_termine):
        if i < len(soap_daten):
            termin.soap_subjective = soap_daten[i]['soap_subjective']
            termin.soap_objective = soap_daten[i]['soap_objective']
            termin.soap_assessment = soap_daten[i]['soap_assessment']
            termin.soap_plan = soap_daten[i]['soap_plan']
            termin.status = soap_daten[i]['status']

    db.session.commit()

    # === Einstellungen: Demo-Daten ===
    _seed_settings_demo_data(org)


def _seed_settings_demo_data(org):
    """Erstellt Demo-Daten fuer den Einstellungen-Bereich"""

    # Standard-Systemeinstellungen
    default_settings = [
        ('app_language', 'de', 'string', 'general'),
        ('timezone', 'Europe/Zurich', 'string', 'general'),
        ('date_format', 'DD.MM.YYYY', 'string', 'general'),
        ('currency', 'CHF', 'string', 'general'),
        ('calendar_time_grid', '15', 'integer', 'calendar'),
        ('calendar_day_start', '07:00', 'string', 'calendar'),
        ('calendar_day_end', '19:00', 'string', 'calendar'),
        ('calendar_default_duration', '30', 'integer', 'calendar'),
        ('email_sender_address', 'praxis@omnia-health.ch', 'string', 'email'),
        ('email_sender_name', 'OMNIA Health Services AG', 'string', 'email'),
        ('email_auto_reminder', 'true', 'boolean', 'email'),
        ('email_reminder_hours', '24', 'integer', 'email'),
        ('billing_default_model', 'tiers_garant', 'string', 'billing'),
        ('billing_payment_term', '30', 'integer', 'billing'),
        ('billing_invoice_format', 'RE-{JAHR}-{NR}', 'string', 'billing'),
        ('billing_next_invoice_number', '1', 'integer', 'billing'),
        ('dunning_1_days', '30', 'integer', 'billing'),
        ('dunning_2_days', '60', 'integer', 'billing'),
        ('dunning_3_days', '90', 'integer', 'billing'),
        ('dunning_1_fee', '0', 'float', 'billing'),
        ('dunning_2_fee', '20', 'float', 'billing'),
        ('dunning_3_fee', '50', 'float', 'billing'),
        ('dunning_1_text', 'Wir erlauben uns, Sie freundlich an die ausstehende Zahlung zu erinnern. Bitte überweisen Sie den offenen Betrag innert 10 Tagen.', 'string', 'billing'),
        ('dunning_2_text', 'Trotz unserer Erinnerung ist die untenstehende Rechnung noch nicht beglichen worden. Wir bitten Sie, den Betrag umgehend zu überweisen.', 'string', 'billing'),
        ('dunning_3_text', 'Dies ist unsere letzte Mahnung. Sollte der Betrag nicht innert 10 Tagen bei uns eingehen, werden wir rechtliche Schritte einleiten.', 'string', 'billing'),
    ]

    for key, value, value_type, category in default_settings:
        setting = SystemSetting(
            organization_id=org.id,
            key=key,
            value=value,
            value_type=value_type,
            category=category
        )
        db.session.add(setting)

    # KI-Einstellungen
    import json
    ai_settings = AISettings(
        organization_id=org.id,
        intensity_level='normal',
        budget_monthly=100.0,
        budget_used=23.50,
        features_enabled_json=json.dumps({
            'chat_assistant': True,
            'auto_appointment_suggestions': True,
            'proactive_hints': True,
            'documentation_suggestions': True
        })
    )
    db.session.add(ai_settings)

    # E-Mail-Vorlagen
    email_templates = [
        EmailTemplate(
            organization_id=org.id,
            name='Terminerinnerung Standard',
            template_type='reminder',
            subject='Erinnerung: Ihr Termin am {termin_datum}',
            body_html='<p>Guten Tag {patient_name},</p><p>Wir möchten Sie an Ihren Termin am <strong>{termin_datum}</strong> um <strong>{termin_zeit}</strong> bei {therapeut_name} erinnern.</p><p>Bitte melden Sie sich falls Sie den Termin nicht wahrnehmen können.</p><p>Freundliche Grüsse<br>{praxis_name}<br>{praxis_telefon}</p>',
            placeholders_json=json.dumps(['{patient_name}', '{termin_datum}', '{termin_zeit}', '{therapeut_name}', '{praxis_name}', '{praxis_telefon}'])
        ),
        EmailTemplate(
            organization_id=org.id,
            name='Terminbestätigung Standard',
            template_type='confirmation',
            subject='Terminbestätigung: {termin_datum} um {termin_zeit}',
            body_html='<p>Guten Tag {patient_name},</p><p>Hiermit bestätigen wir Ihren Termin:</p><ul><li><strong>Datum:</strong> {termin_datum}</li><li><strong>Uhrzeit:</strong> {termin_zeit}</li><li><strong>Therapeut/in:</strong> {therapeut_name}</li></ul><p>Wir freuen uns auf Sie!</p><p>Freundliche Grüsse<br>{praxis_name}</p>',
            placeholders_json=json.dumps(['{patient_name}', '{termin_datum}', '{termin_zeit}', '{therapeut_name}', '{praxis_name}'])
        ),
        EmailTemplate(
            organization_id=org.id,
            name='Recall Standard',
            template_type='recall',
            subject='Vereinbaren Sie Ihren nächsten Termin',
            body_html='<p>Guten Tag {patient_name},</p><p>Ihre letzte Behandlungsserie bei uns liegt bereits einige Zeit zurück. Wir möchten Sie freundlich daran erinnern, bei Bedarf einen neuen Termin zu vereinbaren.</p><p>Rufen Sie uns an unter {praxis_telefon} oder antworten Sie direkt auf diese E-Mail.</p><p>Freundliche Grüsse<br>{praxis_name}</p>',
            placeholders_json=json.dumps(['{patient_name}', '{praxis_name}', '{praxis_telefon}'])
        ),
    ]
    db.session.add_all(email_templates)

    # Druckvorlage: Rechnung
    print_template = PrintTemplate(
        organization_id=org.id,
        name='Rechnung Standard',
        template_type='invoice',
        body_html="""<html>
<head><style>
body { font-family: Arial, sans-serif; font-size: 10pt; }
.header { display: flex; justify-content: space-between; margin-bottom: 30px; }
.patient-info { margin-bottom: 20px; }
.invoice-info { text-align: right; margin-bottom: 20px; }
table { width: 100%; border-collapse: collapse; margin: 20px 0; }
th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
th { background: #f5f5f5; }
.total { font-weight: bold; text-align: right; }
.footer { margin-top: 40px; font-size: 9pt; color: #666; border-top: 1px solid #ccc; padding-top: 10px; }
</style></head>
<body>
<div class="header">
    <div>{praxis_name}<br>{praxis_adresse}<br>ZSR: {praxis_zsr} | GLN: {praxis_gln}</div>
    <div class="invoice-info">Rechnung Nr. {rechnungsnummer}<br>Datum: {rechnungsdatum}<br>Fällig: {faelligkeitsdatum}</div>
</div>
<div class="patient-info">
    <strong>{patient_name}</strong><br>{patient_adresse}
</div>
<p>Sehr geehrte/r {patient_name},</p>
<p>Für die erbrachten Leistungen erlauben wir uns, Ihnen folgenden Betrag in Rechnung zu stellen:</p>
<table>
    <tr><th>Pos.</th><th>Beschreibung</th><th>Menge</th><th>Betrag</th></tr>
    <tr><td colspan="4">{rechnungspositionen}</td></tr>
</table>
<p class="total">Total: CHF {betrag_total}</p>
<p>Zahlbar innert {zahlungsziel_tage} Tagen.</p>
<div class="footer">{praxis_name} | {praxis_adresse} | {praxis_telefon} | {praxis_email}</div>
</body></html>"""
    )
    db.session.add(print_template)

    # Rollen-Berechtigungen
    modules = ['dashboard', 'kalender', 'patienten', 'mitarbeiter', 'behandlung',
               'abrechnung', 'produkte', 'ressourcen', 'adressen', 'einstellungen']
    actions = ['lesen', 'erstellen', 'bearbeiten', 'loeschen']

    # Therapeut: Lesen ueberall, Bearbeiten bei Patienten/Behandlung/Kalender
    therapeut_rechte = {
        'dashboard': ['lesen'],
        'kalender': ['lesen', 'erstellen', 'bearbeiten'],
        'patienten': ['lesen', 'erstellen', 'bearbeiten'],
        'mitarbeiter': ['lesen'],
        'behandlung': ['lesen', 'erstellen', 'bearbeiten'],
        'abrechnung': ['lesen'],
        'produkte': ['lesen'],
        'ressourcen': ['lesen'],
        'adressen': ['lesen', 'erstellen', 'bearbeiten'],
        'einstellungen': [],
    }

    # Empfang: Lesen ueberall, Erstellen bei Kalender/Patienten
    empfang_rechte = {
        'dashboard': ['lesen'],
        'kalender': ['lesen', 'erstellen', 'bearbeiten'],
        'patienten': ['lesen', 'erstellen', 'bearbeiten'],
        'mitarbeiter': ['lesen'],
        'behandlung': ['lesen'],
        'abrechnung': ['lesen', 'erstellen'],
        'produkte': ['lesen'],
        'ressourcen': ['lesen', 'erstellen'],
        'adressen': ['lesen', 'erstellen', 'bearbeiten'],
        'einstellungen': [],
    }

    for module in modules:
        for action in actions:
            # Therapeut
            db.session.add(Permission(
                role='therapist',
                module=module,
                action=action,
                is_allowed=action in therapeut_rechte.get(module, [])
            ))
            # Empfang
            db.session.add(Permission(
                role='reception',
                module=module,
                action=action,
                is_allowed=action in empfang_rechte.get(module, [])
            ))

    db.session.commit()


app = create_app()
