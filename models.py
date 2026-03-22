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
    healing_phase = db.Column(db.String(30), default='initial')  # initial/treatment/consolidation/autonomy
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    appointments = db.relationship('Appointment', backref='series', lazy='dynamic')
    template = db.relationship('TreatmentSeriesTemplate', backref='series')
    prescribing_doctor = db.relationship('Doctor', backref='treatment_series')

    @property
    def num_completed(self):
        """Anzahl abgeschlossener Termine"""
        return self.appointments.filter_by(status='completed').count()

    @property
    def num_total(self):
        """Geplante Anzahl Termine (aus Template oder gezählte)"""
        if self.template:
            return self.template.num_appointments
        return self.appointments.count()

    PHASE_NAMES = {
        'initial': 'Initialphase',
        'treatment': 'Behandlungsphase',
        'consolidation': 'Konsolidierungsphase',
        'autonomy': 'Autonomiephase',
    }


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
    capacity = db.Column(db.Integer, default=1)  # Für Gruppentherapie
    is_active = db.Column(db.Boolean, default=True)


# ============================================================
# Behandlungsplan (Ziele, Messungen, Phasen)
# ============================================================

class TreatmentGoal(db.Model):
    """Behandlungsziel pro Serie"""
    __tablename__ = 'treatment_goals'
    id = db.Column(db.Integer, primary_key=True)
    series_id = db.Column(db.Integer, db.ForeignKey('treatment_series.id'), nullable=False)
    title = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text)
    target_value = db.Column(db.String(100))  # z.B. "90 Grad Flexion"
    current_value = db.Column(db.String(100))
    status = db.Column(db.String(20), default='active')  # active/achieved/abandoned
    phase = db.Column(db.String(30), default='initial')  # initial/treatment/consolidation/autonomy
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    achieved_at = db.Column(db.DateTime)

    series = db.relationship('TreatmentSeries', backref=db.backref('goals', lazy='dynamic'))


class TreatmentMeasurement(db.Model):
    """Messwerte pro Serie/Termin"""
    __tablename__ = 'treatment_measurements'
    id = db.Column(db.Integer, primary_key=True)
    series_id = db.Column(db.Integer, db.ForeignKey('treatment_series.id'), nullable=False)
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointments.id'))
    goal_id = db.Column(db.Integer, db.ForeignKey('treatment_goals.id'))
    measurement_type = db.Column(db.String(50), nullable=False)  # single/pair/multi
    label = db.Column(db.String(200), nullable=False)  # z.B. "Knieflexion rechts"
    value = db.Column(db.String(100))  # Einzelwert
    value_pair_left = db.Column(db.String(100))  # Wertepaar links
    value_pair_right = db.Column(db.String(100))  # Wertepaar rechts
    values_json = db.Column(db.JSON)  # Mehrfachwerte
    unit = db.Column(db.String(30))  # Grad, cm, kg, etc.
    notes = db.Column(db.Text)
    measured_at = db.Column(db.DateTime, default=datetime.utcnow)

    series = db.relationship('TreatmentSeries', backref=db.backref('measurements', lazy='dynamic'))


class WaitlistEntry(db.Model):
    """Warteliste: Patient wartet auf einen Termin"""
    __tablename__ = 'waitlist_entries'
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    series_id = db.Column(db.Integer, db.ForeignKey('treatment_series.id'))
    therapist_id = db.Column(db.Integer, db.ForeignKey('employees.id'))
    duration_minutes = db.Column(db.Integer, default=30)
    preferred_times_json = db.Column(db.JSON, default=dict)  # z.B. {"days": [0,1], "time_from": "08:00", "time_to": "12:00"}
    priority = db.Column(db.Integer, default=5)  # 1=höchste, 10=niedrigste
    notes = db.Column(db.Text)
    status = db.Column(db.String(20), default='waiting')  # waiting/offered/scheduled/cancelled
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    patient = db.relationship('Patient', backref=db.backref('waitlist_entries', lazy='dynamic'))
    therapist = db.relationship('Employee', backref=db.backref('waitlist_entries', lazy='dynamic'))
    series = db.relationship('TreatmentSeries', backref=db.backref('waitlist_entries', lazy='dynamic'))


# ============================================================
# Abrechnung
# ============================================================

class Invoice(db.Model):
    __tablename__ = 'invoices'
    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(50), unique=True)  # z.B. "RE-2026-0001"
    series_id = db.Column(db.Integer, db.ForeignKey('treatment_series.id'))
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    insurance_provider_id = db.Column(db.Integer, db.ForeignKey('insurance_providers.id'))
    therapist_id = db.Column(db.Integer, db.ForeignKey('employees.id'))
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id'))
    amount = db.Column(db.Float, default=0)
    status = db.Column(db.String(20), default='open')  # open/sent/answered/partially_paid/paid/in_collection
    billing_type = db.Column(db.String(20))  # KVG/UVG/MVG/IVG/private/self
    billing_model = db.Column(db.String(20))  # tiers_garant/tiers_payant
    tariff_type = db.Column(db.String(20))  # 311/312/338/325/590/999/flatrate
    due_date = db.Column(db.Date)
    sent_at = db.Column(db.DateTime)
    paid_at = db.Column(db.DateTime)
    dunning_level = db.Column(db.Integer, default=0)  # 0/1/2/3
    last_dunning_date = db.Column(db.Date)
    dunning_fees = db.Column(db.Float, default=0)  # Aufgelaufene Mahngebühren
    qr_reference = db.Column(db.String(30))  # QR-Referenznummer
    notes = db.Column(db.Text)
    tp_copy_sent = db.Column(db.Boolean, default=False)  # Rechnungskopie an Patient bei Tiers Payant
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    items = db.relationship('InvoiceItem', backref='invoice', lazy='dynamic')
    payments = db.relationship('Payment', backref='invoice', lazy='dynamic')
    patient = db.relationship('Patient', backref=db.backref('invoices', lazy='dynamic'))
    insurance_provider = db.relationship('InsuranceProvider', backref=db.backref('invoices', lazy='dynamic'))
    series = db.relationship('TreatmentSeries', backref=db.backref('invoices', lazy='dynamic'))
    therapist = db.relationship('Employee', backref=db.backref('invoices', lazy='dynamic'))
    doctor = db.relationship('Doctor', backref=db.backref('invoices', lazy='dynamic'))

    STATUS_LABELS = {
        'open': 'Offen',
        'sent': 'Gesendet',
        'answered': 'Beantwortet',
        'partially_paid': 'Teilbezahlt',
        'paid': 'Bezahlt',
        'in_collection': 'Im Inkasso',
    }

    BILLING_TYPE_LABELS = {
        'KVG': 'KVG (Grundversicherung)',
        'UVG': 'UVG (Unfall)',
        'MVG': 'MVG (Militär)',
        'IVG': 'IVG (Invalidität)',
        'private': 'Privat (Zusatzversicherung)',
        'self': 'Selbstzahler',
    }

    @property
    def status_label(self):
        return self.STATUS_LABELS.get(self.status, self.status)

    @property
    def billing_type_label(self):
        return self.BILLING_TYPE_LABELS.get(self.billing_type, self.billing_type or '-')

    @property
    def total_paid(self):
        """Summe aller Zahlungen"""
        return sum(p.amount for p in self.payments.all())

    @property
    def outstanding(self):
        """Offener Betrag inkl. Mahngebühren"""
        return (self.amount or 0) + (self.dunning_fees or 0) - self.total_paid

    @property
    def is_overdue(self):
        """Ist die Rechnung überfällig?"""
        if self.status in ('paid', 'in_collection'):
            return False
        if self.due_date and date.today() > self.due_date:
            return True
        return False

    @staticmethod
    def generate_invoice_number():
        """Generiert eine fortlaufende Rechnungsnummer"""
        year = date.today().year
        last = Invoice.query.filter(
            Invoice.invoice_number.like(f'RE-{year}-%')
        ).order_by(Invoice.id.desc()).first()
        if last and last.invoice_number:
            try:
                num = int(last.invoice_number.split('-')[-1]) + 1
            except (ValueError, IndexError):
                num = 1
        else:
            num = 1
        return f'RE-{year}-{num:04d}'


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
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointments.id'))
    position = db.Column(db.Integer, default=0)  # Reihenfolge


class Payment(db.Model):
    __tablename__ = 'payments'
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payment_date = db.Column(db.Date, nullable=False)
    reference = db.Column(db.String(200))
    source = db.Column(db.String(20), default='manual')  # manual/vesr/medidata
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class CostApproval(db.Model):
    __tablename__ = 'cost_approvals'
    id = db.Column(db.Integer, primary_key=True)
    series_id = db.Column(db.Integer, db.ForeignKey('treatment_series.id'))
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    insurance_provider_id = db.Column(db.Integer, db.ForeignKey('insurance_providers.id'))
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctors.id'))
    status = db.Column(db.String(20), default='pending')  # pending/sent/approved/rejected
    approved_sessions = db.Column(db.Integer)  # Anzahl bewilligte Sitzungen
    approved_amount = db.Column(db.Float)  # Bewilligter Betrag
    diagnosis = db.Column(db.Text)
    treatment_type = db.Column(db.String(100))  # z.B. "Physiotherapie"
    valid_until = db.Column(db.Date)
    sent_at = db.Column(db.DateTime)
    answered_at = db.Column(db.DateTime)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    patient = db.relationship('Patient', backref=db.backref('cost_approvals', lazy='dynamic'))
    insurance_provider = db.relationship('InsuranceProvider', backref=db.backref('cost_approvals', lazy='dynamic'))
    doctor = db.relationship('Doctor', backref=db.backref('cost_approvals', lazy='dynamic'))
    series = db.relationship('TreatmentSeries', backref=db.backref('cost_approvals', lazy='dynamic'))

    STATUS_LABELS = {
        'pending': 'Erstellt',
        'sent': 'Gesendet',
        'approved': 'Genehmigt',
        'rejected': 'Abgelehnt',
    }

    @property
    def status_label(self):
        return self.STATUS_LABELS.get(self.status, self.status)


class TaxPointValue(db.Model):
    """Taxpunktwerte pro Kanton/Versicherer/Tarif"""
    __tablename__ = 'tax_point_values'
    id = db.Column(db.Integer, primary_key=True)
    tariff_type = db.Column(db.String(20), nullable=False)  # 311/312/338/325/590/999
    canton = db.Column(db.String(2))  # ZH, BE, etc.
    insurance_provider_id = db.Column(db.Integer, db.ForeignKey('insurance_providers.id'))
    value = db.Column(db.Float, nullable=False)  # Taxpunktwert in CHF
    valid_from = db.Column(db.Date, default=date.today)
    valid_until = db.Column(db.Date)
    notes = db.Column(db.String(200))

    insurance_provider = db.relationship('InsuranceProvider', backref=db.backref('tax_point_values', lazy='dynamic'))

    @staticmethod
    def get_value(tariff_type, canton='ZH', insurance_provider_id=None):
        """Findet den passenden Taxpunktwert"""
        today = date.today()
        query = TaxPointValue.query.filter(
            TaxPointValue.tariff_type == tariff_type,
            TaxPointValue.valid_from <= today,
        ).filter(
            db.or_(TaxPointValue.valid_until.is_(None), TaxPointValue.valid_until >= today)
        )
        # Erst spezifisch für Versicherer suchen
        if insurance_provider_id:
            specific = query.filter(
                TaxPointValue.canton == canton,
                TaxPointValue.insurance_provider_id == insurance_provider_id,
            ).first()
            if specific:
                return specific.value
        # Dann kantonal
        cantonal = query.filter(
            TaxPointValue.canton == canton,
            TaxPointValue.insurance_provider_id.is_(None),
        ).first()
        if cantonal:
            return cantonal.value
        # Fallback: beliebiger Wert für diesen Tarif
        fallback = query.first()
        return fallback.value if fallback else 1.0


class DunningConfig(db.Model):
    """Mahnwesen-Konfiguration pro Stufe"""
    __tablename__ = 'dunning_configs'
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    level = db.Column(db.Integer, nullable=False)  # 1, 2, 3
    days_after_due = db.Column(db.Integer, nullable=False)  # Tage nach Fälligkeit
    fee = db.Column(db.Float, default=0)  # Mahngebühr (nur bei Tiers Garant)
    text_template = db.Column(db.Text)  # Mahntext-Vorlage
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    organization = db.relationship('Organization', backref=db.backref('dunning_configs', lazy='dynamic'))


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
