import os
import json
from datetime import datetime, timedelta, date, time
from flask import Flask
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from models import db, Organization, Location, User, Employee, WorkSchedule, Patient, \
    InsuranceProvider, Doctor, Resource, TreatmentSeriesTemplate, TreatmentSeries, \
    Appointment, AISettings, Product, MaintenanceRecord, BankAccount, Holiday, TaxPointValue, \
    Certificate, AbsenceQuota, Absence, PatientDocument, Contact, WaitingList, \
    TherapyGoal, Milestone, Measurement, HealingPhase, \
    SystemSetting, EmailTemplate, PrintTemplate, Permission, \
    CostApproval, CostApprovalItem, Task, TaskComment, \
    Invoice, InvoiceItem, Payment, DunningRecord, EmailFolder, Email, \
    Account, JournalEntry, JournalEntryLine, CreditorInvoice, FixedAsset, CostCenter, PeriodLock, \
    EmployeeContract, EmployeeSalary, EmployeeChild, PayrollRun, Payslip, \
    TimeEntry, OvertimeAccount, Expense, SavedReport, \
    SubscriptionTemplate, Subscription, FitnessVisit, \
    PortalAccount, PortalMessage, OnlineBookingRequest
from config import config


login_manager = LoginManager()
migrate = Migrate()
csrf = CSRFProtect()


def create_app(config_name=None):
    """App-Factory: Erstellt und konfiguriert die Flask-Anwendung"""
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'default')

    app = Flask(__name__)
    app.config.from_object(config.get(config_name, config['default']))

    # Erweiterungen initialisieren
    db.init_app(app)
    migrate.init_app(app, db)
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
    from blueprints.cost_approvals import cost_approvals_bp
    from blueprints.tasks import tasks_bp
    from blueprints.billing import billing_bp
    from blueprints.mailing import mailing_bp
    from blueprints.accounting import accounting_bp
    from blueprints.hr import hr_bp
    from blueprints.reporting import reporting_bp
    from blueprints.fitness import fitness_bp
    from blueprints.portal import portal_bp

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
    app.register_blueprint(cost_approvals_bp, url_prefix='/cost-approvals')
    app.register_blueprint(tasks_bp, url_prefix='/tasks')
    app.register_blueprint(billing_bp, url_prefix='/billing')
    app.register_blueprint(mailing_bp, url_prefix='/mailing')
    app.register_blueprint(accounting_bp, url_prefix='/accounting')
    app.register_blueprint(hr_bp, url_prefix='/hr')
    app.register_blueprint(reporting_bp, url_prefix='/reporting')
    app.register_blueprint(fitness_bp, url_prefix='/fitness')
    app.register_blueprint(portal_bp, url_prefix='/portal')

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
    csrf.exempt(cost_approvals_bp)
    csrf.exempt(tasks_bp)
    csrf.exempt(billing_bp)
    csrf.exempt(mailing_bp)
    csrf.exempt(accounting_bp)
    csrf.exempt(hr_bp)
    csrf.exempt(reporting_bp)
    csrf.exempt(fitness_bp)
    csrf.exempt(portal_bp)

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
        if app.config.get('DEBUG'):
            seed_demo_data()

    # CLI-Befehl fuer Demo-Daten
    @app.cli.command('seed-demo')
    def seed_demo_command():
        """Demo-Daten erstellen (nur fuer Entwicklung/Test)"""
        seed_demo_data()
        print('Demo-Daten erstellt.')

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
        # Standard-Dashboard-Konfiguration pro Rolle
        dashboard_defaults = {
            'admin': json.dumps(['ki_tagesuebersicht', 'heutige_termine', 'offene_aufgaben',
                                 'patientenverlauf', 'umsatzuebersicht', 'geburtstage',
                                 'schnellaktionen', 'auslastung', 'offene_rechnungen',
                                 'ungelesene_emails', 'absenzen']),
            'therapist': json.dumps(['ki_tagesuebersicht', 'heutige_termine', 'offene_aufgaben',
                                     'patientenverlauf', 'schnellaktionen', 'auslastung']),
            'reception': json.dumps(['heutige_termine', 'offene_aufgaben', 'ungelesene_emails',
                                     'schnellaktionen', 'geburtstage', 'absenzen'])
        }
        user = User(
            organization_id=org.id,
            username=ud['username'],
            first_name=ud['first_name'],
            last_name=ud['last_name'],
            name=f"{ud['first_name']} {ud['last_name']}",
            email=ud['email'],
            role=ud['role'],
            dashboard_config_json=dashboard_defaults.get(ud['role'], dashboard_defaults['therapist'])
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

    # === Patientenportal: Demo-Daten ===
    portal_max = PortalAccount(
        patient_id=patients[0].id,
        email='max.huber@gmail.com',
        is_active=True,
        is_verified=True
    )
    portal_max.set_password('portal123')

    portal_sandra = PortalAccount(
        patient_id=patients[1].id,
        email='sandra.meier@bluewin.ch',
        is_active=True,
        is_verified=True
    )
    portal_sandra.set_password('portal123')

    portal_lukas = PortalAccount(
        patient_id=patients[4].id,
        email='lukas.z@gmail.com',
        is_active=False,
        is_verified=False
    )
    portal_lukas.set_password('portal123')

    db.session.add_all([portal_max, portal_sandra, portal_lukas])
    db.session.flush()

    # Portal-Nachrichten
    pmsg1 = PortalMessage(
        patient_id=patients[0].id,
        sender_type='patient',
        sender_name='Max Huber',
        subject='Frage zu meinem nächsten Termin',
        body='Guten Tag, ich wollte fragen ob es möglich wäre, meinen Termin am Donnerstag um eine Stunde zu verschieben? Vielen Dank.',
        created_at=datetime(2026, 3, 20, 14, 30)
    )
    pmsg2 = PortalMessage(
        patient_id=patients[0].id,
        sender_type='practice',
        sender_name='OMNIA Praxisteam',
        subject='Re: Frage zu meinem nächsten Termin',
        body='Guten Tag Herr Huber, selbstverständlich können wir Ihren Termin verschieben. Wir haben Sie auf 10:00 Uhr umgebucht. Freundliche Grüsse, Ihr OMNIA Praxisteam.',
        read_at=datetime(2026, 3, 20, 16, 0),
        created_at=datetime(2026, 3, 20, 15, 45)
    )
    pmsg3 = PortalMessage(
        patient_id=patients[1].id,
        sender_type='practice',
        sender_name='OMNIA Praxisteam',
        subject='Erinnerung: Verordnung einreichen',
        body='Guten Tag Frau Meier, wir möchten Sie daran erinnern, dass wir für die Fortsetzung Ihrer Behandlung eine neue Verordnung benötigen. Bitte bringen Sie diese zum nächsten Termin mit. Freundliche Grüsse, Ihr OMNIA Praxisteam.',
        created_at=datetime(2026, 3, 21, 9, 0)
    )
    db.session.add_all([pmsg1, pmsg2, pmsg3])

    # Online-Buchungsanfrage (pending)
    buchung1 = OnlineBookingRequest(
        patient_id=patients[0].id,
        template_id=tpl_physio_kvg.id,
        preferred_employee_id=employees['thomas'].id,
        requested_date=date(2026, 4, 2),
        requested_time=time(10, 0),
        status='pending',
        notes='Wenn möglich am Vormittag.',
        created_at=datetime(2026, 3, 22, 11, 30)
    )
    db.session.add(buchung1)

    # 2 Dokumente als portal_visible markieren
    portal_docs = PatientDocument.query.filter_by(patient_id=patients[0].id).limit(2).all()
    for doc in portal_docs:
        doc.portal_visible = True

    db.session.commit()

    # === Gutsprachen: Demo-Daten ===
    _seed_gutsprachen_demo_data(org, patients, serien, insurances, doctors, employees, created_users)

    # === Abrechnung: Demo-Daten ===
    _seed_billing_demo_data(org, patients, serien, insurances, employees, created_users)

    # === Einstellungen: Demo-Daten ===
    _seed_settings_demo_data(org, patients)

    # === Finanzbuchhaltung: Demo-Daten ===
    try:
        seed_accounting_data(org, loc_zh, loc_wt, created_users)
    except Exception as e:
        print(f'Fehler bei Finanzbuchhaltung-Demo-Daten: {e}')
        import traceback
        traceback.print_exc()

    # === HR & Lohnbuchhaltung: Demo-Daten ===
    try:
        _seed_hr_demo_data(org, employees, created_users)
    except Exception as e:
        print(f'Fehler bei HR-Demo-Daten: {e}')
        import traceback
        traceback.print_exc()


def _seed_billing_demo_data(org, patients, serien, insurances, employees, created_users):
    """Erstellt Demo-Daten fuer Abrechnung: Rechnungen, Zahlungen, Mahnungen"""

    today = date.today()

    # Taxpunktwert fuer Berechnungen
    tp_wert_312 = 1.00  # TarReha / Tarif 312
    tp_wert_311 = 0.89  # Tarif 311 (UVG)
    tp_physio = 1.00    # Physiotarif

    # === Rechnung 1: Bezahlt (Serie 4 - Maria Fischer, Manuelle Therapie, abgeschlossen) ===
    inv1 = Invoice(
        organization_id=org.id,
        series_id=serien[3].id,
        patient_id=patients[3].id,
        insurance_provider_id=insurances[0].id,
        invoice_number='RE-2026-0001',
        amount_total=540.00,
        amount_paid=540.00,
        amount_open=0.00,
        status='paid',
        billing_type='KVG',
        billing_model='tiers_garant',
        tax_point_value=tp_physio,
        due_date=today - timedelta(days=20),
        sent_at=datetime(2026, 2, 20, 10, 0),
        sent_via='email',
        paid_at=datetime(2026, 3, 5, 14, 30),
        created_at=datetime(2026, 2, 18, 9, 0)
    )
    db.session.add(inv1)
    db.session.flush()

    # Positionen fuer Rechnung 1: 6x Manuelle Therapie 45 Min
    db.session.add(InvoiceItem(
        invoice_id=inv1.id, position=1,
        tariff_code='7302', description='Manuelle Therapie (45 Min.)',
        quantity=6, tax_points=90.0, tax_point_value=tp_physio,
        amount=540.00, vat_rate=0.0, vat_amount=0.0
    ))

    # Zahlung fuer Rechnung 1
    db.session.add(Payment(
        invoice_id=inv1.id, amount=540.00,
        payment_date=date(2026, 3, 5),
        payment_method='bank_transfer',
        reference='QRR-2026-0001-001'
    ))

    # === Rechnung 2: Gesendet, offen (Serie 1 - Max Huber, KVG) ===
    inv2 = Invoice(
        organization_id=org.id,
        series_id=serien[0].id,
        patient_id=patients[0].id,
        insurance_provider_id=insurances[0].id,
        invoice_number='RE-2026-0002',
        amount_total=270.00,
        amount_paid=0.00,
        amount_open=270.00,
        status='sent',
        billing_type='KVG',
        billing_model='tiers_garant',
        tax_point_value=tp_wert_312,
        due_date=today + timedelta(days=20),
        sent_at=datetime.now() - timedelta(days=5),
        sent_via='print',
        created_at=datetime.now() - timedelta(days=7)
    )
    db.session.add(inv2)
    db.session.flush()

    # Positionen: ca. 5-6 Sitzungen Physio KVG 30 Min (voruebergehend, Serie laeuft noch)
    # Zwischenabrechnung: 5 Sitzungen abgerechnet
    # Hinweis: Wir rechnen weniger ab als die volle Serie
    db.session.add(InvoiceItem(
        invoice_id=inv2.id, position=1,
        tariff_code='7301', description='Physiotherapie KVG (30 Min.)',
        quantity=5, tax_points=48.0, tax_point_value=tp_wert_312,
        amount=240.00, vat_rate=0.0, vat_amount=0.0
    ))
    db.session.add(InvoiceItem(
        invoice_id=inv2.id, position=2,
        tariff_code='7320', description='Befundbericht an Arzt',
        quantity=1, tax_points=30.0, tax_point_value=tp_wert_312,
        amount=30.00, vat_rate=0.0, vat_amount=0.0
    ))

    # === Rechnung 3: Ueberfaellig (Dummy-Patient Daniel Schmid) ===
    inv3 = Invoice(
        organization_id=org.id,
        patient_id=patients[6].id,
        insurance_provider_id=insurances[2].id,
        invoice_number='RE-2026-0003',
        amount_total=180.00,
        amount_paid=0.00,
        amount_open=180.00,
        status='overdue',
        billing_type='KVG',
        billing_model='tiers_garant',
        tax_point_value=tp_wert_312,
        due_date=today - timedelta(days=35),
        sent_at=datetime.now() - timedelta(days=50),
        sent_via='email',
        dunning_level=1,
        dunning_1_date=today - timedelta(days=5),
        created_at=datetime.now() - timedelta(days=55)
    )
    db.session.add(inv3)
    db.session.flush()

    db.session.add(InvoiceItem(
        invoice_id=inv3.id, position=1,
        tariff_code='7301', description='Physiotherapie KVG (30 Min.)',
        quantity=3, tax_points=48.0, tax_point_value=tp_wert_312,
        amount=144.00, vat_rate=0.0, vat_amount=0.0
    ))
    db.session.add(InvoiceItem(
        invoice_id=inv3.id, position=2,
        tariff_code='7310', description='Erstbefundaufnahme',
        quantity=1, tax_points=36.0, tax_point_value=tp_wert_312,
        amount=36.00, vat_rate=0.0, vat_amount=0.0
    ))

    # Mahnungshistorie fuer Rechnung 3
    db.session.add(DunningRecord(
        invoice_id=inv3.id,
        dunning_level=1,
        dunning_date=today - timedelta(days=5),
        dunning_fee=0.0,
        dunning_text='Wir erlauben uns, Sie freundlich an die ausstehende Zahlung zu erinnern. Bitte überweisen Sie den offenen Betrag innert 10 Tagen.',
        sent_via='email'
    ))

    # === Rechnung 4: Teilbezahlt (Petra Schneider) ===
    inv4 = Invoice(
        organization_id=org.id,
        patient_id=patients[7].id,
        insurance_provider_id=insurances[1].id,
        invoice_number='RE-2026-0004',
        amount_total=405.00,
        amount_paid=200.00,
        amount_open=205.00,
        status='partially_paid',
        billing_type='KVG',
        billing_model='tiers_garant',
        tax_point_value=tp_wert_312,
        due_date=today + timedelta(days=5),
        sent_at=datetime.now() - timedelta(days=20),
        sent_via='print',
        created_at=datetime.now() - timedelta(days=22)
    )
    db.session.add(inv4)
    db.session.flush()

    db.session.add(InvoiceItem(
        invoice_id=inv4.id, position=1,
        tariff_code='7301', description='Physiotherapie KVG (30 Min.)',
        quantity=8, tax_points=48.0, tax_point_value=tp_wert_312,
        amount=384.00, vat_rate=0.0, vat_amount=0.0
    ))
    db.session.add(InvoiceItem(
        invoice_id=inv4.id, position=2,
        tariff_code='7320', description='Befundbericht an Arzt',
        quantity=1, tax_points=21.0, tax_point_value=tp_wert_312,
        amount=21.00, vat_rate=0.0, vat_amount=0.0
    ))

    # Teilzahlung
    db.session.add(Payment(
        invoice_id=inv4.id, amount=200.00,
        payment_date=today - timedelta(days=10),
        payment_method='bank_transfer',
        reference='QRR-2026-0004-001',
        notes='Teilzahlung Patient'
    ))

    # === Rechnung 5: Entwurf (Serie 3 - Bruno Keller, UVG) ===
    inv5 = Invoice(
        organization_id=org.id,
        series_id=serien[2].id,
        patient_id=patients[2].id,
        insurance_provider_id=insurances[2].id,
        invoice_number='RE-2026-0005',
        amount_total=384.48,
        amount_paid=0.00,
        amount_open=384.48,
        status='draft',
        billing_type='UVG',
        billing_model='tiers_payant',
        tax_point_value=tp_wert_311,
        due_date=today + timedelta(days=30),
        created_at=datetime.now() - timedelta(days=1)
    )
    db.session.add(inv5)
    db.session.flush()

    # UVG-Positionen mit Tarif 311
    db.session.add(InvoiceItem(
        invoice_id=inv5.id, position=1,
        tariff_code='7311', description='Physiotherapie UVG (30 Min.)',
        quantity=9, tax_points=48.0, tax_point_value=tp_wert_311,
        amount=384.48, vat_rate=0.0, vat_amount=0.0
    ))

    # Zweite Zahlung (fuer Rechnung 1 - falls Anzahlung und Rest)
    db.session.add(Payment(
        invoice_id=inv1.id, amount=0.00,
        payment_date=date(2026, 2, 25),
        payment_method='esr_qr',
        reference='ESR-Kontrolle',
        notes='Automatische Zuordnung via ESR-Referenz (Nullbetrag-Pruefung)'
    ))

    # Naechste Rechnungsnummer auf 6 setzen
    next_nr_setting = SystemSetting.query.filter_by(
        organization_id=org.id, key='billing_next_invoice_number'
    ).first()
    if next_nr_setting:
        next_nr_setting.value = '6'

    db.session.commit()


def _seed_gutsprachen_demo_data(org, patients, serien, insurances, doctors, employees, created_users):
    """Erstellt Demo-Daten fuer Gutsprachen und Aufgaben"""

    # === 3 Gutsprachen ===

    # 1. Bewilligt (Serie 1, Max Huber, 9 Sitzungen bewilligt)
    gs1 = CostApproval(
        organization_id=org.id,
        approval_number='GS-2026-0001',
        series_id=serien[0].id,
        patient_id=patients[0].id,
        insurance_provider_id=insurances[0].id,
        doctor_id=doctors[0].id,
        therapist_id=employees['thomas'].id,
        status='approved',
        requested_date=date.today() - timedelta(days=12),
        sent_date=date.today() - timedelta(days=12),
        response_date=date.today() - timedelta(days=8),
        valid_until=date.today() + timedelta(days=90),
        requested_sessions=9,
        approved_sessions=9,
        total_amount=432.0,
        approved_amount=432.0,
        diagnosis_code='M54.5',
        diagnosis_text='Kreuzschmerz',
        prescription_date=date.today() - timedelta(days=14),
        prescription_type='erst',
        justification='Patient leidet seit 3 Wochen an akuten Kreuzschmerzen mit Ausstrahlung ins linke Bein. '
                       'Konservative Therapie mit 9 Sitzungen Physiotherapie indiziert.',
        response_notes='Gutsprache bewilligt. 9 Sitzungen genehmigt.'
    )
    db.session.add(gs1)
    db.session.flush()

    # Positionen fuer GS1
    db.session.add(CostApprovalItem(
        cost_approval_id=gs1.id,
        tariff_code='7301',
        description='Physiotherapie Einzelbehandlung',
        quantity=9,
        amount=48.0
    ))

    # 2. Gesendet, ausstehend (Serie 2, Sandra Meier)
    gs2 = CostApproval(
        organization_id=org.id,
        approval_number='GS-2026-0002',
        series_id=serien[1].id,
        patient_id=patients[1].id,
        insurance_provider_id=insurances[0].id,
        doctor_id=doctors[1].id,
        therapist_id=employees['sarah'].id,
        status='sent',
        requested_date=date.today() - timedelta(days=5),
        sent_date=date.today() - timedelta(days=5),
        requested_sessions=9,
        total_amount=432.0,
        diagnosis_code='M75.1',
        diagnosis_text='Impingement-Syndrom Schulter',
        prescription_date=date.today() - timedelta(days=7),
        prescription_type='erst',
        justification='Impingement-Syndrom der rechten Schulter. Einschraenkung der Abduktion und Aussenrotation. '
                       '9 Sitzungen Physiotherapie zur Mobilisation und Kraeftigung beantragt.'
    )
    db.session.add(gs2)
    db.session.flush()

    db.session.add(CostApprovalItem(
        cost_approval_id=gs2.id,
        tariff_code='7301',
        description='Physiotherapie Einzelbehandlung',
        quantity=9,
        amount=48.0
    ))

    # 3. Abgelehnt (Serie 3, mit Ablehnungsgrund)
    gs3 = CostApproval(
        organization_id=org.id,
        approval_number='GS-2026-0003',
        series_id=serien[2].id,
        patient_id=patients[2].id,
        insurance_provider_id=insurances[2].id,
        doctor_id=doctors[4].id,
        therapist_id=employees['thomas'].id,
        status='rejected',
        requested_date=date.today() - timedelta(days=20),
        sent_date=date.today() - timedelta(days=20),
        response_date=date.today() - timedelta(days=15),
        requested_sessions=18,
        total_amount=864.0,
        diagnosis_code='S82.1',
        diagnosis_text='Fraktur proximale Tibia',
        prescription_date=date.today() - timedelta(days=21),
        prescription_type='erst',
        justification='Zustand nach operativ versorgter proximaler Tibiafraktur. 18 Sitzungen Physiotherapie fuer '
                       'Mobilisation, Kraeftigung und Gangschulung beantragt.',
        rejection_reason='Angefragte Anzahl Sitzungen uebersteigt den bewilligungsfreien Rahmen. '
                         'Bitte Antrag mit max. 9 Sitzungen (Erstverordnung) einreichen.',
        response_notes='Ablehnung wegen ueberschrittener Anzahl. Neuer Antrag moeglich.'
    )
    db.session.add(gs3)
    db.session.flush()

    db.session.add(CostApprovalItem(
        cost_approval_id=gs3.id,
        tariff_code='7301',
        description='Physiotherapie Einzelbehandlung',
        quantity=18,
        amount=48.0
    ))

    # Gutsprache mit Serie 1 verknuepfen
    serien[0].cost_approval_id = gs1.id

    # === 5 Aufgaben ===

    # 1. Automatisch: Fehlende Versicherungsdaten (Patient 5 hat zwar Versicherung, simulieren wir)
    task1 = Task(
        organization_id=org.id,
        title='Fehlende Versicherungsdaten: Lukas Zimmermann',
        description='Patient P00005 hat eine aktive Behandlungsserie aber unvollstaendige Versicherungsdaten. '
                    'Bitte Versicherungsnummer pruefen.',
        category='versicherung',
        priority='high',
        task_type='missing_insurance',
        status='open',
        auto_generated=True,
        related_patient_id=patients[4].id,
        related_series_id=serien[4].id
    )
    db.session.add(task1)

    # 2. Automatisch: Fehlende Verordnung
    task2 = Task(
        organization_id=org.id,
        title='Fehlende Verordnung: Nina Brunner',
        description='Patientin hat keinen Verordnungsnachweis fuer die geplante Behandlung hinterlegt.',
        category='verordnung',
        priority='high',
        task_type='missing_prescription',
        status='open',
        auto_generated=True,
        related_patient_id=patients[5].id
    )
    db.session.add(task2)

    # 3. Manuell: Rueckruf Patient
    task3 = Task(
        organization_id=org.id,
        title='Rückruf: Daniel Schmid wegen Terminverschiebung',
        description='Patient hat angerufen und bittet um Terminverschiebung naechste Woche. Bitte zurueckrufen.',
        category='sonstiges',
        priority='normal',
        task_type='manual',
        status='open',
        auto_generated=False,
        assigned_to_id=created_users['lisa'].id,
        created_by_id=created_users['thomas'].id,
        related_patient_id=patients[6].id,
        due_date=date.today() + timedelta(days=1)
    )
    db.session.add(task3)

    # 4. Manuell: Geraet warten
    task4 = Task(
        organization_id=org.id,
        title='Stosswellengerät: Wartungstermin vereinbaren',
        description='Wartung ist ueberfaellig. Bitte MedTech Service AG kontaktieren fuer Terminvereinbarung.',
        category='sonstiges',
        priority='normal',
        task_type='manual',
        status='open',
        auto_generated=False,
        assigned_to_id=created_users['admin'].id,
        created_by_id=created_users['admin'].id,
        due_date=date.today() + timedelta(days=7)
    )
    db.session.add(task4)

    # 5. Erledigt
    task5 = Task(
        organization_id=org.id,
        title='Verordnung eingescannt: Max Huber',
        description='Verordnung fuer Physiotherapie KVG wurde eingescannt und im System hinterlegt.',
        category='verordnung',
        priority='low',
        task_type='manual',
        status='completed',
        auto_generated=False,
        assigned_to_id=created_users['lisa'].id,
        created_by_id=created_users['thomas'].id,
        related_patient_id=patients[0].id,
        completed_at=datetime.now() - timedelta(days=2)
    )
    db.session.add(task5)

    # Kommentar zur erledigten Aufgabe
    db.session.flush()
    db.session.add(TaskComment(
        task_id=task5.id,
        user_id=created_users['lisa'].id,
        comment='Verordnung eingescannt und unter Patientendokumenten abgelegt.'
    ))

    db.session.commit()


def _seed_settings_demo_data(org, patients):
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

    # === E-Mail Demo-Daten ===
    # Eigener Ordner
    ordner_wichtig = EmailFolder(
        organization_id=org.id,
        name='Wichtig',
        sort_order=1
    )
    db.session.add(ordner_wichtig)
    db.session.flush()

    # E-Mail 1: Posteingang, gelesen
    email_inbox_read = Email(
        organization_id=org.id,
        from_address='dr.weber@arztpraxis-weber.ch',
        to_address='info@omnia-health.ch',
        subject='Verordnung Physiotherapie - Patient Huber',
        body_html='<p>Sehr geehrtes Praxisteam,</p><p>anbei sende ich Ihnen die Verordnung für Herrn Max Huber (geb. 15.03.1985) für 9 Sitzungen Physiotherapie KVG.</p><p>Diagnose: Chronische lumbale Rückenschmerzen (M54.5)</p><p>Bitte kontaktieren Sie den Patienten zur Terminvereinbarung.</p><p>Freundliche Grüsse<br>Dr. med. Thomas Weber</p>',
        body_text='Sehr geehrtes Praxisteam, anbei sende ich Ihnen die Verordnung für Herrn Max Huber für 9 Sitzungen Physiotherapie KVG. Diagnose: Chronische lumbale Rückenschmerzen.',
        status='received',
        folder='inbox',
        linked_patient_id=patients[0].id,
        read_at=datetime.utcnow() - timedelta(hours=2),
        created_at=datetime.utcnow() - timedelta(days=1)
    )
    # E-Mail 2: Posteingang, ungelesen
    email_inbox_unread = Email(
        organization_id=org.id,
        from_address='anna.meier@bluewin.ch',
        to_address='info@omnia-health.ch',
        subject='Terminverschiebung nächste Woche',
        body_html='<p>Guten Tag,</p><p>Ich möchte meinen Termin am Mittwoch gerne auf Freitag verschieben, da ich beruflich verhindert bin. Ist das möglich?</p><p>Vielen Dank und freundliche Grüsse<br>Anna Meier</p>',
        body_text='Guten Tag, ich möchte meinen Termin am Mittwoch gerne auf Freitag verschieben. Ist das möglich? Vielen Dank, Anna Meier',
        status='received',
        folder='inbox',
        linked_patient_id=patients[1].id,
        created_at=datetime.utcnow() - timedelta(hours=3)
    )
    # E-Mail 3: Gesendet (Terminbestätigung)
    email_sent = Email(
        organization_id=org.id,
        from_address='info@omnia-health.ch',
        to_address='max.huber@gmail.com',
        subject='Terminbestätigung - OMNIA Physiotherapie',
        body_html='<p>Sehr geehrter Herr Huber,</p><p>Hiermit bestätigen wir Ihren Termin:</p><p><strong>Datum:</strong> Montag, 23.03.2026<br><strong>Zeit:</strong> 09:00 Uhr<br><strong>Therapeut:</strong> Thomas Müller</p><p>Bitte bringen Sie Ihre Versicherungskarte mit.</p><p>Freundliche Grüsse<br>OMNIA Health Services AG</p>',
        body_text='Terminbestätigung für Max Huber: Montag 23.03.2026, 09:00 Uhr, Therapeut Thomas Müller.',
        status='sent',
        folder='sent',
        linked_patient_id=patients[0].id,
        sent_at=datetime.utcnow() - timedelta(days=2),
        created_at=datetime.utcnow() - timedelta(days=2)
    )
    # E-Mail 4: Entwurf
    email_draft = Email(
        organization_id=org.id,
        from_address='info@omnia-health.ch',
        to_address='peter.keller@sunrise.ch',
        subject='Behandlungsplan - Nachkontrolle',
        body_html='<p>Sehr geehrter Herr Keller,</p><p>Im Rahmen Ihrer Nachbehandlung nach der Tibiafraktur möchten wir Sie über den weiteren Behandlungsplan informieren...</p>',
        body_text='Behandlungsplan Nachkontrolle für Peter Keller...',
        status='draft',
        folder='drafts',
        linked_patient_id=patients[2].id,
        created_at=datetime.utcnow() - timedelta(hours=5)
    )
    # E-Mail 5: Archiviert
    email_archive = Email(
        organization_id=org.id,
        from_address='info@css.ch',
        to_address='info@omnia-health.ch',
        subject='Kostengutsprache KGS-2026-0001 genehmigt',
        body_html='<p>Sehr geehrte Damen und Herren,</p><p>Wir teilen Ihnen mit, dass die Kostengutsprache KGS-2026-0001 für die Patientin Lisa Fischer genehmigt wurde.</p><p>Genehmigter Umfang: 12 Sitzungen Physiotherapie KVG</p><p>Freundliche Grüsse<br>CSS Versicherung</p>',
        body_text='Kostengutsprache KGS-2026-0001 für Lisa Fischer genehmigt. 12 Sitzungen Physiotherapie KVG.',
        status='received',
        folder='archive',
        linked_patient_id=patients[3].id,
        read_at=datetime.utcnow() - timedelta(days=5),
        created_at=datetime.utcnow() - timedelta(days=7)
    )
    # E-Mail 6: Gutsprache-bezogene E-Mail (gesendet an Versicherung)
    gs_sent = CostApproval.query.filter_by(organization_id=org.id, status='sent').first()
    if gs_sent:
        email_gs = Email(
            organization_id=org.id,
            from_address='info@omnia-health.ch',
            to_address='leistungen@css.ch',
            subject='Kostengutsprache ' + (gs_sent.approval_number or '') + ' - Antrag',
            body_html='<p>Sehr geehrte Damen und Herren,</p><p>Anbei senden wir Ihnen den Antrag auf Kostengutsprache für die oben genannte Patientin.</p><p>Bitte um Prüfung und Rückmeldung.</p><p>Freundliche Grüsse<br>OMNIA Health Services AG</p>',
            body_text='Kostengutsprache-Antrag für Patientin. Bitte um Prüfung.',
            status='sent',
            folder='sent',
            linked_patient_id=gs_sent.patient_id,
            linked_cost_approval_id=gs_sent.id,
            sent_at=datetime.utcnow() - timedelta(days=3),
            created_at=datetime.utcnow() - timedelta(days=3)
        )
        db.session.add_all([email_inbox_read, email_inbox_unread, email_sent, email_draft, email_archive, email_gs])
    else:
        db.session.add_all([email_inbox_read, email_inbox_unread, email_sent, email_draft, email_archive])

    # Rollen-Berechtigungen
    modules = ['dashboard', 'kalender', 'patienten', 'mitarbeiter', 'behandlung',
               'abrechnung', 'produkte', 'ressourcen', 'adressen', 'einstellungen',
               'kommunikation']
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
        'kommunikation': ['lesen', 'erstellen'],
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
        'kommunikation': ['lesen', 'erstellen', 'bearbeiten'],
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


def _seed_hr_demo_data(org, employees, created_users):
    """Erstellt Demo-Daten fuer HR und Lohnbuchhaltung"""
    today = date.today()

    admin_emp = employees['admin']
    thomas_emp = employees['thomas']
    sarah_emp = employees['sarah']
    lisa_emp = employees['lisa']

    # === Arbeitsvertraege ===
    contracts_data = [
        (admin_emp, 'permanent', date(2024, 1, 1), None, date(2024, 4, 1), 3, 100, 25),
        (thomas_emp, 'permanent', date(2024, 3, 1), None, date(2024, 6, 1), 2, 100, 20),
        (sarah_emp, 'permanent', date(2024, 4, 15), None, date(2024, 7, 15), 2, 100, 20),
        (lisa_emp, 'permanent', date(2024, 6, 1), None, date(2024, 9, 1), 1, 80, 16),
    ]
    for emp, ctype, start, end, probation, notice, pensum, vacation in contracts_data:
        db.session.add(EmployeeContract(
            employee_id=emp.id,
            contract_type=ctype,
            start_date=start,
            end_date=end,
            probation_end=probation,
            notice_period_months=notice,
            pensum_percent=pensum,
            vacation_days=vacation
        ))

    # === Lohndaten ===
    salaries_data = [
        (admin_emp, 'monthly', 10000, None, True, 'CH9300762011623852957', '756.1234.5678.10', 7.0, 1.5, 0.5, date(2024, 1, 1)),
        (thomas_emp, 'monthly', 7500, None, True, 'CH5800791123000889012', '756.2345.6789.11', 7.0, 1.5, 0.5, date(2024, 3, 1)),
        (sarah_emp, 'monthly', 7200, None, True, 'CH3600700110002069411', '756.3456.7890.12', 7.0, 1.5, 0.5, date(2024, 4, 15)),
        (lisa_emp, 'monthly', 4800, None, False, 'CH4431999123000889999', '756.4567.8901.13', 7.0, 1.5, 0.5, date(2024, 6, 1)),
    ]
    for emp, stype, amount, hourly, thirteenth, iban, ahv, bvg, nbuv, ktg, valid_from in salaries_data:
        db.session.add(EmployeeSalary(
            employee_id=emp.id,
            salary_type=stype,
            amount=amount,
            hourly_rate=hourly,
            thirteenth_month=thirteenth,
            iban=iban,
            ahv_number=ahv,
            bvg_rate=bvg,
            nbuv_rate=nbuv,
            ktg_rate=ktg,
            valid_from=valid_from
        ))

    # === Kinder (Thomas Meier hat 1 Kind) ===
    db.session.add(EmployeeChild(
        employee_id=thomas_emp.id,
        first_name='Luca',
        last_name='Meier',
        date_of_birth=date(2020, 5, 12),
        allowance_type='child',
        allowance_amount=200.0
    ))

    db.session.flush()

    # === Lohnlauf Februar 2026 (ausbezahlt) ===
    from services.payroll_service import calculate_payslip, MONTH_NAMES
    run = PayrollRun(
        organization_id=org.id,
        year=2026,
        month=2,
        status='paid',
        paid_at=datetime(2026, 2, 25, 14, 0)
    )
    db.session.add(run)
    db.session.flush()

    total_gross = 0
    total_net = 0
    total_employer = 0

    for emp in [admin_emp, thomas_emp, sarah_emp, lisa_emp]:
        data = calculate_payslip(emp, 2, 2026)
        if not data:
            continue

        slip = Payslip(
            payroll_run_id=run.id,
            employee_id=emp.id,
            gross_salary=data['gross_salary'],
            thirteenth_month=data['thirteenth_month'],
            child_allowance=data['child_allowance'],
            bonuses=data['bonuses'],
            expenses_total=data['expenses_total'],
            overtime_payout=data['overtime_payout'],
            gross_total=data['gross_total'],
            ahv_iv_eo=data['ahv_iv_eo'],
            alv=data['alv'],
            alv2=data.get('alv2', 0),
            bvg=data['bvg'],
            nbuv=data['nbuv'],
            ktg=data['ktg'],
            withholding_tax=data['withholding_tax'],
            deductions_total=data['deductions_total'],
            net_salary=data['net_salary'],
            employer_ahv_iv_eo=data['employer_ahv_iv_eo'],
            employer_alv=data['employer_alv'],
            employer_bvg=data['employer_bvg'],
            employer_uvg=data['employer_uvg'],
            employer_ktg=data['employer_ktg'],
            employer_fak=data['employer_fak'],
            employer_vk=data['employer_vk'],
            employer_total=data['employer_total'],
            details_json=str(data)
        )
        db.session.add(slip)
        total_gross += data['gross_total']
        total_net += data['net_salary']
        total_employer += data['employer_total']

    run.total_gross = round(total_gross, 2)
    run.total_net = round(total_net, 2)
    run.total_employer_contributions = round(total_employer, 2)

    # === Zeiterfassungs-Eintraege (letzte Woche, Thomas Meier) ===
    last_monday = today - timedelta(days=today.weekday() + 7)
    for i in range(5):
        d = last_monday + timedelta(days=i)
        worked = 510 if i < 4 else 480  # 8:30h oder 8:00h
        db.session.add(TimeEntry(
            employee_id=thomas_emp.id,
            date=d,
            clock_in=time(7, 45),
            clock_out=time(17, 15) if i < 4 else time(16, 45),
            break_minutes=60,
            worked_minutes=worked,
            entry_type='clock'
        ))

    # === Ueberstundenkonto Thomas Meier (+12h kumuliert) ===
    db.session.add(OvertimeAccount(
        employee_id=thomas_emp.id,
        year=2026,
        month=2,
        target_minutes=10080,  # 168h (21 Arbeitstage x 8h)
        actual_minutes=10800,  # 180h
        overtime_minutes=720,  # +12h
        cumulative_overtime=720
    ))

    # === Spesen ===
    # 1. Genehmigt (Sarah)
    db.session.add(Expense(
        employee_id=sarah_emp.id,
        date=today - timedelta(days=10),
        description='Zugfahrt Winterthur-Bern, Weiterbildung Sportphysiotherapie',
        category='travel',
        amount=68.40,
        vat_amount=5.54,
        status='approved',
        approved_by_id=created_users['admin'].id,
        approved_at=datetime.now() - timedelta(days=8)
    ))
    # 2. Eingereicht (Thomas Meier)
    db.session.add(Expense(
        employee_id=thomas_emp.id,
        date=today - timedelta(days=3),
        description='Fachliteratur: Manuelle Therapie Update 2026',
        category='training',
        amount=89.00,
        vat_amount=7.21,
        status='submitted'
    ))
    # 3. Ausbezahlt (Lisa)
    db.session.add(Expense(
        employee_id=lisa_emp.id,
        date=today - timedelta(days=20),
        description='Büromaterial: Druckerpapier, Ordner',
        category='material',
        amount=45.50,
        vat_amount=3.69,
        status='paid',
        approved_by_id=created_users['admin'].id,
        approved_at=datetime.now() - timedelta(days=18),
        paid_via='separate'
    ))

    db.session.commit()


def seed_accounting_data(org, loc_zh, loc_wt, created_users):
    """Erstellt Demo-Daten fuer die Finanzbuchhaltung"""

    # Pruefen ob bereits Konten vorhanden
    if Account.query.filter_by(organization_id=org.id).first():
        return

    admin_user = created_users.get('admin')

    # === Kontenplan (Schweizer KMU, Physiotherapie-spezifisch) ===
    konten_daten = [
        # 1xxx Aktiven
        ('1000', 'Kasse', 'asset'),
        ('1020', 'Bank (UBS)', 'asset'),
        ('1021', 'Bank (ZKB)', 'asset'),
        ('1100', 'Debitoren Patienten', 'asset'),
        ('1101', 'Debitoren Versicherungen', 'asset'),
        ('1170', 'Vorsteuer', 'asset'),
        ('1200', 'Vorräte Therapiematerial', 'asset'),
        ('1500', 'Praxiseinrichtung', 'asset'),
        ('1510', 'Medizinische Geräte', 'asset'),
        ('1520', 'IT/EDV', 'asset'),
        # 2xxx Passiven
        ('2000', 'Kreditoren', 'liability'),
        ('2200', 'MwSt-Schuld', 'liability'),
        ('2270', 'SV-Verbindlichkeiten', 'liability'),
        ('2400', 'Langfristige Darlehen', 'liability'),
        ('2800', 'Eigenkapital', 'equity'),
        ('2900', 'Gewinnvortrag', 'equity'),
        # 3xxx Betriebsertrag
        ('3000', 'Behandlungsertrag KVG', 'income'),
        ('3010', 'Behandlungsertrag UVG/IVG/MVG', 'income'),
        ('3020', 'Behandlungsertrag Privat/Selbstzahler', 'income'),
        ('3100', 'Produkteverkauf', 'income'),
        ('3200', 'Fitnessabo-Ertrag', 'income'),
        # 4xxx Aufwand Material
        ('4000', 'Therapiematerial', 'expense'),
        ('4100', 'Medizinisches Verbrauchsmaterial', 'expense'),
        # 5xxx Personalaufwand
        ('5000', 'Löhne', 'expense'),
        ('5700', 'Sozialversicherungen', 'expense'),
        ('5800', 'Übriger Personalaufwand', 'expense'),
        # 6xxx Betriebsaufwand
        ('6000', 'Raumaufwand (Miete)', 'expense'),
        ('6100', 'Unterhalt und Reparaturen', 'expense'),
        ('6200', 'Fahrzeugaufwand', 'expense'),
        ('6300', 'Versicherungen', 'expense'),
        ('6400', 'Energie', 'expense'),
        ('6500', 'Verwaltungsaufwand', 'expense'),
        ('6570', 'IT-Kosten', 'expense'),
        ('6600', 'Werbung/Marketing', 'expense'),
        ('6700', 'Sonstiger Betriebsaufwand', 'expense'),
        ('6800', 'Abschreibungen', 'expense'),
        ('6900', 'Finanzaufwand', 'expense'),
    ]

    konten = {}
    for nummer, name, typ in konten_daten:
        acc = Account(
            organization_id=org.id,
            account_number=nummer,
            name=name,
            account_type=typ,
            is_active=True
        )
        db.session.add(acc)
        konten[nummer] = acc
    db.session.flush()

    # === Kostenstellen ===
    kostenstellen = [
        ('KST-PHY-ZH', 'Physiotherapie Zürich', loc_zh.id),
        ('KST-PHY-WT', 'Physiotherapie Winterthur', loc_wt.id),
        ('KST-FIT', 'Fitness', None),
        ('KST-ADM', 'Administration', None),
    ]

    cc_objects = {}
    for code, name, loc_id in kostenstellen:
        cc = CostCenter(
            organization_id=org.id,
            code=code,
            name=name,
            location_id=loc_id,
            is_active=True
        )
        db.session.add(cc)
        cc_objects[code] = cc
    db.session.flush()

    # === Demo-Buchungen ===
    from datetime import date as date_cls, timedelta

    buchungen = [
        # 1: Rechnung Patient (Debitoren an Behandlungsertrag KVG)
        {
            'date': date_cls(2026, 3, 1), 'desc': 'Rechnung RE-2026-0001 - Müller Hans',
            'source': 'invoice', 'lines': [
                {'acc': '1100', 'debit': 450.00, 'credit': 0},
                {'acc': '3000', 'debit': 0, 'credit': 450.00}
            ]
        },
        # 2: Rechnung Versicherung (Debitoren an Behandlungsertrag UVG)
        {
            'date': date_cls(2026, 3, 3), 'desc': 'Rechnung RE-2026-0002 - Weber Anna (UVG)',
            'source': 'invoice', 'lines': [
                {'acc': '1101', 'debit': 720.00, 'credit': 0},
                {'acc': '3010', 'debit': 0, 'credit': 720.00}
            ]
        },
        # 3: Zahlung Patient (Bank an Debitoren)
        {
            'date': date_cls(2026, 3, 8), 'desc': 'Zahlungseingang Müller Hans',
            'source': 'payment', 'lines': [
                {'acc': '1020', 'debit': 450.00, 'credit': 0},
                {'acc': '1100', 'debit': 0, 'credit': 450.00}
            ]
        },
        # 4: Zahlung Versicherung (Bank an Debitoren)
        {
            'date': date_cls(2026, 3, 12), 'desc': 'Zahlungseingang CSS UVG Weber',
            'source': 'payment', 'lines': [
                {'acc': '1020', 'debit': 720.00, 'credit': 0},
                {'acc': '1101', 'debit': 0, 'credit': 720.00}
            ]
        },
        # 5: Miete (Raumaufwand an Bank)
        {
            'date': date_cls(2026, 3, 1), 'desc': 'Miete März 2026',
            'source': 'manual', 'lines': [
                {'acc': '6000', 'debit': 3500.00, 'credit': 0, 'cc': 'KST-PHY-ZH'},
                {'acc': '1020', 'debit': 0, 'credit': 3500.00}
            ]
        },
        # 6: Versicherung (Versicherung an Bank)
        {
            'date': date_cls(2026, 3, 5), 'desc': 'Betriebsversicherung Q1/2026',
            'source': 'manual', 'lines': [
                {'acc': '6300', 'debit': 450.00, 'credit': 0},
                {'acc': '1020', 'debit': 0, 'credit': 450.00}
            ]
        },
        # 7: Materialbestellung (Therapiematerial an Kreditoren)
        {
            'date': date_cls(2026, 3, 10), 'desc': 'Therapiematerial MediShop AG',
            'source': 'creditor', 'lines': [
                {'acc': '4000', 'debit': 258.54, 'credit': 0},
                {'acc': '1170', 'debit': 21.46, 'credit': 0, 'vat_code': 'vorsteuer', 'vat_amount': 21.46},
                {'acc': '2000', 'debit': 0, 'credit': 280.00}
            ]
        },
        # 8: Kreditor-Zahlung (Kreditoren an Bank)
        {
            'date': date_cls(2026, 3, 15), 'desc': 'Zahlung MediShop AG',
            'source': 'creditor_payment', 'lines': [
                {'acc': '2000', 'debit': 280.00, 'credit': 0},
                {'acc': '1020', 'debit': 0, 'credit': 280.00}
            ]
        },
        # 9: Lohn (Löhne an Bank)
        {
            'date': date_cls(2026, 3, 25), 'desc': 'Löhne März 2026',
            'source': 'salary', 'lines': [
                {'acc': '5000', 'debit': 12000.00, 'credit': 0, 'cc': 'KST-ADM'},
                {'acc': '1020', 'debit': 0, 'credit': 12000.00}
            ]
        },
        # 10: MwSt-Buchung (Privatleistung mit MwSt)
        {
            'date': date_cls(2026, 3, 18), 'desc': 'Rechnung RE-2026-0003 - Privatbehandlung',
            'source': 'invoice', 'lines': [
                {'acc': '1100', 'debit': 200.00, 'credit': 0},
                {'acc': '3020', 'debit': 0, 'credit': 185.01},
                {'acc': '2200', 'debit': 0, 'credit': 14.99, 'vat_code': '8.1', 'vat_amount': 14.99}
            ]
        },
    ]

    entry_num = 1
    for b in buchungen:
        entry = JournalEntry(
            organization_id=org.id,
            entry_number=f'BU-2026-{entry_num:04d}',
            date=b['date'],
            description=b['desc'],
            source=b['source'],
            created_by_id=admin_user.id if admin_user else None
        )
        db.session.add(entry)
        db.session.flush()

        for line in b['lines']:
            acc = konten.get(line['acc'])
            if acc:
                jel = JournalEntryLine(
                    entry_id=entry.id,
                    account_id=acc.id,
                    debit=line.get('debit', 0),
                    credit=line.get('credit', 0),
                    vat_code=line.get('vat_code'),
                    vat_amount=line.get('vat_amount', 0),
                    cost_center_id=cc_objects.get(line.get('cc')).id if line.get('cc') else None,
                    description=b['desc']
                )
                db.session.add(jel)

        entry_num += 1

    # === Kreditoren-Rechnungen ===
    # 1: Offen
    cred1 = CreditorInvoice(
        organization_id=org.id,
        creditor_name='PhysioSupply GmbH',
        invoice_number='PS-2026-0142',
        invoice_date=date_cls(2026, 3, 15),
        due_date=date_cls(2026, 4, 15),
        amount=560.00,
        vat_amount=45.36,
        account_id=konten['4100'].id,
        status='open',
        notes='Verbrauchsmaterial Q1'
    )
    # 2: Bezahlt
    cred2 = CreditorInvoice(
        organization_id=org.id,
        creditor_name='MediShop AG',
        invoice_number='MS-2026-0089',
        invoice_date=date_cls(2026, 3, 5),
        due_date=date_cls(2026, 4, 5),
        amount=280.00,
        vat_amount=21.46,
        account_id=konten['4000'].id,
        status='paid',
        notes='Therapiematerial'
    )
    db.session.add_all([cred1, cred2])

    # === Anlagegüter ===
    asset1 = FixedAsset(
        organization_id=org.id,
        name='Ultraschallgerät Siemens',
        category='devices',
        acquisition_date=date_cls(2024, 1, 15),
        acquisition_value=8000.00,
        useful_life_years=8,
        depreciation_method='linear',
        current_book_value=6000.00,
        account_id=konten['1510'].id,
        depreciation_account_id=konten['6800'].id,
        is_active=True
    )
    asset2 = FixedAsset(
        organization_id=org.id,
        name='Stosswellengerät Swiss DolorClast',
        category='devices',
        acquisition_date=date_cls(2023, 6, 1),
        acquisition_value=12000.00,
        useful_life_years=10,
        depreciation_method='linear',
        current_book_value=8800.00,
        account_id=konten['1510'].id,
        depreciation_account_id=konten['6800'].id,
        is_active=True
    )
    asset3 = FixedAsset(
        organization_id=org.id,
        name='IT-Infrastruktur (Server, PCs, Tablets)',
        category='it',
        acquisition_date=date_cls(2025, 1, 1),
        acquisition_value=5000.00,
        useful_life_years=4,
        depreciation_method='linear',
        current_book_value=3750.00,
        account_id=konten['1520'].id,
        depreciation_account_id=konten['6800'].id,
        is_active=True
    )
    db.session.add_all([asset1, asset2, asset3])

    # === Gespeicherte Auswertungen (Demo) ===
    saved_report1 = SavedReport(
        organization_id=org.id,
        user_id=created_users['admin'].id,
        name='Aktive Patienten mit Versicherung',
        category='patients',
        filters_json=json.dumps({'is_active': '1'}),
        columns_json=json.dumps(['patient_number', 'last_name', 'first_name', 'date_of_birth', 'insurance_type', 'insurance_provider', 'phone', 'email'])
    )
    saved_report2 = SavedReport(
        organization_id=org.id,
        user_id=created_users['admin'].id,
        name='Umsatz Q1 2026',
        category='invoices',
        filters_json=json.dumps({'date_from': '2026-01-01', 'date_to': '2026-03-31', 'status': 'paid'}),
        columns_json=json.dumps(['invoice_number', 'patient_name', 'amount_total', 'amount_paid', 'status', 'created_at'])
    )
    db.session.add_all([saved_report1, saved_report2])

    # === Fitness: Abo-Vorlagen ===
    fitness_vorlage1 = SubscriptionTemplate(
        organization_id=org.id,
        name='Fitness Jahresabo',
        category='fitness',
        duration_months=12,
        price=89.00,
        payment_interval='monthly',
        cancellation_months=2,
        auto_renew=True,
        max_visits=0,
        access_hours_json=json.dumps({"Mo-Fr": "06:00-22:00", "Sa-So": "08:00-18:00"}),
        is_active=True
    )
    fitness_vorlage2 = SubscriptionTemplate(
        organization_id=org.id,
        name='MTT 3 Monate',
        category='mtt',
        duration_months=3,
        price=120.00,
        payment_interval='once',
        cancellation_months=0,
        auto_renew=False,
        max_visits=0,
        is_active=True
    )
    fitness_vorlage3 = SubscriptionTemplate(
        organization_id=org.id,
        name='10er-Karte',
        category='fitness',
        duration_months=0,
        price=150.00,
        payment_interval='once',
        cancellation_months=0,
        auto_renew=False,
        max_visits=10,
        is_active=True
    )
    db.session.add_all([fitness_vorlage1, fitness_vorlage2, fitness_vorlage3])
    db.session.flush()

    # === Fitness: Abonnemente ===
    today = date.today()
    fitness_abos = []

    # Abo 1: Aktiv - Jahresabo (Patient 0: Anna Mueller)
    abo1 = Subscription(
        organization_id=org.id,
        patient_id=patients[0].id,
        template_id=fitness_vorlage1.id,
        subscription_number='ABO-00001',
        badge_number='NFC-1001',
        start_date=today - timedelta(days=120),
        end_date=today + timedelta(days=245),
        status='active',
        visits_used=18
    )
    # Abo 2: Aktiv - MTT (Patient 1: Peter Keller)
    abo2 = Subscription(
        organization_id=org.id,
        patient_id=patients[1].id,
        template_id=fitness_vorlage2.id,
        subscription_number='ABO-00002',
        badge_number='NFC-1002',
        start_date=today - timedelta(days=30),
        end_date=today + timedelta(days=60),
        status='active',
        visits_used=8
    )
    # Abo 3: Aktiv - Jahresabo (Patient 2: Sandra Huber)
    abo3 = Subscription(
        organization_id=org.id,
        patient_id=patients[2].id,
        template_id=fitness_vorlage1.id,
        subscription_number='ABO-00003',
        badge_number='NFC-1003',
        start_date=today - timedelta(days=200),
        end_date=today + timedelta(days=165),
        status='active',
        visits_used=32
    )
    # Abo 4: Pausiert - Jahresabo (Patient 3: Marco Brunner)
    abo4 = Subscription(
        organization_id=org.id,
        patient_id=patients[3].id,
        template_id=fitness_vorlage1.id,
        subscription_number='ABO-00004',
        start_date=today - timedelta(days=90),
        end_date=today + timedelta(days=275),
        status='paused',
        paused_from=today - timedelta(days=10),
        paused_until=today + timedelta(days=20),
        visits_used=12
    )
    # Abo 5: Abgelaufen - MTT (Patient 4: Lisa Weber)
    abo5 = Subscription(
        organization_id=org.id,
        patient_id=patients[4].id,
        template_id=fitness_vorlage2.id,
        subscription_number='ABO-00005',
        start_date=today - timedelta(days=120),
        end_date=today - timedelta(days=30),
        status='expired',
        visits_used=15
    )
    # Abo 6: 10er-Karte mit 6 von 10 Besuchen (Patient 5: Thomas Gerber)
    abo6 = Subscription(
        organization_id=org.id,
        patient_id=patients[5].id,
        template_id=fitness_vorlage3.id,
        subscription_number='ABO-00006',
        badge_number='NFC-1006',
        start_date=today - timedelta(days=45),
        end_date=None,
        status='active',
        visits_used=6
    )
    db.session.add_all([abo1, abo2, abo3, abo4, abo5, abo6])
    db.session.flush()

    # === Fitness: Besuche (15 Besuche verteilt ueber letzte 2 Wochen) ===
    import random
    fitness_besuche = []
    aktive_abos_demo = [abo1, abo2, abo3, abo6]
    for tag_offset in range(14, 0, -1):
        # 1-2 Besuche pro Tag
        anzahl = 1 if tag_offset % 3 == 0 else 2
        if len(fitness_besuche) >= 15:
            break
        for _ in range(anzahl):
            if len(fitness_besuche) >= 15:
                break
            abo = aktive_abos_demo[len(fitness_besuche) % len(aktive_abos_demo)]
            stunde = random.randint(7, 19)
            minute = random.randint(0, 59)
            checkin_time = datetime.combine(
                today - timedelta(days=tag_offset),
                time(stunde, minute)
            )
            checkout_time = checkin_time + timedelta(minutes=random.randint(30, 90))
            besuch = FitnessVisit(
                subscription_id=abo.id,
                patient_id=abo.patient_id,
                location_id=loc_zh.id,
                check_in=checkin_time,
                check_out=checkout_time
            )
            fitness_besuche.append(besuch)

    db.session.add_all(fitness_besuche)

    db.session.commit()


app = create_app()
