# Datenbank-Modelle für OMNIA Praxissoftware
# Alle Entitäten gemäss Spezifikation (auch für spätere Phasen)

from datetime import datetime, date, time
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


# ============================================================
# Organisation & Standorte
# ============================================================

class Organization(db.Model):
    __tablename__ = 'organizations'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    address = db.Column(db.String(500))
    phone = db.Column(db.String(50))
    email = db.Column(db.String(200))
    nif_number = db.Column(db.String(50))
    gln_number = db.Column(db.String(50))
    zsr_number = db.Column(db.String(50))
    logo = db.Column(db.String(500))
    settings_json = db.Column(db.JSON, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    locations = db.relationship('Location', backref='organization', lazy='dynamic')
    employees = db.relationship('Employee', backref='organization', lazy='dynamic')
    patients = db.relationship('Patient', backref='organization', lazy='dynamic')


class Location(db.Model):
    __tablename__ = 'locations'
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    address = db.Column(db.String(500))
    phone = db.Column(db.String(50))
    opening_hours_json = db.Column(db.JSON, default=dict)
    holidays_json = db.Column(db.JSON, default=list)
    is_active = db.Column(db.Boolean, default=True)

    resources = db.relationship('Resource', backref='location', lazy='dynamic')


# ============================================================
# Benutzer & Mitarbeiter
# ============================================================

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(200))
    role = db.Column(db.String(20), nullable=False, default='therapist')  # admin/therapist/reception
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    employee = db.relationship('Employee', backref='user', uselist=False)
    chat_messages = db.relationship('ChatMessage', backref='user', lazy='dynamic')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Employee(db.Model):
    __tablename__ = 'employees'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    qualifications = db.Column(db.JSON, default=list)
    employment_model = db.Column(db.String(50), default='employed')  # employed/self_employed_own/self_employed_practice
    pensum_percent = db.Column(db.Integer, default=100)
    zsr_number = db.Column(db.String(50))
    gln_number = db.Column(db.String(50))
    color_code = db.Column(db.String(7), default='#4a90d9')
    is_active = db.Column(db.Boolean, default=True)

    work_schedules = db.relationship('WorkSchedule', backref='employee', lazy='dynamic')
    absences = db.relationship('Absence', backref='employee', lazy='dynamic')
    appointments = db.relationship('Appointment', backref='employee', lazy='dynamic')
    treatment_series = db.relationship('TreatmentSeries', backref='therapist', lazy='dynamic')

    # Hilfsfunktionen
    @property
    def display_name(self):
        return self.user.name if self.user else f'Mitarbeiter #{self.id}'

    @property
    def location_ids(self):
        """Standort-IDs aus den Arbeitszeiten ermitteln"""
        schedules = WorkSchedule.query.filter_by(employee_id=self.id).all()
        return list(set(s.location_id for s in schedules if s.location_id))


class WorkSchedule(db.Model):
    __tablename__ = 'work_schedules'
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'))
    type = db.Column(db.String(20), default='weekly')  # weekly/repeating/fixed
    day_of_week = db.Column(db.Integer, nullable=False)  # 0=Montag, 6=Sonntag
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    work_type = db.Column(db.String(20), default='working')  # working/break/office/overtime_buffer

    DAY_NAMES = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag']

    @property
    def day_name(self):
        return self.DAY_NAMES[self.day_of_week] if 0 <= self.day_of_week <= 6 else '?'


class Absence(db.Model):
    __tablename__ = 'absences'
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    type = db.Column(db.String(20), nullable=False)  # vacation/illness/training
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default='requested')  # requested/approved/rejected
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ============================================================
# Patienten
# ============================================================

class Patient(db.Model):
    __tablename__ = 'patients'
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    date_of_birth = db.Column(db.Date)
    gender = db.Column(db.String(10))  # m/f/d
    phone = db.Column(db.String(50))
    mobile = db.Column(db.String(50))
    email = db.Column(db.String(200))
    address = db.Column(db.String(500))
    insurance_provider_id = db.Column(db.Integer, db.ForeignKey('insurance_providers.id'))
    insurance_number = db.Column(db.String(50))
    ahv_number = db.Column(db.String(20))
    preferred_contact_method = db.Column(db.String(20), default='phone')
    preferred_appointment_times_json = db.Column(db.JSON, default=dict)
    blacklisted = db.Column(db.Boolean, default=False)
    blacklist_reason = db.Column(db.Text)
    employer = db.Column(db.String(200))
    notes = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    appointments = db.relationship('Appointment', backref='patient', lazy='dynamic')
    treatment_series = db.relationship('TreatmentSeries', backref='patient', lazy='dynamic')
    insurance_provider = db.relationship('InsuranceProvider', backref='patients')

    @property
    def full_name(self):
        return f'{self.first_name} {self.last_name}'

    @property
    def age(self):
        if not self.date_of_birth:
            return None
        today = date.today()
        return today.year - self.date_of_birth.year - (
            (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
        )


# ============================================================
# Behandlungsserien & Termine
# ============================================================

class TreatmentSeriesTemplate(db.Model):
    __tablename__ = 'treatment_series_templates'
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    tariff_type = db.Column(db.String(20))  # 311/312/338/325/590/999/flatrate
    num_appointments = db.Column(db.Integer, default=9)
    duration_minutes = db.Column(db.Integer, default=30)
    min_interval_days = db.Column(db.Integer, default=1)
    default_location_id = db.Column(db.Integer, db.ForeignKey('locations.id'))
    group_therapy = db.Column(db.Boolean, default=False)
    requires_resource = db.Column(db.Boolean, default=False)
    settings_json = db.Column(db.JSON, default=dict)


class TreatmentSeries(db.Model):
    __tablename__ = 'treatment_series'
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    template_id = db.Column(db.Integer, db.ForeignKey('treatment_series_templates.id'))
    therapist_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    prescribing_doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id'))
    diagnosis = db.Column(db.Text)
    prescription_date = db.Column(db.Date)
    prescription_type = db.Column(db.String(20), default='initial')  # initial/followup
    status = db.Column(db.String(20), default='active')  # active/completed/cancelled
    insurance_type = db.Column(db.String(20))  # KVG/UVG/MVG/IVG/private/self
    billing_model = db.Column(db.String(20))  # tiers_garant/tiers_payant
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    appointments = db.relationship('Appointment', backref='series', lazy='dynamic')


class Appointment(db.Model):
    __tablename__ = 'appointments'
    id = db.Column(db.Integer, primary_key=True)
    series_id = db.Column(db.Integer, db.ForeignKey('treatment_series.id'))
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'))
    resource_id = db.Column(db.Integer, db.ForeignKey('resources.id'))
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default='scheduled')  # scheduled/completed/cancelled/no_show
    type = db.Column(db.String(20), default='treatment')  # treatment/admin/general/waiting_list/group
    notes = db.Column(db.Text)
    cancellation_reason = db.Column(db.Text)
    cancellation_fee = db.Column(db.Float, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    resource = db.relationship('Resource', backref='appointments')
    location = db.relationship('Location', backref='appointments')


class Resource(db.Model):
    __tablename__ = 'resources'
    id = db.Column(db.Integer, primary_key=True)
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    type = db.Column(db.String(20), default='room')  # room/equipment/other
    is_active = db.Column(db.Boolean, default=True)


# ============================================================
# Abrechnung
# ============================================================

class Invoice(db.Model):
    __tablename__ = 'invoices'
    id = db.Column(db.Integer, primary_key=True)
    series_id = db.Column(db.Integer, db.ForeignKey('treatment_series.id'))
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    insurance_provider_id = db.Column(db.Integer, db.ForeignKey('insurance_providers.id'))
    amount = db.Column(db.Float, default=0)
    status = db.Column(db.String(20), default='open')  # open/sent/answered/partially_paid/paid/in_collection
    billing_type = db.Column(db.String(20))  # KVG/UVG/MVG/IVG/private/self
    billing_model = db.Column(db.String(20))  # tiers_garant/tiers_payant
    due_date = db.Column(db.Date)
    sent_at = db.Column(db.DateTime)
    paid_at = db.Column(db.DateTime)
    dunning_level = db.Column(db.Integer, default=0)  # 0/1/2/3
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    items = db.relationship('InvoiceItem', backref='invoice', lazy='dynamic')
    payments = db.relationship('Payment', backref='invoice', lazy='dynamic')


class InvoiceItem(db.Model):
    __tablename__ = 'invoice_items'
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'), nullable=False)
    tariff_code = db.Column(db.String(20))
    description = db.Column(db.String(500))
    quantity = db.Column(db.Float, default=1)
    tax_points = db.Column(db.Float, default=0)
    tax_point_value = db.Column(db.Float, default=1.0)
    amount = db.Column(db.Float, default=0)


class Payment(db.Model):
    __tablename__ = 'payments'
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payment_date = db.Column(db.Date, nullable=False)
    reference = db.Column(db.String(200))
    source = db.Column(db.String(20), default='manual')  # manual/vesr/medidata


class CostApproval(db.Model):
    __tablename__ = 'cost_approvals'
    id = db.Column(db.Integer, primary_key=True)
    series_id = db.Column(db.Integer, db.ForeignKey('treatment_series.id'))
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    insurance_provider_id = db.Column(db.Integer, db.ForeignKey('insurance_providers.id'))
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id'))
    status = db.Column(db.String(20), default='pending')  # pending/sent/approved/rejected
    valid_until = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ============================================================
# Adressen (Versicherungen, Ärzte)
# ============================================================

class InsuranceProvider(db.Model):
    __tablename__ = 'insurance_providers'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    gln_number = db.Column(db.String(50))
    supports_electronic_billing = db.Column(db.Boolean, default=False)
    contact_json = db.Column(db.JSON, default=dict)


class Doctor(db.Model):
    __tablename__ = 'doctors'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    specialty = db.Column(db.String(100))
    gln_number = db.Column(db.String(50))
    zsr_number = db.Column(db.String(50))
    address = db.Column(db.String(500))
    phone = db.Column(db.String(50))


# ============================================================
# Aufgaben & Kommunikation
# ============================================================

class Task(db.Model):
    __tablename__ = 'tasks'
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'))
    category = db.Column(db.String(50))  # patient_data/insurance_data/doctor_assignment/findings/uvg_data/series_validation
    related_series_id = db.Column(db.Integer, db.ForeignKey('treatment_series.id'))
    related_patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'))
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='open')  # open/completed
    auto_generated = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Email(db.Model):
    __tablename__ = 'emails'
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'))
    from_address = db.Column(db.String(200))
    to_address = db.Column(db.String(200))
    subject = db.Column(db.String(500))
    body_html = db.Column(db.Text)
    status = db.Column(db.String(20), default='draft')  # draft/sent/delivered/read/rejected
    linked_patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'))
    linked_series_id = db.Column(db.Integer, db.ForeignKey('treatment_series.id'))
    linked_invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'))
    folder = db.Column(db.String(50), default='inbox')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ChatMessage(db.Model):
    __tablename__ = 'chat_messages'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # user/assistant
    content = db.Column(db.Text, nullable=False)
    tool_calls_json = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ============================================================
# Produkte
# ============================================================

class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'))
    name = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(100))
    net_price = db.Column(db.Float, default=0)
    unit_type = db.Column(db.String(20), default='piece')  # piece/cm/m/days/months
    tariff_code = db.Column(db.String(20))
    supplier = db.Column(db.String(200))
    article_number = db.Column(db.String(50))
