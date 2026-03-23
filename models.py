from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, time

db = SQLAlchemy()


# ============================================================
# Organisation & Standorte
# ============================================================

class Organization(db.Model):
    __tablename__ = 'organizations'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    address = db.Column(db.String(300))
    city = db.Column(db.String(100))
    zip_code = db.Column(db.String(10))
    phone = db.Column(db.String(30))
    email = db.Column(db.String(200))
    nif_number = db.Column(db.String(50))
    gln_number = db.Column(db.String(20))
    zsr_number = db.Column(db.String(20))
    uid_number = db.Column(db.String(30))
    logo_path = db.Column(db.String(500))
    settings_json = db.Column(db.Text)
    contact_person = db.Column(db.String(200))
    default_language = db.Column(db.String(5), default='de')
    opening_hours_json = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    locations = db.relationship('Location', backref='organization', lazy='dynamic')
    users = db.relationship('User', backref='organization', lazy='dynamic')
    employees = db.relationship('Employee', backref='organization', lazy='dynamic')
    patients = db.relationship('Patient', backref='organization', lazy='dynamic')
    contacts = db.relationship('Contact', backref='organization', lazy='dynamic')
    products = db.relationship('Product', backref='organization', lazy='dynamic')
    resources = db.relationship('Resource', backref='organization', lazy='dynamic')
    invoices = db.relationship('Invoice', backref='organization', lazy='dynamic')
    tasks = db.relationship('Task', backref='organization', lazy='dynamic')
    emails = db.relationship('Email', backref='organization', lazy='dynamic')
    bank_accounts = db.relationship('BankAccount', backref='organization', lazy='dynamic')
    holidays = db.relationship('Holiday', backref='organization', lazy='dynamic')


class Location(db.Model):
    __tablename__ = 'locations'
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    address = db.Column(db.String(300))
    city = db.Column(db.String(100))
    zip_code = db.Column(db.String(10))
    phone = db.Column(db.String(30))
    email = db.Column(db.String(200))
    opening_hours_json = db.Column(db.Text)
    holidays_json = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    resources = db.relationship('Resource', backref='location', lazy='dynamic')
    work_schedules = db.relationship('WorkSchedule', backref='location', lazy='dynamic')


# ============================================================
# Benutzer & Mitarbeiter
# ============================================================

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    name = db.Column(db.String(200))
    first_name = db.Column(db.String(100))
    last_name = db.Column(db.String(100))
    email = db.Column(db.String(200))
    role = db.Column(db.String(20), nullable=False, default='therapist')
    preferred_language = db.Column(db.String(5), default='de')
    dashboard_config_json = db.Column(db.Text)
    notification_preferences_json = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    last_login = db.Column(db.DateTime)
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
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    employee_number = db.Column(db.String(20))
    qualifications_json = db.Column(db.Text)
    specializations_json = db.Column(db.Text)
    employment_model = db.Column(db.String(50))
    pensum_percent = db.Column(db.Integer, default=100)
    zsr_number = db.Column(db.String(20))
    gln_number = db.Column(db.String(20))
    color_code = db.Column(db.String(7))
    default_location_id = db.Column(db.Integer, db.ForeignKey('locations.id'))
    default_room_id = db.Column(db.Integer, db.ForeignKey('resources.id'))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    default_location = db.relationship('Location', foreign_keys=[default_location_id])
    default_room = db.relationship('Resource', foreign_keys=[default_room_id])
    work_schedules = db.relationship('WorkSchedule', backref='employee', lazy='dynamic')
    absences = db.relationship('Absence', backref='employee', lazy='dynamic')
    appointments = db.relationship('Appointment', backref='employee', lazy='dynamic')
    treatment_series = db.relationship('TreatmentSeries', backref='therapist', lazy='dynamic')


class WorkSchedule(db.Model):
    __tablename__ = 'work_schedules'
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'))
    type = db.Column(db.String(20), default='regular')
    day_of_week = db.Column(db.Integer, nullable=False)  # 0=Montag, 6=Sonntag
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    work_type = db.Column(db.String(30), default='treatment')
    valid_from = db.Column(db.Date)
    valid_to = db.Column(db.Date)
    repeat_weeks = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Absence(db.Model):
    __tablename__ = 'absences'
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    absence_type = db.Column(db.String(30), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time)
    end_time = db.Column(db.Time)
    half_day = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(20), default='pending')
    requested_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Certificate(db.Model):
    """Zertifikate und Qualifikationsnachweise von Mitarbeitern"""
    __tablename__ = 'certificates'
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    issued_date = db.Column(db.Date)
    expiry_date = db.Column(db.Date)
    file_path = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    employee = db.relationship('Employee', backref=db.backref('certificates', lazy='dynamic'))


class AbsenceQuota(db.Model):
    """Abwesenheitskontingente pro Mitarbeiter und Jahr"""
    __tablename__ = 'absence_quotas'
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    absence_type = db.Column(db.String(50), default='vacation')
    total_days = db.Column(db.Float, nullable=False)
    used_days = db.Column(db.Float, default=0)
    carryover_days = db.Column(db.Float, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    employee = db.relationship('Employee', backref=db.backref('absence_quotas', lazy='dynamic'))


class Permission(db.Model):
    __tablename__ = 'permissions'
    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.String(20), nullable=False)
    module = db.Column(db.String(50), nullable=False)
    action = db.Column(db.String(50), nullable=False)
    is_allowed = db.Column(db.Boolean, default=True)


# ============================================================
# Patienten
# ============================================================

class Patient(db.Model):
    __tablename__ = 'patients'
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    patient_number = db.Column(db.String(20))
    salutation = db.Column(db.String(20))
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    date_of_birth = db.Column(db.Date)
    gender = db.Column(db.String(10))
    phone = db.Column(db.String(30))
    mobile = db.Column(db.String(30))
    email = db.Column(db.String(200))
    address = db.Column(db.String(300))
    city = db.Column(db.String(100))
    zip_code = db.Column(db.String(10))
    country = db.Column(db.String(5), default='CH')
    insurance_provider_id = db.Column(db.Integer, db.ForeignKey('insurance_providers.id'))
    insurance_number = db.Column(db.String(30))
    insurance_type = db.Column(db.String(10), default='KVG')
    ahv_number = db.Column(db.String(16))
    preferred_contact_method = db.Column(db.String(20), default='phone')
    preferred_appointment_times_json = db.Column(db.Text)
    blacklisted = db.Column(db.Boolean, default=False)
    blacklist_reason = db.Column(db.Text)
    employer_name = db.Column(db.String(200))
    employer_address = db.Column(db.String(300))
    notes = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Erweiterte Versicherungsfelder
    case_number = db.Column(db.String(30))  # Fallnummer bei UVG/IVG
    accident_date = db.Column(db.Date)  # Unfalldatum bei UVG
    supplementary_insurance_name = db.Column(db.String(200))
    supplementary_insurance_number = db.Column(db.String(30))
    # Erweiterte Kontaktfelder
    preferred_language = db.Column(db.String(20), default='Deutsch')
    # Arbeitgeber erweitert
    employer_contact = db.Column(db.String(200))
    employer_phone = db.Column(db.String(30))
    # Bevorzugter Therapeut
    preferred_therapist_id = db.Column(db.Integer, db.ForeignKey('employees.id'))

    insurance_provider = db.relationship('InsuranceProvider', backref='patients')
    preferred_therapist = db.relationship('Employee', foreign_keys=[preferred_therapist_id])
    treatment_series = db.relationship('TreatmentSeries', backref='patient', lazy='dynamic')
    appointments = db.relationship('Appointment', backref='patient', lazy='dynamic')
    invoices = db.relationship('Invoice', backref='patient', lazy='dynamic')
    documents = db.relationship('PatientDocument', backref='patient', lazy='dynamic')


class PatientDocument(db.Model):
    """Dokumente die einem Patienten zugeordnet sind"""
    __tablename__ = 'patient_documents'
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.Integer)
    file_type = db.Column(db.String(50))
    document_type = db.Column(db.String(50))  # verordnung, arztbericht, befund, foto, sonstiges
    notes = db.Column(db.Text)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    uploaded_by = db.relationship('User', backref='uploaded_documents')


# ============================================================
# Adressen (Kontakte)
# ============================================================

class InsuranceProvider(db.Model):
    __tablename__ = 'insurance_providers'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    gln_number = db.Column(db.String(20))
    address = db.Column(db.String(300))
    city = db.Column(db.String(100))
    zip_code = db.Column(db.String(10))
    phone = db.Column(db.String(30))
    email = db.Column(db.String(200))
    fax = db.Column(db.String(30))
    supports_electronic_billing = db.Column(db.Boolean, default=False)
    supports_tiers_payant_json = db.Column(db.Text)
    contact_json = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Doctor(db.Model):
    __tablename__ = 'doctors'
    id = db.Column(db.Integer, primary_key=True)
    salutation = db.Column(db.String(20))
    first_name = db.Column(db.String(100))
    last_name = db.Column(db.String(100), nullable=False)
    specialty = db.Column(db.String(100))
    gln_number = db.Column(db.String(20))
    zsr_number = db.Column(db.String(20))
    address = db.Column(db.String(300))
    city = db.Column(db.String(100))
    zip_code = db.Column(db.String(10))
    phone = db.Column(db.String(30))
    email = db.Column(db.String(200))
    fax = db.Column(db.String(30))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    treatment_series = db.relationship('TreatmentSeries', backref='prescribing_doctor', lazy='dynamic')


class Contact(db.Model):
    __tablename__ = 'contacts'
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    category = db.Column(db.String(50))
    company_name = db.Column(db.String(200))
    first_name = db.Column(db.String(100))
    last_name = db.Column(db.String(100))
    address = db.Column(db.String(300))
    city = db.Column(db.String(100))
    zip_code = db.Column(db.String(10))
    phone = db.Column(db.String(30))
    email = db.Column(db.String(200))
    notes = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ============================================================
# Produkte & Ressourcen
# ============================================================

class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    category = db.Column(db.String(50))
    net_price = db.Column(db.Float, default=0.0)
    vat_rate = db.Column(db.Float, default=0.0)
    unit_type = db.Column(db.String(20))
    tariff_code = db.Column(db.String(20))
    supplier = db.Column(db.String(200))
    manufacturer = db.Column(db.String(200))
    article_number = db.Column(db.String(50))
    stock_quantity = db.Column(db.Integer, default=0)
    min_stock = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Resource(db.Model):
    __tablename__ = 'resources'
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'))
    name = db.Column(db.String(200), nullable=False)
    resource_type = db.Column(db.String(30), nullable=False)
    description = db.Column(db.Text)
    capacity = db.Column(db.Integer, default=1)
    equipment_json = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    bookings = db.relationship('ResourceBooking', backref='resource', lazy='dynamic')


class ProductPriceHistory(db.Model):
    """Preis-Historie fuer Produkte"""
    __tablename__ = 'product_price_history'
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    old_price = db.Column(db.Float, nullable=False)
    new_price = db.Column(db.Float, nullable=False)
    changed_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    changed_at = db.Column(db.DateTime, default=datetime.utcnow)

    product = db.relationship('Product', backref=db.backref('price_history', lazy='dynamic', order_by='ProductPriceHistory.changed_at.desc()'))
    changed_by = db.relationship('User', backref='price_changes')


class MaintenanceRecord(db.Model):
    """Wartungshistorie fuer Geraete"""
    __tablename__ = 'maintenance_records'
    id = db.Column(db.Integer, primary_key=True)
    resource_id = db.Column(db.Integer, db.ForeignKey('resources.id'), nullable=False)
    maintenance_type = db.Column(db.String(50), default='regular')
    description = db.Column(db.Text)
    performed_at = db.Column(db.Date, nullable=False)
    performed_by = db.Column(db.String(200))
    next_due = db.Column(db.Date)
    interval_months = db.Column(db.Integer)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    resource = db.relationship('Resource', backref=db.backref('maintenance_records', lazy='dynamic', order_by='MaintenanceRecord.performed_at.desc()'))


class ResourceBooking(db.Model):
    __tablename__ = 'resource_bookings'
    id = db.Column(db.Integer, primary_key=True)
    resource_id = db.Column(db.Integer, db.ForeignKey('resources.id'), nullable=False)
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointments.id'))
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ============================================================
# Behandlungsserien & Termine
# ============================================================

class TreatmentSeriesTemplate(db.Model):
    __tablename__ = 'treatment_series_templates'
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    short_name = db.Column(db.String(20))
    tariff_type = db.Column(db.String(20))
    num_appointments = db.Column(db.Integer, default=9)
    duration_minutes = db.Column(db.Integer, default=30)
    min_interval_days = db.Column(db.Integer, default=1)
    default_location_id = db.Column(db.Integer, db.ForeignKey('locations.id'))
    group_therapy = db.Column(db.Boolean, default=False)
    max_group_size = db.Column(db.Integer)
    requires_resource = db.Column(db.Boolean, default=False)
    resource_type = db.Column(db.String(30))
    auto_billing_after = db.Column(db.Integer)
    cancellation_fee_type = db.Column(db.String(20))
    cancellation_fee_amount = db.Column(db.Float)
    settings_json = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    organization = db.relationship('Organization', backref='templates')
    default_location = db.relationship('Location', foreign_keys=[default_location_id])


class TreatmentSeries(db.Model):
    __tablename__ = 'treatment_series'
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    template_id = db.Column(db.Integer, db.ForeignKey('treatment_series_templates.id'))
    therapist_id = db.Column(db.Integer, db.ForeignKey('employees.id'))
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'))
    prescribing_doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id'))
    diagnosis_code = db.Column(db.String(20))
    diagnosis_text = db.Column(db.String(500))
    prescription_date = db.Column(db.Date)
    prescription_type = db.Column(db.String(30))
    prescription_document_path = db.Column(db.String(500))
    status = db.Column(db.String(20), default='active')
    insurance_type = db.Column(db.String(10), default='KVG')
    billing_model = db.Column(db.String(20), default='tiers_garant')
    healing_phase = db.Column(db.String(20))
    notes = db.Column(db.Text)
    cost_approval_id = db.Column(db.Integer, db.ForeignKey('cost_approvals.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)

    template = db.relationship('TreatmentSeriesTemplate', backref='series')
    location = db.relationship('Location', foreign_keys=[location_id])
    appointments = db.relationship('Appointment', backref='series', lazy='dynamic')
    invoices = db.relationship('Invoice', backref='series', lazy='dynamic')


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
    duration_minutes = db.Column(db.Integer, default=30)
    status = db.Column(db.String(20), default='scheduled')
    appointment_type = db.Column(db.String(30), default='treatment')
    title = db.Column(db.String(200))
    notes = db.Column(db.Text)
    soap_subjective = db.Column(db.Text)
    soap_objective = db.Column(db.Text)
    soap_assessment = db.Column(db.Text)
    soap_plan = db.Column(db.Text)
    cancellation_reason = db.Column(db.Text)
    cancellation_fee = db.Column(db.Float)
    is_domicile = db.Column(db.Boolean, default=False)
    domicile_address = db.Column(db.String(300))
    travel_time_minutes = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    location = db.relationship('Location', foreign_keys=[location_id])
    resource = db.relationship('Resource', foreign_keys=[resource_id])
    resource_bookings = db.relationship('ResourceBooking', backref='appointment', lazy='dynamic')


# ============================================================
# Abrechnung
# ============================================================

class Invoice(db.Model):
    __tablename__ = 'invoices'
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    series_id = db.Column(db.Integer, db.ForeignKey('treatment_series.id'))
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'))
    insurance_provider_id = db.Column(db.Integer, db.ForeignKey('insurance_providers.id'))
    invoice_number = db.Column(db.String(30), unique=True)
    amount_total = db.Column(db.Float, default=0.0)
    amount_paid = db.Column(db.Float, default=0.0)
    amount_open = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(20), default='draft')
    billing_type = db.Column(db.String(20))
    billing_model = db.Column(db.String(20))
    tax_point_value = db.Column(db.Float)
    due_date = db.Column(db.Date)
    sent_at = db.Column(db.DateTime)
    sent_via = db.Column(db.String(20))
    paid_at = db.Column(db.DateTime)
    dunning_level = db.Column(db.Integer, default=0)
    dunning_1_date = db.Column(db.Date)
    dunning_2_date = db.Column(db.Date)
    dunning_3_date = db.Column(db.Date)
    category = db.Column(db.String(30))  # treatment, fitness, etc.
    notes = db.Column(db.Text)
    pdf_path = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    insurance_provider = db.relationship('InsuranceProvider', backref='invoices')
    items = db.relationship('InvoiceItem', backref='invoice', lazy='dynamic')
    payments = db.relationship('Payment', backref='invoice', lazy='dynamic')


class InvoiceItem(db.Model):
    __tablename__ = 'invoice_items'
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'), nullable=False)
    position = db.Column(db.Integer)
    tariff_code = db.Column(db.String(20))
    description = db.Column(db.String(500))
    quantity = db.Column(db.Float, default=1.0)
    tax_points = db.Column(db.Float, default=0.0)
    tax_point_value = db.Column(db.Float, default=0.0)
    amount = db.Column(db.Float, default=0.0)
    vat_rate = db.Column(db.Float, default=0.0)
    vat_amount = db.Column(db.Float, default=0.0)


class Payment(db.Model):
    __tablename__ = 'payments'
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payment_date = db.Column(db.Date, nullable=False)
    payment_method = db.Column(db.String(30))
    reference = db.Column(db.String(50))
    source = db.Column(db.String(30))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class TaxPointValue(db.Model):
    __tablename__ = 'tax_point_values'
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    tariff_type = db.Column(db.String(20), nullable=False)
    value = db.Column(db.Float, nullable=False)
    valid_from = db.Column(db.Date, nullable=False)
    valid_to = db.Column(db.Date)
    canton = db.Column(db.String(5))
    insurer_id = db.Column(db.Integer, db.ForeignKey('insurance_providers.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    organization = db.relationship('Organization', backref='tax_point_values')
    insurer = db.relationship('InsuranceProvider', backref='tax_point_values')


class BankAccount(db.Model):
    __tablename__ = 'bank_accounts'
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    bank_name = db.Column(db.String(200))
    iban = db.Column(db.String(34), nullable=False)
    qr_iban = db.Column(db.String(34))
    bic_swift = db.Column(db.String(11))
    account_name = db.Column(db.String(200))
    is_default = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class DunningRecord(db.Model):
    """Mahnungshistorie fuer Rechnungen"""
    __tablename__ = 'dunning_records'
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'), nullable=False)
    dunning_level = db.Column(db.Integer, nullable=False)  # 1, 2, 3
    dunning_date = db.Column(db.Date, nullable=False)
    dunning_fee = db.Column(db.Float, default=0)
    dunning_text = db.Column(db.Text)
    sent_via = db.Column(db.String(50))  # email, print, medidata
    pdf_path = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    invoice = db.relationship('Invoice', backref=db.backref('dunning_records', lazy='dynamic', order_by='DunningRecord.dunning_date.desc()'))


class Holiday(db.Model):
    __tablename__ = 'holidays'
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=True)
    name = db.Column(db.String(100), nullable=False)
    date = db.Column(db.Date, nullable=False)
    canton = db.Column(db.String(5))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    location = db.relationship('Location', backref='holidays')


# ============================================================
# Gutsprachen
# ============================================================

class CostApproval(db.Model):
    __tablename__ = 'cost_approvals'
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    approval_number = db.Column(db.String(30))
    series_id = db.Column(db.Integer, db.ForeignKey('treatment_series.id'))
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'))
    insurance_provider_id = db.Column(db.Integer, db.ForeignKey('insurance_providers.id'))
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id'))
    therapist_id = db.Column(db.Integer, db.ForeignKey('employees.id'))
    status = db.Column(db.String(20), default='draft')  # draft, sent, answered, approved, partially_approved, rejected, cancelled
    requested_date = db.Column(db.Date)
    sent_date = db.Column(db.Date)
    response_date = db.Column(db.Date)
    valid_until = db.Column(db.Date)
    requested_sessions = db.Column(db.Integer)
    approved_sessions = db.Column(db.Integer)
    approved_amount = db.Column(db.Float)
    total_amount = db.Column(db.Float)
    rejection_reason = db.Column(db.Text)
    justification = db.Column(db.Text)  # Begruendungstext an Versicherer
    diagnosis_code = db.Column(db.String(20))
    diagnosis_text = db.Column(db.String(500))
    prescription_date = db.Column(db.Date)
    prescription_type = db.Column(db.String(30))  # Erst-/Folgeverordnung
    notes = db.Column(db.Text)
    response_notes = db.Column(db.Text)  # Bemerkung des Kostentraegers
    pdf_path = db.Column(db.String(500))
    prescription_document_path = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    items = db.relationship('CostApprovalItem', backref='cost_approval', lazy='dynamic')
    patient = db.relationship('Patient', backref='cost_approvals')
    insurance_provider = db.relationship('InsuranceProvider', backref='cost_approvals')
    doctor = db.relationship('Doctor', backref='cost_approvals')
    therapist = db.relationship('Employee', backref='cost_approvals')
    series = db.relationship('TreatmentSeries', backref='cost_approval_ref', foreign_keys=[series_id])


class CostApprovalItem(db.Model):
    __tablename__ = 'cost_approval_items'
    id = db.Column(db.Integer, primary_key=True)
    cost_approval_id = db.Column(db.Integer, db.ForeignKey('cost_approvals.id'), nullable=False)
    tariff_code = db.Column(db.String(20))
    description = db.Column(db.String(500))
    quantity = db.Column(db.Float, default=1.0)
    amount = db.Column(db.Float, default=0.0)
    comment = db.Column(db.Text)


# ============================================================
# Aufgaben
# ============================================================

class Task(db.Model):
    __tablename__ = 'tasks'
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    task_type = db.Column(db.String(30))
    category = db.Column(db.String(30))
    title = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text)
    related_patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'))
    related_series_id = db.Column(db.Integer, db.ForeignKey('treatment_series.id'))
    related_invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'))
    assigned_to_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    priority = db.Column(db.String(10), default='normal')
    status = db.Column(db.String(20), default='open')
    due_date = db.Column(db.Date)
    completed_at = db.Column(db.DateTime)
    auto_generated = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    related_patient = db.relationship('Patient', backref='tasks')
    related_series = db.relationship('TreatmentSeries', backref='tasks')
    related_invoice = db.relationship('Invoice', backref='tasks')
    assigned_to = db.relationship('User', foreign_keys=[assigned_to_id], backref='assigned_tasks')
    created_by = db.relationship('User', foreign_keys=[created_by_id], backref='created_tasks')
    comments = db.relationship('TaskComment', backref='task', lazy='dynamic', order_by='TaskComment.created_at')


class TaskComment(db.Model):
    """Kommentare zu Aufgaben"""
    __tablename__ = 'task_comments'
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    comment = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='task_comments')


# ============================================================
# Kommunikation
# ============================================================

class Email(db.Model):
    __tablename__ = 'emails'
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    from_address = db.Column(db.String(200))
    to_address = db.Column(db.String(200))
    cc = db.Column(db.String(500))
    bcc = db.Column(db.String(500))
    subject = db.Column(db.String(500))
    body_html = db.Column(db.Text)
    body_text = db.Column(db.Text)
    status = db.Column(db.String(20), default='draft')
    folder = db.Column(db.String(30), default='inbox')
    linked_patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'))
    linked_series_id = db.Column(db.Integer, db.ForeignKey('treatment_series.id'))
    linked_invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'))
    linked_cost_approval_id = db.Column(db.Integer, db.ForeignKey('cost_approvals.id'))
    has_attachments = db.Column(db.Boolean, default=False)
    read_at = db.Column(db.DateTime)
    sent_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    attachments = db.relationship('EmailAttachment', backref='email', lazy='dynamic')


class EmailAttachment(db.Model):
    __tablename__ = 'email_attachments'
    id = db.Column(db.Integer, primary_key=True)
    email_id = db.Column(db.Integer, db.ForeignKey('emails.id'), nullable=False)
    filename = db.Column(db.String(300))
    filepath = db.Column(db.String(500))
    filesize = db.Column(db.Integer)
    mimetype = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class EmailFolder(db.Model):
    """Eigene E-Mail-Ordner pro Organisation"""
    __tablename__ = 'email_folders'
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    organization = db.relationship('Organization', backref=db.backref('email_folders', lazy='dynamic'))


class ChatMessage(db.Model):
    __tablename__ = 'chat_messages'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    content = db.Column(db.Text, nullable=False)
    tool_calls_json = db.Column(db.Text)
    agent_name = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ============================================================
# KI-Einstellungen
# ============================================================

class AISettings(db.Model):
    __tablename__ = 'ai_settings'
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    intensity_level = db.Column(db.String(10), default='medium')
    budget_monthly = db.Column(db.Float, default=100.0)
    budget_used = db.Column(db.Float, default=0.0)
    features_enabled_json = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    organization = db.relationship('Organization', backref='ai_settings')


# ============================================================
# Warteliste
# ============================================================

class WaitingList(db.Model):
    __tablename__ = 'waiting_list'
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'))
    template_id = db.Column(db.Integer, db.ForeignKey('treatment_series_templates.id'))
    preferred_employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=True)
    preferred_days_json = db.Column(db.Text)  # [0,1,2] = Mo,Di,Mi
    preferred_times_json = db.Column(db.Text)  # ["08:00-12:00", "14:00-17:00"]
    priority = db.Column(db.Integer, default=0)
    notes = db.Column(db.Text)
    status = db.Column(db.String(20), default='waiting')  # waiting, contacted, scheduled, cancelled
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    patient = db.relationship('Patient', backref=db.backref('waiting_list_entries', lazy='dynamic'))
    template = db.relationship('TreatmentSeriesTemplate', backref='waiting_list_entries')
    preferred_employee = db.relationship('Employee', backref='waiting_list_entries')


# ============================================================
# Audit
# ============================================================

class TherapyGoal(db.Model):
    """Therapieziele pro Serie/Patient"""
    __tablename__ = 'therapy_goals'
    id = db.Column(db.Integer, primary_key=True)
    series_id = db.Column(db.Integer, db.ForeignKey('treatment_series.id'))
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'))
    description = db.Column(db.Text, nullable=False)
    target_value = db.Column(db.String(100))
    current_value = db.Column(db.String(100))
    achievement_percent = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default='open')  # open, in_progress, achieved
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    series = db.relationship('TreatmentSeries', backref=db.backref('goals', lazy='dynamic'))
    patient = db.relationship('Patient', backref=db.backref('therapy_goals', lazy='dynamic'))


class Milestone(db.Model):
    """Meilensteine im Behandlungsverlauf"""
    __tablename__ = 'milestones'
    id = db.Column(db.Integer, primary_key=True)
    series_id = db.Column(db.Integer, db.ForeignKey('treatment_series.id'))
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'))
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    target_date = db.Column(db.Date)
    achieved_date = db.Column(db.Date)
    criteria = db.Column(db.Text)
    status = db.Column(db.String(20), default='open')  # open, current, achieved
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    series = db.relationship('TreatmentSeries', backref=db.backref('milestones', lazy='dynamic'))
    patient = db.relationship('Patient', backref=db.backref('milestones', lazy='dynamic'))


class Measurement(db.Model):
    """Messwerte und Assessments"""
    __tablename__ = 'measurements'
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    series_id = db.Column(db.Integer, db.ForeignKey('treatment_series.id'), nullable=True)
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointments.id'), nullable=True)
    measurement_type = db.Column(db.String(50), nullable=False)  # nprs, vas, odi, ndi, dash, custom
    name = db.Column(db.String(200))
    value_json = db.Column(db.Text)  # {"value": 7} oder {"systolic": 120, "diastolic": 80}
    unit = db.Column(db.String(50))
    measured_at = db.Column(db.DateTime, nullable=False)
    measured_by_id = db.Column(db.Integer, db.ForeignKey('employees.id'))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    patient = db.relationship('Patient', backref=db.backref('measurements', lazy='dynamic'))
    series = db.relationship('TreatmentSeries', backref=db.backref('measurements', lazy='dynamic'))
    appointment = db.relationship('Appointment', backref=db.backref('measurements', lazy='dynamic'))
    measured_by = db.relationship('Employee', backref=db.backref('measurements_taken', lazy='dynamic'))


class HealingPhase(db.Model):
    """Heilungsphasen einer Behandlungsserie"""
    __tablename__ = 'healing_phases'
    id = db.Column(db.Integer, primary_key=True)
    series_id = db.Column(db.Integer, db.ForeignKey('treatment_series.id'), nullable=False)
    phase_type = db.Column(db.String(30), nullable=False)  # initial, treatment, consolidation, autonomy
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    series = db.relationship('TreatmentSeries', backref=db.backref('healing_phases', lazy='dynamic'))


# ============================================================
# Audit
# ============================================================

class SystemSetting(db.Model):
    """Zentrale Systemeinstellungen als Key-Value-Paare"""
    __tablename__ = 'system_settings'
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    key = db.Column(db.String(100), nullable=False)
    value = db.Column(db.Text)
    value_type = db.Column(db.String(20), default='string')  # string, integer, boolean, json
    category = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

    organization = db.relationship('Organization', backref=db.backref('system_settings', lazy='dynamic'))

    __table_args__ = (
        db.UniqueConstraint('organization_id', 'key', name='uix_org_setting_key'),
    )


class EmailTemplate(db.Model):
    """E-Mail-Vorlagen fuer automatische und manuelle E-Mails"""
    __tablename__ = 'email_templates'
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    template_type = db.Column(db.String(50))  # reminder, confirmation, cancellation, recall, welcome
    subject = db.Column(db.String(500))
    body_html = db.Column(db.Text)
    placeholders_json = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    organization = db.relationship('Organization', backref=db.backref('email_templates', lazy='dynamic'))


class PrintTemplate(db.Model):
    """Druckvorlagen fuer Rechnungen, Mahnungen, Berichte etc."""
    __tablename__ = 'print_templates'
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    template_type = db.Column(db.String(50))  # invoice, dunning, prescription, report, confirmation
    body_html = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    organization = db.relationship('Organization', backref=db.backref('print_templates', lazy='dynamic'))


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    action = db.Column(db.String(50), nullable=False)
    entity_type = db.Column(db.String(50))
    entity_id = db.Column(db.Integer)
    changes_json = db.Column(db.Text)
    ip_address = db.Column(db.String(45))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='audit_logs')


# ============================================================
# Finanzbuchhaltung
# ============================================================

class Account(db.Model):
    """Kontenplan fuer doppelte Buchhaltung nach Schweizer KMU-Kontenrahmen"""
    __tablename__ = 'accounts'
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    account_number = db.Column(db.String(10), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    account_type = db.Column(db.String(20))  # asset, liability, equity, income, expense
    parent_account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=True)
    vat_code = db.Column(db.String(20))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    organization = db.relationship('Organization', backref=db.backref('accounts', lazy='dynamic'))
    parent_account = db.relationship('Account', remote_side='Account.id', backref='sub_accounts')
    journal_lines = db.relationship('JournalEntryLine', backref='account', lazy='dynamic')


class JournalEntry(db.Model):
    """Buchungsjournal-Eintrag (Kopf)"""
    __tablename__ = 'journal_entries'
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    entry_number = db.Column(db.String(20))
    date = db.Column(db.Date, nullable=False)
    description = db.Column(db.String(500), nullable=False)
    reference = db.Column(db.String(100))
    source = db.Column(db.String(50))  # manual, invoice, payment, salary, depreciation, storno
    source_id = db.Column(db.Integer)
    is_storno = db.Column(db.Boolean, default=False)
    storno_of_id = db.Column(db.Integer, db.ForeignKey('journal_entries.id'), nullable=True)
    is_recurring = db.Column(db.Boolean, default=False)
    recurring_interval = db.Column(db.String(20))  # monthly, quarterly, yearly
    attachment_path = db.Column(db.String(500))
    period_locked = db.Column(db.Boolean, default=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    organization = db.relationship('Organization', backref=db.backref('journal_entries', lazy='dynamic'))
    created_by = db.relationship('User', backref='journal_entries')
    storno_of = db.relationship('JournalEntry', remote_side='JournalEntry.id', backref='storno_entries')
    lines = db.relationship('JournalEntryLine', backref='entry', lazy='dynamic', cascade='all, delete-orphan')


class JournalEntryLine(db.Model):
    """Einzelne Buchungszeile (Soll/Haben)"""
    __tablename__ = 'journal_entry_lines'
    id = db.Column(db.Integer, primary_key=True)
    entry_id = db.Column(db.Integer, db.ForeignKey('journal_entries.id'), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'), nullable=False)
    debit = db.Column(db.Float, default=0)
    credit = db.Column(db.Float, default=0)
    vat_code = db.Column(db.String(20))
    vat_amount = db.Column(db.Float, default=0)
    cost_center_id = db.Column(db.Integer, db.ForeignKey('cost_centers.id'), nullable=True)
    description = db.Column(db.String(500))


class CreditorInvoice(db.Model):
    """Kreditoren-Rechnungen (Lieferantenrechnungen)"""
    __tablename__ = 'creditor_invoices'
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    contact_id = db.Column(db.Integer, db.ForeignKey('contacts.id'), nullable=True)
    creditor_name = db.Column(db.String(200))
    invoice_number = db.Column(db.String(50))
    invoice_date = db.Column(db.Date)
    due_date = db.Column(db.Date)
    amount = db.Column(db.Float, nullable=False)
    vat_amount = db.Column(db.Float, default=0)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'))
    status = db.Column(db.String(20), default='open')  # open, approved, paid
    attachment_path = db.Column(db.String(500))
    journal_entry_id = db.Column(db.Integer, db.ForeignKey('journal_entries.id'), nullable=True)
    payment_journal_entry_id = db.Column(db.Integer, db.ForeignKey('journal_entries.id'), nullable=True)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    organization = db.relationship('Organization', backref=db.backref('creditor_invoices', lazy='dynamic'))
    contact = db.relationship('Contact', backref='creditor_invoices')
    account = db.relationship('Account', foreign_keys=[account_id])
    journal_entry = db.relationship('JournalEntry', foreign_keys=[journal_entry_id])
    payment_journal_entry = db.relationship('JournalEntry', foreign_keys=[payment_journal_entry_id])


class FixedAsset(db.Model):
    """Anlagenbuchhaltung"""
    __tablename__ = 'fixed_assets'
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(50))  # furniture, devices, it, vehicles
    acquisition_date = db.Column(db.Date, nullable=False)
    acquisition_value = db.Column(db.Float, nullable=False)
    useful_life_years = db.Column(db.Integer, nullable=False)
    depreciation_method = db.Column(db.String(20), default='linear')  # linear, degressive
    current_book_value = db.Column(db.Float)
    account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'))
    depreciation_account_id = db.Column(db.Integer, db.ForeignKey('accounts.id'))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    organization = db.relationship('Organization', backref=db.backref('fixed_assets', lazy='dynamic'))
    account = db.relationship('Account', foreign_keys=[account_id])
    depreciation_account = db.relationship('Account', foreign_keys=[depreciation_account_id])


class CostCenter(db.Model):
    """Kostenstellen"""
    __tablename__ = 'cost_centers'
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    code = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    organization = db.relationship('Organization', backref=db.backref('cost_centers', lazy='dynamic'))
    location = db.relationship('Location', backref='cost_centers')


class PeriodLock(db.Model):
    """Periodensperre (Monats-/Jahresabschluss)"""
    __tablename__ = 'period_locks'
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)  # 0 = ganzes Jahr
    locked_at = db.Column(db.DateTime)
    locked_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    organization = db.relationship('Organization', backref=db.backref('period_locks', lazy='dynamic'))
    locked_by = db.relationship('User', backref='period_locks')


# ============================================================
# HR & Lohnbuchhaltung
# ============================================================

class EmployeeContract(db.Model):
    """Arbeitsvertraege der Mitarbeiter"""
    __tablename__ = 'employee_contracts'
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    contract_type = db.Column(db.String(20), default='permanent')  # permanent, temporary
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date)
    probation_end = db.Column(db.Date)
    notice_period_months = db.Column(db.Integer, default=1)
    pensum_percent = db.Column(db.Integer, default=100)
    vacation_days = db.Column(db.Integer, default=20)
    document_path = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    employee = db.relationship('Employee', backref=db.backref('contracts', lazy='dynamic'))


class EmployeeSalary(db.Model):
    """Lohndaten mit Historie"""
    __tablename__ = 'employee_salaries'
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    salary_type = db.Column(db.String(20), default='monthly')  # monthly, hourly
    amount = db.Column(db.Float, nullable=False)
    hourly_rate = db.Column(db.Float)
    thirteenth_month = db.Column(db.Boolean, default=True)
    iban = db.Column(db.String(34))
    ahv_number = db.Column(db.String(20))
    withholding_tax = db.Column(db.Boolean, default=False)
    withholding_tax_code = db.Column(db.String(10))
    withholding_tax_canton = db.Column(db.String(5))
    bvg_rate = db.Column(db.Float, default=7.0)  # BVG-Beitragssatz in %
    nbuv_rate = db.Column(db.Float, default=1.5)  # NBUV-Satz in %
    ktg_rate = db.Column(db.Float, default=0.5)  # KTG-Satz in %
    valid_from = db.Column(db.Date, nullable=False)
    valid_to = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    employee = db.relationship('Employee', backref=db.backref('salaries', lazy='dynamic'))


class EmployeeChild(db.Model):
    """Kinder der Mitarbeiter fuer Kinderzulagen"""
    __tablename__ = 'employee_children'
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    first_name = db.Column(db.String(100))
    last_name = db.Column(db.String(100))
    date_of_birth = db.Column(db.Date)
    allowance_type = db.Column(db.String(20), default='child')  # child (200/Mt), education (250/Mt)
    allowance_amount = db.Column(db.Float, default=200.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    employee = db.relationship('Employee', backref=db.backref('children', lazy='dynamic'))


class PayrollRun(db.Model):
    """Lohnlauf (monatlich)"""
    __tablename__ = 'payroll_runs'
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='draft')  # draft, calculated, approved, paid
    total_gross = db.Column(db.Float, default=0)
    total_net = db.Column(db.Float, default=0)
    total_employer_contributions = db.Column(db.Float, default=0)
    journal_entry_id = db.Column(db.Integer, db.ForeignKey('journal_entries.id'), nullable=True)
    approved_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    approved_at = db.Column(db.DateTime)
    paid_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    organization = db.relationship('Organization', backref=db.backref('payroll_runs', lazy='dynamic'))
    approved_by = db.relationship('User', backref='approved_payroll_runs')
    journal_entry = db.relationship('JournalEntry', backref='payroll_run')
    payslips = db.relationship('Payslip', backref='payroll_run', lazy='dynamic')


class Payslip(db.Model):
    """Lohnabrechnung pro Mitarbeiter pro Monat"""
    __tablename__ = 'payslips'
    id = db.Column(db.Integer, primary_key=True)
    payroll_run_id = db.Column(db.Integer, db.ForeignKey('payroll_runs.id'), nullable=False)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    # Bruttolohn-Komponenten
    gross_salary = db.Column(db.Float, default=0)
    thirteenth_month = db.Column(db.Float, default=0)
    child_allowance = db.Column(db.Float, default=0)
    bonuses = db.Column(db.Float, default=0)
    expenses_total = db.Column(db.Float, default=0)
    overtime_payout = db.Column(db.Float, default=0)
    gross_total = db.Column(db.Float, default=0)
    # Arbeitnehmer-Abzuege
    ahv_iv_eo = db.Column(db.Float, default=0)
    alv = db.Column(db.Float, default=0)
    alv2 = db.Column(db.Float, default=0)
    bvg = db.Column(db.Float, default=0)
    nbuv = db.Column(db.Float, default=0)
    ktg = db.Column(db.Float, default=0)
    withholding_tax = db.Column(db.Float, default=0)
    deductions_total = db.Column(db.Float, default=0)
    net_salary = db.Column(db.Float, default=0)
    # Arbeitgeber-Beitraege
    employer_ahv_iv_eo = db.Column(db.Float, default=0)
    employer_alv = db.Column(db.Float, default=0)
    employer_bvg = db.Column(db.Float, default=0)
    employer_uvg = db.Column(db.Float, default=0)
    employer_ktg = db.Column(db.Float, default=0)
    employer_fak = db.Column(db.Float, default=0)  # Familienzulagen-Beitrag
    employer_vk = db.Column(db.Float, default=0)  # Verwaltungskosten AHV
    employer_total = db.Column(db.Float, default=0)
    # Details
    pdf_path = db.Column(db.String(500))
    details_json = db.Column(db.Text)

    employee = db.relationship('Employee', backref=db.backref('payslips', lazy='dynamic'))


class TimeEntry(db.Model):
    """Zeiterfassungs-Eintraege"""
    __tablename__ = 'time_entries'
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    clock_in = db.Column(db.Time)
    clock_out = db.Column(db.Time)
    break_minutes = db.Column(db.Integer, default=0)
    worked_minutes = db.Column(db.Integer, default=0)
    entry_type = db.Column(db.String(20), default='manual')  # manual, clock, auto_calendar
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    employee = db.relationship('Employee', backref=db.backref('time_entries', lazy='dynamic'))


class OvertimeAccount(db.Model):
    """Ueberstundenkonto pro Mitarbeiter pro Monat"""
    __tablename__ = 'overtime_accounts'
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    month = db.Column(db.Integer, nullable=False)
    target_minutes = db.Column(db.Integer, default=0)  # Soll
    actual_minutes = db.Column(db.Integer, default=0)  # Ist
    overtime_minutes = db.Column(db.Integer, default=0)  # Differenz
    cumulative_overtime = db.Column(db.Integer, default=0)  # Kumuliert

    employee = db.relationship('Employee', backref=db.backref('overtime_accounts', lazy='dynamic'))


class Expense(db.Model):
    """Spesen der Mitarbeiter"""
    __tablename__ = 'expenses'
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employees.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    description = db.Column(db.String(500), nullable=False)
    category = db.Column(db.String(50))  # travel, meals, material, training, other
    amount = db.Column(db.Float, nullable=False)
    vat_amount = db.Column(db.Float, default=0)
    receipt_path = db.Column(db.String(500))
    status = db.Column(db.String(20), default='submitted')  # submitted, approved, rejected, paid
    approved_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    approved_at = db.Column(db.DateTime)
    paid_via = db.Column(db.String(20))  # payroll, separate
    payroll_run_id = db.Column(db.Integer, db.ForeignKey('payroll_runs.id'), nullable=True)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    employee = db.relationship('Employee', backref=db.backref('expenses', lazy='dynamic'))
    approved_by = db.relationship('User', backref='approved_expenses')
    payroll_run = db.relationship('PayrollRun', backref='expenses')


# ============================================================
# Auswertung & Kennzahlen
# ============================================================

class SavedReport(db.Model):
    """Gespeicherte Auswertungen (Report-Builder)"""
    __tablename__ = 'saved_reports'
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    name = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(50), nullable=False)  # patients, appointments, series, invoices, employees, products
    filters_json = db.Column(db.Text)  # JSON mit Filter-Konfiguration
    columns_json = db.Column(db.Text)  # JSON mit ausgewaehlten Spalten
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    organization = db.relationship('Organization', backref=db.backref('saved_reports', lazy='dynamic'))
    user = db.relationship('User', backref=db.backref('saved_reports', lazy='dynamic'))


# ============================================================
# Fitness & Abonnemente
# ============================================================

class SubscriptionTemplate(db.Model):
    """Abo-Vorlagen (z.B. Fitness Jahresabo, MTT 3 Monate, 10er-Karte)"""
    __tablename__ = 'subscription_templates'
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(50))  # fitness, mtt, prevention, other
    duration_months = db.Column(db.Integer, default=12)
    price = db.Column(db.Float, nullable=False)
    payment_interval = db.Column(db.String(20))  # monthly, quarterly, yearly, once
    cancellation_months = db.Column(db.Integer, default=1)
    auto_renew = db.Column(db.Boolean, default=True)
    max_visits = db.Column(db.Integer, default=0)  # 0 = unbegrenzt
    access_hours_json = db.Column(db.Text)  # JSON: z.B. {"Mo-Fr": "06:00-22:00", "Sa-So": "08:00-18:00"}
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=True)  # null = alle Standorte
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    organization = db.relationship('Organization', backref=db.backref('subscription_templates', lazy='dynamic'))
    location = db.relationship('Location', backref=db.backref('subscription_templates', lazy='dynamic'))


class Subscription(db.Model):
    """Fitness-Abonnemente der Patienten"""
    __tablename__ = 'subscriptions'
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    template_id = db.Column(db.Integer, db.ForeignKey('subscription_templates.id'), nullable=False)
    subscription_number = db.Column(db.String(20))
    badge_number = db.Column(db.String(50))
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date)
    status = db.Column(db.String(20), default='active')  # active, paused, expired, cancelled
    paused_from = db.Column(db.Date)
    paused_until = db.Column(db.Date)
    visits_used = db.Column(db.Integer, default=0)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    organization = db.relationship('Organization', backref=db.backref('subscriptions', lazy='dynamic'))
    patient = db.relationship('Patient', backref=db.backref('subscriptions', lazy='dynamic'))
    template = db.relationship('SubscriptionTemplate', backref=db.backref('subscriptions', lazy='dynamic'))


class FitnessVisit(db.Model):
    """Fitness-Besuche (Check-in/Check-out)"""
    __tablename__ = 'fitness_visits'
    id = db.Column(db.Integer, primary_key=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey('subscriptions.id'), nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=True)
    check_in = db.Column(db.DateTime, nullable=False)
    check_out = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    subscription = db.relationship('Subscription', backref=db.backref('visits', lazy='dynamic'))
    patient = db.relationship('Patient', backref=db.backref('fitness_visits', lazy='dynamic'))
    location = db.relationship('Location', backref=db.backref('fitness_visits', lazy='dynamic'))
