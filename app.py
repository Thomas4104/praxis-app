import os
import json
from datetime import datetime, timedelta, date, time
from flask import Flask
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from models import db, Organization, Location, User, Employee, WorkSchedule, Patient, \
    InsuranceProvider, Doctor, Resource, TreatmentSeriesTemplate, TreatmentSeries, \
    Appointment, AISettings
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

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)

    # CSRF-Exempt fuer API-Routen
    csrf.exempt(dashboard_bp)

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
            'tageszeit': tageszeit
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

    # === KI-Einstellungen ===
    db.session.add(AISettings(
        organization_id=org.id,
        intensity_level='medium',
        budget_monthly=100.0,
        features_enabled_json=json.dumps({
            'chat': True,
            'auto_dokumentation': False,
            'terminvorschlaege': True,
            'proaktive_hinweise': False
        })
    ))

    db.session.commit()


app = create_app()
