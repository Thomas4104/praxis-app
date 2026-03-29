"""Reporting-Service: Auswertungen, KPI-Berechnungen und Therapeuten-Scorecards"""
import io
import csv
from datetime import datetime, date, timedelta
from sqlalchemy import func, and_, or_, extract
from models import (
    db, Patient, Appointment, TreatmentSeries, Invoice, InvoiceItem,
    Payment, Employee, Product, User, Location, InsuranceProvider,
    WorkSchedule, DunningRecord
)


# ============================================================
# Report-Definitionen: Kategorien, Filter und Spalten
# ============================================================

REPORT_CATEGORIES = {
    'patients': {
        'label': 'Patienten',
        'filters': [
            {'key': 'date_from', 'label': 'Erstellt ab', 'type': 'date'},
            {'key': 'date_to', 'label': 'Erstellt bis', 'type': 'date'},
            {'key': 'location_id', 'label': 'Standort', 'type': 'select', 'model': 'Location'},
            {'key': 'insurance_type', 'label': 'Versicherungstyp', 'type': 'select',
             'options': [{'value': 'KVG', 'label': 'KVG'}, {'value': 'UVG', 'label': 'UVG'},
                         {'value': 'VVG', 'label': 'VVG (Privat)'}, {'value': 'IVG', 'label': 'IVG'},
                         {'value': 'MVG', 'label': 'MVG'}]},
            {'key': 'is_active', 'label': 'Status', 'type': 'select',
             'options': [{'value': '1', 'label': 'Aktiv'}, {'value': '0', 'label': 'Inaktiv'}]},
            {'key': 'search', 'label': 'Freitext-Suche', 'type': 'text'},
        ],
        'columns': [
            {'key': 'patient_number', 'label': 'Pat.-Nr.'},
            {'key': 'last_name', 'label': 'Nachname'},
            {'key': 'first_name', 'label': 'Vorname'},
            {'key': 'date_of_birth', 'label': 'Geburtsdatum'},
            {'key': 'phone', 'label': 'Telefon'},
            {'key': 'mobile', 'label': 'Mobil'},
            {'key': 'email', 'label': 'E-Mail'},
            {'key': 'insurance_type', 'label': 'Versicherungstyp'},
            {'key': 'insurance_provider', 'label': 'Versicherung'},
            {'key': 'city', 'label': 'Ort'},
            {'key': 'zip_code', 'label': 'PLZ'},
            {'key': 'last_appointment', 'label': 'Letzter Termin'},
            {'key': 'open_invoices', 'label': 'Offene Rechnungen', 'numeric': True},
            {'key': 'created_at', 'label': 'Erstellt am'},
        ]
    },
    'appointments': {
        'label': 'Termine',
        'filters': [
            {'key': 'date_from', 'label': 'Datum von', 'type': 'date'},
            {'key': 'date_to', 'label': 'Datum bis', 'type': 'date'},
            {'key': 'location_id', 'label': 'Standort', 'type': 'select', 'model': 'Location'},
            {'key': 'employee_id', 'label': 'Therapeut', 'type': 'select', 'model': 'Employee'},
            {'key': 'status', 'label': 'Status', 'type': 'select',
             'options': [{'value': 'scheduled', 'label': 'Geplant'}, {'value': 'completed', 'label': 'Abgeschlossen'},
                         {'value': 'cancelled', 'label': 'Abgesagt'}, {'value': 'no_show', 'label': 'Nicht erschienen'}]},
            {'key': 'appointment_type', 'label': 'Typ', 'type': 'select',
             'options': [{'value': 'treatment', 'label': 'Behandlung'}, {'value': 'initial', 'label': 'Ersttermin'},
                         {'value': 'follow_up', 'label': 'Nachkontrolle'}, {'value': 'group', 'label': 'Gruppe'}]},
        ],
        'columns': [
            {'key': 'date', 'label': 'Datum'},
            {'key': 'time', 'label': 'Zeit'},
            {'key': 'patient_name', 'label': 'Patient'},
            {'key': 'employee_name', 'label': 'Therapeut'},
            {'key': 'appointment_type', 'label': 'Typ'},
            {'key': 'status', 'label': 'Status'},
            {'key': 'duration_minutes', 'label': 'Dauer (Min.)', 'numeric': True},
            {'key': 'series_diagnosis', 'label': 'Diagnose'},
            {'key': 'location_name', 'label': 'Standort'},
        ]
    },
    'series': {
        'label': 'Behandlungsserien',
        'filters': [
            {'key': 'date_from', 'label': 'Erstellt ab', 'type': 'date'},
            {'key': 'date_to', 'label': 'Erstellt bis', 'type': 'date'},
            {'key': 'employee_id', 'label': 'Therapeut', 'type': 'select', 'model': 'Employee'},
            {'key': 'status', 'label': 'Status', 'type': 'select',
             'options': [{'value': 'active', 'label': 'Aktiv'}, {'value': 'completed', 'label': 'Abgeschlossen'},
                         {'value': 'cancelled', 'label': 'Abgebrochen'}]},
            {'key': 'insurance_type', 'label': 'Versicherungstyp', 'type': 'select',
             'options': [{'value': 'KVG', 'label': 'KVG'}, {'value': 'UVG', 'label': 'UVG'},
                         {'value': 'VVG', 'label': 'VVG (Privat)'}]},
            {'key': 'diagnosis', 'label': 'Diagnose', 'type': 'text'},
        ],
        'columns': [
            {'key': 'patient_name', 'label': 'Patient'},
            {'key': 'therapist_name', 'label': 'Therapeut'},
            {'key': 'diagnosis', 'label': 'Diagnose'},
            {'key': 'status', 'label': 'Status'},
            {'key': 'insurance_type', 'label': 'Versicherungstyp'},
            {'key': 'billing_model', 'label': 'Abrechnungsmodell'},
            {'key': 'num_appointments', 'label': 'Anz. Termine', 'numeric': True},
            {'key': 'created_at', 'label': 'Erstellt am'},
            {'key': 'completed_at', 'label': 'Abgeschlossen am'},
            {'key': 'avg_interval_days', 'label': 'Ø Terminabstand (Tage)', 'numeric': True},
        ]
    },
    'invoices': {
        'label': 'Rechnungen/Abrechnung',
        'filters': [
            {'key': 'date_from', 'label': 'Erstellt ab', 'type': 'date'},
            {'key': 'date_to', 'label': 'Erstellt bis', 'type': 'date'},
            {'key': 'status', 'label': 'Status', 'type': 'select',
             'options': [{'value': 'draft', 'label': 'Entwurf'}, {'value': 'sent', 'label': 'Gesendet'},
                         {'value': 'paid', 'label': 'Bezahlt'}, {'value': 'overdue', 'label': 'Überfällig'},
                         {'value': 'cancelled', 'label': 'Storniert'}]},
            {'key': 'dunning_level', 'label': 'Mahnstufe', 'type': 'select',
             'options': [{'value': '0', 'label': 'Keine Mahnung'}, {'value': '1', 'label': '1. Mahnung'},
                         {'value': '2', 'label': '2. Mahnung'}, {'value': '3', 'label': '3. Mahnung'}]},
            {'key': 'billing_model', 'label': 'Abrechnungsmodell', 'type': 'select',
             'options': [{'value': 'tiers_garant', 'label': 'Tiers Garant'}, {'value': 'tiers_payant', 'label': 'Tiers Payant'}]},
        ],
        'columns': [
            {'key': 'invoice_number', 'label': 'Rechnungs-Nr.'},
            {'key': 'patient_name', 'label': 'Patient'},
            {'key': 'amount_total', 'label': 'Betrag (CHF)', 'numeric': True},
            {'key': 'amount_paid', 'label': 'Bezahlt (CHF)', 'numeric': True},
            {'key': 'amount_open', 'label': 'Offen (CHF)', 'numeric': True},
            {'key': 'status', 'label': 'Status'},
            {'key': 'billing_model', 'label': 'Abrechnungsmodell'},
            {'key': 'due_date', 'label': 'Fällig am'},
            {'key': 'dunning_level', 'label': 'Mahnstufe', 'numeric': True},
            {'key': 'created_at', 'label': 'Erstellt am'},
        ]
    },
    'employees': {
        'label': 'Mitarbeiter',
        'filters': [
            {'key': 'location_id', 'label': 'Standort', 'type': 'select', 'model': 'Location'},
            {'key': 'is_active', 'label': 'Status', 'type': 'select',
             'options': [{'value': '1', 'label': 'Aktiv'}, {'value': '0', 'label': 'Inaktiv'}]},
        ],
        'columns': [
            {'key': 'employee_number', 'label': 'Personal-Nr.'},
            {'key': 'last_name', 'label': 'Nachname'},
            {'key': 'first_name', 'label': 'Vorname'},
            {'key': 'email', 'label': 'E-Mail'},
            {'key': 'pensum_percent', 'label': 'Pensum (%)', 'numeric': True},
            {'key': 'location_name', 'label': 'Standort'},
            {'key': 'num_patients', 'label': 'Anz. Patienten', 'numeric': True},
            {'key': 'num_appointments', 'label': 'Anz. Termine', 'numeric': True},
        ]
    },
    'products': {
        'label': 'Produkte',
        'filters': [
            {'key': 'category', 'label': 'Kategorie', 'type': 'text'},
            {'key': 'is_active', 'label': 'Status', 'type': 'select',
             'options': [{'value': '1', 'label': 'Aktiv'}, {'value': '0', 'label': 'Inaktiv'}]},
            {'key': 'search', 'label': 'Freitext-Suche', 'type': 'text'},
        ],
        'columns': [
            {'key': 'name', 'label': 'Bezeichnung'},
            {'key': 'category', 'label': 'Kategorie'},
            {'key': 'article_number', 'label': 'Artikelnummer'},
            {'key': 'net_price', 'label': 'Nettopreis (CHF)', 'numeric': True},
            {'key': 'vat_rate', 'label': 'MwSt. (%)', 'numeric': True},
            {'key': 'stock_quantity', 'label': 'Bestand', 'numeric': True},
            {'key': 'supplier', 'label': 'Lieferant'},
        ]
    }
}


def get_report_categories():
    """Gibt alle Report-Kategorien mit Labels zurueck"""
    return {k: v['label'] for k, v in REPORT_CATEGORIES.items()}


def get_category_filters(category):
    """Gibt die Filter fuer eine Kategorie zurueck"""
    cat = REPORT_CATEGORIES.get(category)
    return cat['filters'] if cat else []


def get_category_columns(category):
    """Gibt die verfuegbaren Spalten fuer eine Kategorie zurueck"""
    cat = REPORT_CATEGORIES.get(category)
    return cat['columns'] if cat else []


def _parse_date(val):
    """Hilfsfunktion: String zu date-Objekt"""
    if not val:
        return None
    if isinstance(val, date):
        return val
    try:
        return datetime.strptime(val, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None


# ============================================================
# Report ausfuehren
# ============================================================

def run_report(category, filters, columns, org_id, page=1, per_page=50, sort_by=None, sort_dir='asc'):
    """Fuehrt eine Auswertung aus und gibt Ergebnisse zurueck"""
    if category not in REPORT_CATEGORIES:
        return {'headers': [], 'rows': [], 'totals': {}, 'total_count': 0}

    # Verfuegbare Spalten-Definitionen laden
    all_cols = {c['key']: c for c in REPORT_CATEGORIES[category]['columns']}
    # Nur gewaehlte Spalten
    selected_cols = [all_cols[c] for c in columns if c in all_cols] if columns else list(all_cols.values())

    if category == 'patients':
        return _run_patients_report(filters, selected_cols, org_id, page, per_page, sort_by, sort_dir)
    elif category == 'appointments':
        return _run_appointments_report(filters, selected_cols, org_id, page, per_page, sort_by, sort_dir)
    elif category == 'series':
        return _run_series_report(filters, selected_cols, org_id, page, per_page, sort_by, sort_dir)
    elif category == 'invoices':
        return _run_invoices_report(filters, selected_cols, org_id, page, per_page, sort_by, sort_dir)
    elif category == 'employees':
        return _run_employees_report(filters, selected_cols, org_id, page, per_page, sort_by, sort_dir)
    elif category == 'products':
        return _run_products_report(filters, selected_cols, org_id, page, per_page, sort_by, sort_dir)

    return {'headers': [], 'rows': [], 'totals': {}, 'total_count': 0}


def _run_patients_report(filters, cols, org_id, page, per_page, sort_by, sort_dir):
    query = Patient.query.filter_by(organization_id=org_id)

    date_from = _parse_date(filters.get('date_from'))
    date_to = _parse_date(filters.get('date_to'))
    if date_from:
        query = query.filter(Patient.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        query = query.filter(Patient.created_at <= datetime.combine(date_to, datetime.max.time()))
    if filters.get('insurance_type'):
        query = query.filter(Patient.insurance_type == filters['insurance_type'])
    if filters.get('is_active') is not None and filters.get('is_active') != '':
        query = query.filter(Patient.is_active == (filters['is_active'] in ('1', True, 1)))
    if filters.get('search'):
        s = f"%{filters['search']}%"
        query = query.filter(or_(Patient.first_name.ilike(s), Patient.last_name.ilike(s),
                                  Patient.patient_number.ilike(s), Patient.email.ilike(s)))

    total_count = query.count()

    # Sortierung
    sort_map = {
        'last_name': Patient.last_name, 'first_name': Patient.first_name,
        'date_of_birth': Patient.date_of_birth, 'created_at': Patient.created_at,
        'patient_number': Patient.patient_number, 'insurance_type': Patient.insurance_type,
        'city': Patient.city, 'zip_code': Patient.zip_code,
    }
    if sort_by and sort_by in sort_map:
        col = sort_map[sort_by]
        query = query.order_by(col.desc() if sort_dir == 'desc' else col.asc())
    else:
        query = query.order_by(Patient.last_name.asc())

    patients = query.offset((page - 1) * per_page).limit(per_page).all()

    headers = [c['label'] for c in cols]
    col_keys = [c['key'] for c in cols]
    rows = []
    totals = {}

    for p in patients:
        row = []
        for key in col_keys:
            if key == 'patient_number':
                row.append(p.patient_number or '')
            elif key == 'last_name':
                row.append(p.last_name or '')
            elif key == 'first_name':
                row.append(p.first_name or '')
            elif key == 'date_of_birth':
                row.append(p.date_of_birth.strftime('%d.%m.%Y') if p.date_of_birth else '')
            elif key == 'phone':
                row.append(p.phone or '')
            elif key == 'mobile':
                row.append(p.mobile or '')
            elif key == 'email':
                row.append(p.email or '')
            elif key == 'insurance_type':
                row.append(p.insurance_type or '')
            elif key == 'insurance_provider':
                row.append(p.insurance_provider.name if p.insurance_provider else '')
            elif key == 'city':
                row.append(p.city or '')
            elif key == 'zip_code':
                row.append(p.zip_code or '')
            elif key == 'last_appointment':
                last = Appointment.query.filter_by(patient_id=p.id).order_by(Appointment.start_time.desc()).first()
                row.append(last.start_time.strftime('%d.%m.%Y') if last else '')
            elif key == 'open_invoices':
                amount = db.session.query(func.coalesce(func.sum(Invoice.amount_open), 0)).filter(
                    Invoice.patient_id == p.id, Invoice.status.in_(['sent', 'overdue'])).scalar()
                row.append(round(float(amount), 2))
                totals[key] = totals.get(key, 0) + float(amount)
            elif key == 'created_at':
                row.append(p.created_at.strftime('%d.%m.%Y') if p.created_at else '')
            else:
                row.append('')
        rows.append(row)

    # Totals runden
    for k in totals:
        totals[k] = round(totals[k], 2)

    return {'headers': headers, 'col_keys': col_keys, 'rows': rows, 'totals': totals, 'total_count': total_count}


def _run_appointments_report(filters, cols, org_id, page, per_page, sort_by, sort_dir):
    query = Appointment.query.join(Patient).filter(Patient.organization_id == org_id)

    date_from = _parse_date(filters.get('date_from'))
    date_to = _parse_date(filters.get('date_to'))
    if date_from:
        query = query.filter(Appointment.start_time >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        query = query.filter(Appointment.start_time <= datetime.combine(date_to, datetime.max.time()))
    if filters.get('employee_id'):
        query = query.filter(Appointment.employee_id == int(filters['employee_id']))
    if filters.get('location_id'):
        query = query.filter(Appointment.location_id == int(filters['location_id']))
    if filters.get('status'):
        query = query.filter(Appointment.status == filters['status'])
    if filters.get('appointment_type'):
        query = query.filter(Appointment.appointment_type == filters['appointment_type'])

    total_count = query.count()

    if sort_by == 'date' or not sort_by:
        col = Appointment.start_time
        query = query.order_by(col.desc() if sort_dir == 'desc' else col.asc())
    elif sort_by == 'patient_name':
        query = query.order_by(Patient.last_name.desc() if sort_dir == 'desc' else Patient.last_name.asc())

    appointments = query.offset((page - 1) * per_page).limit(per_page).all()

    headers = [c['label'] for c in cols]
    col_keys = [c['key'] for c in cols]
    rows = []
    totals = {}

    status_labels = {'scheduled': 'Geplant', 'completed': 'Abgeschlossen', 'cancelled': 'Abgesagt', 'no_show': 'Nicht erschienen'}
    type_labels = {'treatment': 'Behandlung', 'initial': 'Ersttermin', 'follow_up': 'Nachkontrolle', 'group': 'Gruppe'}

    for a in appointments:
        row = []
        for key in col_keys:
            if key == 'date':
                row.append(a.start_time.strftime('%d.%m.%Y') if a.start_time else '')
            elif key == 'time':
                row.append(a.start_time.strftime('%H:%M') if a.start_time else '')
            elif key == 'patient_name':
                row.append(f"{a.patient.last_name}, {a.patient.first_name}" if a.patient else '')
            elif key == 'employee_name':
                emp = a.employee
                row.append(f"{emp.user.last_name}, {emp.user.first_name}" if emp and emp.user else '')
            elif key == 'appointment_type':
                row.append(type_labels.get(a.appointment_type, a.appointment_type or ''))
            elif key == 'status':
                row.append(status_labels.get(a.status, a.status or ''))
            elif key == 'duration_minutes':
                val = a.duration_minutes or 0
                row.append(val)
                totals[key] = totals.get(key, 0) + val
            elif key == 'series_diagnosis':
                row.append(a.series.diagnosis_text if a.series else '')
            elif key == 'location_name':
                row.append(a.location.name if a.location else '')
            else:
                row.append('')
        rows.append(row)

    return {'headers': headers, 'col_keys': col_keys, 'rows': rows, 'totals': totals, 'total_count': total_count}


def _run_series_report(filters, cols, org_id, page, per_page, sort_by, sort_dir):
    query = TreatmentSeries.query.join(Patient).filter(Patient.organization_id == org_id)

    date_from = _parse_date(filters.get('date_from'))
    date_to = _parse_date(filters.get('date_to'))
    if date_from:
        query = query.filter(TreatmentSeries.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        query = query.filter(TreatmentSeries.created_at <= datetime.combine(date_to, datetime.max.time()))
    if filters.get('employee_id'):
        query = query.filter(TreatmentSeries.therapist_id == int(filters['employee_id']))
    if filters.get('status'):
        query = query.filter(TreatmentSeries.status == filters['status'])
    if filters.get('insurance_type'):
        query = query.filter(TreatmentSeries.insurance_type == filters['insurance_type'])
    if filters.get('diagnosis'):
        s = f"%{filters['diagnosis']}%"
        query = query.filter(TreatmentSeries.diagnosis_text.ilike(s))

    total_count = query.count()
    query = query.order_by(TreatmentSeries.created_at.desc())
    series_list = query.offset((page - 1) * per_page).limit(per_page).all()

    headers = [c['label'] for c in cols]
    col_keys = [c['key'] for c in cols]
    rows = []
    totals = {}

    status_labels = {'active': 'Aktiv', 'completed': 'Abgeschlossen', 'cancelled': 'Abgebrochen'}

    for s in series_list:
        row = []
        for key in col_keys:
            if key == 'patient_name':
                row.append(f"{s.patient.last_name}, {s.patient.first_name}" if s.patient else '')
            elif key == 'therapist_name':
                emp = s.therapist
                row.append(f"{emp.user.last_name}, {emp.user.first_name}" if emp and emp.user else '')
            elif key == 'diagnosis':
                row.append(s.diagnosis_text or '')
            elif key == 'status':
                row.append(status_labels.get(s.status, s.status or ''))
            elif key == 'insurance_type':
                row.append(s.insurance_type or '')
            elif key == 'billing_model':
                models = {'tiers_garant': 'Tiers Garant', 'tiers_payant': 'Tiers Payant'}
                row.append(models.get(s.billing_model, s.billing_model or ''))
            elif key == 'num_appointments':
                cnt = s.appointments.count()
                row.append(cnt)
                totals[key] = totals.get(key, 0) + cnt
            elif key == 'created_at':
                row.append(s.created_at.strftime('%d.%m.%Y') if s.created_at else '')
            elif key == 'completed_at':
                row.append(s.completed_at.strftime('%d.%m.%Y') if s.completed_at else '')
            elif key == 'avg_interval_days':
                appts = s.appointments.order_by(Appointment.start_time.asc()).all()
                if len(appts) >= 2:
                    intervals = [(appts[i+1].start_time.date() - appts[i].start_time.date()).days
                                 for i in range(len(appts)-1)]
                    avg = round(sum(intervals) / len(intervals), 1)
                else:
                    avg = 0
                row.append(avg)
            else:
                row.append('')
        rows.append(row)

    return {'headers': headers, 'col_keys': col_keys, 'rows': rows, 'totals': totals, 'total_count': total_count}


def _run_invoices_report(filters, cols, org_id, page, per_page, sort_by, sort_dir):
    query = Invoice.query.filter_by(organization_id=org_id)

    date_from = _parse_date(filters.get('date_from'))
    date_to = _parse_date(filters.get('date_to'))
    if date_from:
        query = query.filter(Invoice.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        query = query.filter(Invoice.created_at <= datetime.combine(date_to, datetime.max.time()))
    if filters.get('status'):
        query = query.filter(Invoice.status == filters['status'])
    if filters.get('dunning_level') is not None and filters.get('dunning_level') != '':
        query = query.filter(Invoice.dunning_level == int(filters['dunning_level']))
    if filters.get('billing_model'):
        query = query.filter(Invoice.billing_model == filters['billing_model'])

    total_count = query.count()
    query = query.order_by(Invoice.created_at.desc())
    invoices = query.offset((page - 1) * per_page).limit(per_page).all()

    headers = [c['label'] for c in cols]
    col_keys = [c['key'] for c in cols]
    rows = []
    totals = {}

    status_labels = {'draft': 'Entwurf', 'sent': 'Gesendet', 'paid': 'Bezahlt', 'overdue': 'Überfällig',
                     'cancelled': 'Storniert', 'partial': 'Teilbezahlt'}
    model_labels = {'tiers_garant': 'Tiers Garant', 'tiers_payant': 'Tiers Payant'}

    for inv in invoices:
        row = []
        for key in col_keys:
            if key == 'invoice_number':
                row.append(inv.invoice_number or '')
            elif key == 'patient_name':
                row.append(f"{inv.patient.last_name}, {inv.patient.first_name}" if inv.patient else '')
            elif key == 'amount_total':
                val = round(float(inv.amount_total or 0), 2)
                row.append(val)
                totals[key] = totals.get(key, 0) + val
            elif key == 'amount_paid':
                val = round(float(inv.amount_paid or 0), 2)
                row.append(val)
                totals[key] = totals.get(key, 0) + val
            elif key == 'amount_open':
                val = round(float(inv.amount_open or 0), 2)
                row.append(val)
                totals[key] = totals.get(key, 0) + val
            elif key == 'status':
                row.append(status_labels.get(inv.status, inv.status or ''))
            elif key == 'billing_model':
                row.append(model_labels.get(inv.billing_model, inv.billing_model or ''))
            elif key == 'due_date':
                row.append(inv.due_date.strftime('%d.%m.%Y') if inv.due_date else '')
            elif key == 'dunning_level':
                row.append(inv.dunning_level or 0)
            elif key == 'created_at':
                row.append(inv.created_at.strftime('%d.%m.%Y') if inv.created_at else '')
            else:
                row.append('')
        rows.append(row)

    for k in totals:
        totals[k] = round(totals[k], 2)

    return {'headers': headers, 'col_keys': col_keys, 'rows': rows, 'totals': totals, 'total_count': total_count}


def _run_employees_report(filters, cols, org_id, page, per_page, sort_by, sort_dir):
    query = Employee.query.filter_by(organization_id=org_id)

    if filters.get('location_id'):
        query = query.filter(Employee.default_location_id == int(filters['location_id']))
    if filters.get('is_active') is not None and filters.get('is_active') != '':
        query = query.filter(Employee.is_active == (filters['is_active'] in ('1', True, 1)))

    total_count = query.count()
    employees = query.offset((page - 1) * per_page).limit(per_page).all()

    headers = [c['label'] for c in cols]
    col_keys = [c['key'] for c in cols]
    rows = []
    totals = {}

    for emp in employees:
        row = []
        user = emp.user
        for key in col_keys:
            if key == 'employee_number':
                row.append(emp.employee_number or '')
            elif key == 'last_name':
                row.append(user.last_name if user else '')
            elif key == 'first_name':
                row.append(user.first_name if user else '')
            elif key == 'email':
                row.append(user.email if user else '')
            elif key == 'pensum_percent':
                val = emp.pensum_percent or 0
                row.append(val)
            elif key == 'location_name':
                row.append(emp.default_location.name if emp.default_location else '')
            elif key == 'num_patients':
                cnt = TreatmentSeries.query.filter_by(therapist_id=emp.id, status='active').with_entities(
                    func.count(func.distinct(TreatmentSeries.patient_id))).scalar() or 0
                row.append(cnt)
                totals[key] = totals.get(key, 0) + cnt
            elif key == 'num_appointments':
                cnt = Appointment.query.filter_by(employee_id=emp.id, status='completed').count()
                row.append(cnt)
                totals[key] = totals.get(key, 0) + cnt
            else:
                row.append('')
        rows.append(row)

    return {'headers': headers, 'col_keys': col_keys, 'rows': rows, 'totals': totals, 'total_count': total_count}


def _run_products_report(filters, cols, org_id, page, per_page, sort_by, sort_dir):
    query = Product.query.filter_by(organization_id=org_id)

    if filters.get('category'):
        query = query.filter(Product.category.ilike(f"%{filters['category']}%"))
    if filters.get('is_active') is not None and filters.get('is_active') != '':
        query = query.filter(Product.is_active == (filters['is_active'] in ('1', True, 1)))
    if filters.get('search'):
        s = f"%{filters['search']}%"
        query = query.filter(or_(Product.name.ilike(s), Product.article_number.ilike(s)))

    total_count = query.count()
    products = query.order_by(Product.name.asc()).offset((page - 1) * per_page).limit(per_page).all()

    headers = [c['label'] for c in cols]
    col_keys = [c['key'] for c in cols]
    rows = []
    totals = {}

    for p in products:
        row = []
        for key in col_keys:
            if key == 'name':
                row.append(p.name or '')
            elif key == 'category':
                row.append(p.category or '')
            elif key == 'article_number':
                row.append(p.article_number or '')
            elif key == 'net_price':
                val = round(float(p.net_price or 0), 2)
                row.append(val)
            elif key == 'vat_rate':
                row.append(p.vat_rate or 0)
            elif key == 'stock_quantity':
                val = p.stock_quantity or 0
                row.append(val)
                totals[key] = totals.get(key, 0) + val
            elif key == 'supplier':
                row.append(p.supplier or '')
            else:
                row.append('')
        rows.append(row)

    return {'headers': headers, 'col_keys': col_keys, 'rows': rows, 'totals': totals, 'total_count': total_count}


# ============================================================
# KPI-Berechnung
# ============================================================

def calculate_kpis(date_from, date_to, org_id, location_id=None, employee_id=None):
    """Berechnet alle KPIs fuer einen Zeitraum"""
    d_from = _parse_date(date_from) if isinstance(date_from, str) else date_from
    d_to = _parse_date(date_to) if isinstance(date_to, str) else date_to

    if not d_from or not d_to:
        d_to = date.today()
        d_from = d_to.replace(day=1)

    dt_from = datetime.combine(d_from, datetime.min.time())
    dt_to = datetime.combine(d_to, datetime.max.time())

    kpis = {}

    # --- Umsatz ---
    inv_query = Invoice.query.filter(
        Invoice.organization_id == org_id,
        Invoice.status == 'paid',
        Invoice.paid_at >= dt_from,
        Invoice.paid_at <= dt_to
    )
    kpis['umsatz'] = round(float(inv_query.with_entities(
        func.coalesce(func.sum(Invoice.amount_total), 0)).scalar()), 2)

    # --- Offene Posten ---
    open_query = Invoice.query.filter(
        Invoice.organization_id == org_id,
        Invoice.status.in_(['sent', 'overdue', 'partial'])
    )
    kpis['offene_posten'] = round(float(open_query.with_entities(
        func.coalesce(func.sum(Invoice.amount_open), 0)).scalar()), 2)

    # --- Neupatienten ---
    pat_query = Patient.query.filter(
        Patient.organization_id == org_id,
        Patient.created_at >= dt_from,
        Patient.created_at <= dt_to
    )
    kpis['neupatienten'] = pat_query.count()

    # --- Behandlungen (abgeschlossene Termine) ---
    appt_base = Appointment.query.join(Patient).filter(
        Patient.organization_id == org_id,
        Appointment.start_time >= dt_from,
        Appointment.start_time <= dt_to
    )
    if employee_id:
        appt_base = appt_base.filter(Appointment.employee_id == employee_id)

    kpis['behandlungen'] = appt_base.filter(Appointment.status == 'completed').count()

    # --- Gesamttermine ---
    total_appts = appt_base.count()
    kpis['gesamttermine'] = total_appts

    # --- No-Show-Rate ---
    no_shows = appt_base.filter(Appointment.status == 'no_show').count()
    kpis['no_shows'] = no_shows
    kpis['no_show_rate'] = round((no_shows / total_appts * 100) if total_appts > 0 else 0, 1)

    # --- Absagequote ---
    cancellations = appt_base.filter(Appointment.status == 'cancelled').count()
    kpis['absagen'] = cancellations
    kpis['absagequote'] = round((cancellations / total_appts * 100) if total_appts > 0 else 0, 1)

    # --- Auslastung ---
    completed_minutes = db.session.query(func.coalesce(func.sum(Appointment.duration_minutes), 0)).join(Patient).filter(
        Patient.organization_id == org_id,
        Appointment.start_time >= dt_from,
        Appointment.start_time <= dt_to,
        Appointment.status == 'completed'
    )
    if employee_id:
        completed_minutes = completed_minutes.filter(Appointment.employee_id == employee_id)
    completed_minutes = float(completed_minutes.scalar())

    # Arbeitsminuten aus WorkSchedule berechnen
    num_days = (d_to - d_from).days + 1
    if employee_id:
        emp = Employee.query.get(employee_id)
        work_minutes = _calc_work_minutes(emp, d_from, d_to) if emp else 0
    else:
        employees = Employee.query.filter_by(organization_id=org_id, is_active=True).all()
        work_minutes = sum(_calc_work_minutes(e, d_from, d_to) for e in employees)

    kpis['behandlungsminuten'] = int(completed_minutes)
    kpis['arbeitsminuten'] = work_minutes
    kpis['auslastung'] = round((completed_minutes / work_minutes * 100) if work_minutes > 0 else 0, 1)

    # --- Durchschnittliche Seriendauer ---
    completed_series = TreatmentSeries.query.join(Patient).filter(
        Patient.organization_id == org_id,
        TreatmentSeries.status == 'completed',
        TreatmentSeries.completed_at >= dt_from,
        TreatmentSeries.completed_at <= dt_to
    ).all()
    if completed_series:
        durations = [(s.completed_at.date() - s.created_at.date()).days for s in completed_series if s.completed_at]
        kpis['avg_seriendauer'] = round(sum(durations) / len(durations), 1) if durations else 0
    else:
        kpis['avg_seriendauer'] = 0

    # --- Umsatz pro Therapeut ---
    active_therapists = Employee.query.filter_by(organization_id=org_id, is_active=True).count()
    kpis['umsatz_pro_therapeut'] = round(kpis['umsatz'] / active_therapists, 2) if active_therapists > 0 else 0

    # --- Patienten pro Therapeut ---
    active_patients = Patient.query.filter_by(organization_id=org_id, is_active=True).count()
    kpis['patienten_pro_therapeut'] = round(active_patients / active_therapists, 1) if active_therapists > 0 else 0

    # --- Mahnquote ---
    total_umsatz_all = float(Invoice.query.filter(
        Invoice.organization_id == org_id,
        Invoice.created_at >= dt_from,
        Invoice.created_at <= dt_to
    ).with_entities(func.coalesce(func.sum(Invoice.amount_total), 0)).scalar())

    dunned_amount = float(Invoice.query.filter(
        Invoice.organization_id == org_id,
        Invoice.dunning_level > 0,
        Invoice.created_at >= dt_from,
        Invoice.created_at <= dt_to
    ).with_entities(func.coalesce(func.sum(Invoice.amount_total), 0)).scalar())

    kpis['mahnquote'] = round((dunned_amount / total_umsatz_all * 100) if total_umsatz_all > 0 else 0, 1)

    # --- Durchschnittliche Zahlungsfrist ---
    paid_invoices = Invoice.query.filter(
        Invoice.organization_id == org_id,
        Invoice.status == 'paid',
        Invoice.paid_at >= dt_from,
        Invoice.paid_at <= dt_to,
        Invoice.paid_at.isnot(None),
        Invoice.created_at.isnot(None)
    ).all()
    if paid_invoices:
        payment_days = [(inv.paid_at.date() - inv.created_at.date()).days for inv in paid_invoices
                        if inv.paid_at and inv.created_at]
        kpis['avg_zahlungsfrist'] = round(sum(payment_days) / len(payment_days), 1) if payment_days else 0
    else:
        kpis['avg_zahlungsfrist'] = 0

    return kpis


def _calc_work_minutes(employee, d_from, d_to):
    """Berechnet Arbeitsminuten eines Mitarbeiters in einem Zeitraum"""
    schedules = WorkSchedule.query.filter_by(employee_id=employee.id).all()
    if not schedules:
        # Fallback: 8h * Pensum
        pensum = (employee.pensum_percent or 100) / 100
        num_workdays = sum(1 for i in range((d_to - d_from).days + 1)
                          if (d_from + timedelta(days=i)).weekday() < 5)
        return int(num_workdays * 480 * pensum)  # 480 = 8h * 60

    total = 0
    current = d_from
    while current <= d_to:
        dow = current.weekday()  # 0=Montag
        for ws in schedules:
            if ws.day_of_week == dow:
                if ws.valid_from and current < ws.valid_from:
                    continue
                if ws.valid_to and current > ws.valid_to:
                    continue
                start = ws.start_time
                end = ws.end_time
                minutes = (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)
                total += max(0, minutes)
        current += timedelta(days=1)
    return total


# ============================================================
# KPI-Vergleich Vorjahr
# ============================================================

def calculate_kpi_comparison(date_from, date_to, org_id):
    """Berechnet KPIs fuer aktuellen Zeitraum und Vorjahr"""
    d_from = _parse_date(date_from) if isinstance(date_from, str) else date_from
    d_to = _parse_date(date_to) if isinstance(date_to, str) else date_to

    current = calculate_kpis(d_from, d_to, org_id)

    # Vorjahr berechnen
    prev_from = d_from.replace(year=d_from.year - 1)
    try:
        prev_to = d_to.replace(year=d_to.year - 1)
    except ValueError:
        prev_to = d_to.replace(year=d_to.year - 1, day=28)
    previous = calculate_kpis(prev_from, prev_to, org_id)

    comparison = {}
    for key in current:
        curr_val = current[key]
        prev_val = previous.get(key, 0)
        if isinstance(curr_val, (int, float)) and isinstance(prev_val, (int, float)):
            if prev_val != 0:
                change_pct = round((curr_val - prev_val) / prev_val * 100, 1)
            elif curr_val > 0:
                change_pct = 100.0
            else:
                change_pct = 0.0
            trend = 'up' if change_pct > 0 else ('down' if change_pct < 0 else 'neutral')
            comparison[key] = {
                'current': curr_val,
                'previous': prev_val,
                'change_pct': change_pct,
                'trend': trend
            }
        else:
            comparison[key] = {'current': curr_val, 'previous': prev_val, 'change_pct': 0, 'trend': 'neutral'}

    return comparison


# ============================================================
# Chart-Daten
# ============================================================

def get_revenue_chart_data(org_id, months=12):
    """Umsatzverlauf der letzten N Monate"""
    today = date.today()
    data = []
    for i in range(months - 1, -1, -1):
        m_date = today.replace(day=1) - timedelta(days=i * 30)
        m_from = m_date.replace(day=1)
        if m_from.month == 12:
            m_to = m_from.replace(year=m_from.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            m_to = m_from.replace(month=m_from.month + 1, day=1) - timedelta(days=1)

        amount = float(Invoice.query.filter(
            Invoice.organization_id == org_id,
            Invoice.status == 'paid',
            Invoice.paid_at >= datetime.combine(m_from, datetime.min.time()),
            Invoice.paid_at <= datetime.combine(m_to, datetime.max.time())
        ).with_entities(func.coalesce(func.sum(Invoice.amount_total), 0)).scalar())

        monat_namen = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']
        data.append({
            'label': f"{monat_namen[m_from.month - 1]} {m_from.year}",
            'value': round(amount, 2)
        })
    return data


def get_revenue_by_therapist(org_id, date_from, date_to):
    """Umsatz pro Therapeut"""
    d_from = _parse_date(date_from) if isinstance(date_from, str) else date_from
    d_to = _parse_date(date_to) if isinstance(date_to, str) else date_to
    dt_from = datetime.combine(d_from, datetime.min.time())
    dt_to = datetime.combine(d_to, datetime.max.time())

    employees = Employee.query.filter_by(organization_id=org_id, is_active=True).all()
    data = []
    for emp in employees:
        if not emp.user:
            continue
        amount = float(Invoice.query.join(TreatmentSeries).filter(
            Invoice.organization_id == org_id,
            Invoice.status == 'paid',
            Invoice.paid_at >= dt_from,
            Invoice.paid_at <= dt_to,
            TreatmentSeries.therapist_id == emp.id
        ).with_entities(func.coalesce(func.sum(Invoice.amount_total), 0)).scalar())
        data.append({
            'label': f"{emp.user.first_name} {emp.user.last_name}",
            'value': round(amount, 2)
        })
    return data


def get_revenue_by_insurance_type(org_id, date_from, date_to):
    """Umsatz nach Versicherungstyp"""
    d_from = _parse_date(date_from) if isinstance(date_from, str) else date_from
    d_to = _parse_date(date_to) if isinstance(date_to, str) else date_to
    dt_from = datetime.combine(d_from, datetime.min.time())
    dt_to = datetime.combine(d_to, datetime.max.time())

    types = ['KVG', 'UVG', 'VVG', 'IVG', 'MVG']
    data = []
    for t in types:
        amount = float(Invoice.query.join(TreatmentSeries).filter(
            Invoice.organization_id == org_id,
            Invoice.status == 'paid',
            Invoice.paid_at >= dt_from,
            Invoice.paid_at <= dt_to,
            TreatmentSeries.insurance_type == t
        ).with_entities(func.coalesce(func.sum(Invoice.amount_total), 0)).scalar())
        if amount > 0:
            data.append({'label': t, 'value': round(amount, 2)})
    return data


def get_utilization_by_therapist(org_id, date_from, date_to):
    """Auslastung pro Therapeut"""
    d_from = _parse_date(date_from) if isinstance(date_from, str) else date_from
    d_to = _parse_date(date_to) if isinstance(date_to, str) else date_to
    dt_from = datetime.combine(d_from, datetime.min.time())
    dt_to = datetime.combine(d_to, datetime.max.time())

    employees = Employee.query.filter_by(organization_id=org_id, is_active=True).all()
    data = []
    for emp in employees:
        if not emp.user:
            continue
        minutes = float(db.session.query(func.coalesce(func.sum(Appointment.duration_minutes), 0)).filter(
            Appointment.employee_id == emp.id,
            Appointment.status == 'completed',
            Appointment.start_time >= dt_from,
            Appointment.start_time <= dt_to
        ).scalar())
        work = _calc_work_minutes(emp, d_from, d_to)
        util = round((minutes / work * 100) if work > 0 else 0, 1)
        data.append({
            'label': f"{emp.user.first_name} {emp.user.last_name}",
            'value': util
        })
    return data


def get_new_patients_chart_data(org_id, months=12):
    """Neupatienten pro Monat"""
    today = date.today()
    data = []
    monat_namen = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']
    for i in range(months - 1, -1, -1):
        m_date = today.replace(day=1) - timedelta(days=i * 30)
        m_from = m_date.replace(day=1)
        if m_from.month == 12:
            m_to = m_from.replace(year=m_from.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            m_to = m_from.replace(month=m_from.month + 1, day=1) - timedelta(days=1)

        count = Patient.query.filter(
            Patient.organization_id == org_id,
            Patient.created_at >= datetime.combine(m_from, datetime.min.time()),
            Patient.created_at <= datetime.combine(m_to, datetime.max.time())
        ).count()
        data.append({
            'label': f"{monat_namen[m_from.month - 1]} {m_from.year}",
            'value': count
        })
    return data


# ============================================================
# Therapeuten-Scorecard
# ============================================================

def calculate_therapist_scorecard(employee_id, date_from, date_to, org_id):
    """Berechnet Scorecard fuer einen Therapeuten"""
    d_from = _parse_date(date_from) if isinstance(date_from, str) else date_from
    d_to = _parse_date(date_to) if isinstance(date_to, str) else date_to
    dt_from = datetime.combine(d_from, datetime.min.time())
    dt_to = datetime.combine(d_to, datetime.max.time())

    emp = Employee.query.get(employee_id)
    if not emp:
        return None

    num_days = (d_to - d_from).days + 1
    num_workdays = sum(1 for i in range(num_days) if (d_from + timedelta(days=i)).weekday() < 5)

    # Behandlungen
    completed = Appointment.query.filter(
        Appointment.employee_id == employee_id,
        Appointment.status == 'completed',
        Appointment.start_time >= dt_from,
        Appointment.start_time <= dt_to
    ).count()

    treatments_per_day = round(completed / num_workdays, 1) if num_workdays > 0 else 0

    # Produktive Stunden
    completed_minutes = float(db.session.query(func.coalesce(func.sum(Appointment.duration_minutes), 0)).filter(
        Appointment.employee_id == employee_id,
        Appointment.status == 'completed',
        Appointment.start_time >= dt_from,
        Appointment.start_time <= dt_to
    ).scalar())
    work_minutes = _calc_work_minutes(emp, d_from, d_to)
    productive_pct = round((completed_minutes / work_minutes * 100) if work_minutes > 0 else 0, 1)

    # Umsatz pro Stunde
    revenue = float(Invoice.query.join(TreatmentSeries).filter(
        Invoice.organization_id == org_id,
        Invoice.status == 'paid',
        Invoice.paid_at >= dt_from,
        Invoice.paid_at <= dt_to,
        TreatmentSeries.therapist_id == employee_id
    ).with_entities(func.coalesce(func.sum(Invoice.amount_total), 0)).scalar())
    productive_hours = completed_minutes / 60
    revenue_per_hour = round(revenue / productive_hours, 2) if productive_hours > 0 else 0

    # No-Show-Rate
    total_appts = Appointment.query.filter(
        Appointment.employee_id == employee_id,
        Appointment.start_time >= dt_from,
        Appointment.start_time <= dt_to
    ).count()
    no_shows = Appointment.query.filter(
        Appointment.employee_id == employee_id,
        Appointment.status == 'no_show',
        Appointment.start_time >= dt_from,
        Appointment.start_time <= dt_to
    ).count()
    no_show_rate = round((no_shows / total_appts * 100) if total_appts > 0 else 0, 1)

    # Serienabschlussrate
    total_series = TreatmentSeries.query.filter(
        TreatmentSeries.therapist_id == employee_id,
        TreatmentSeries.created_at >= dt_from,
        TreatmentSeries.created_at <= dt_to
    ).count()
    completed_series = TreatmentSeries.query.filter(
        TreatmentSeries.therapist_id == employee_id,
        TreatmentSeries.status == 'completed',
        TreatmentSeries.completed_at >= dt_from,
        TreatmentSeries.completed_at <= dt_to
    ).count()
    completion_rate = round((completed_series / total_series * 100) if total_series > 0 else 0, 1)

    # Team-Durchschnitt berechnen
    team_kpis = calculate_kpis(d_from, d_to, org_id)
    active_therapists = Employee.query.filter_by(organization_id=org_id, is_active=True).count()

    team_avg = {
        'treatments_per_day': round(team_kpis['behandlungen'] / (num_workdays * max(active_therapists, 1)), 1),
        'productive_pct': team_kpis['auslastung'],
        'revenue_per_hour': round(team_kpis['umsatz'] / max(active_therapists, 1) / max(productive_hours, 1), 2) if productive_hours > 0 else 0,
        'no_show_rate': team_kpis['no_show_rate'],
    }

    # Trend (letzte 3 Monate)
    trend = []
    for i in range(2, -1, -1):
        m_to = d_to - timedelta(days=i * 30)
        m_from = m_to - timedelta(days=29)
        m_kpis = calculate_kpis(m_from, m_to, org_id, employee_id=employee_id)
        monat_namen = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']
        trend.append({
            'label': f"{monat_namen[m_to.month - 1]} {m_to.year}",
            'behandlungen': m_kpis['behandlungen'],
            'auslastung': m_kpis['auslastung'],
            'no_show_rate': m_kpis['no_show_rate']
        })

    return {
        'employee_name': f"{emp.user.first_name} {emp.user.last_name}" if emp.user else '',
        'treatments_per_day': treatments_per_day,
        'productive_pct': productive_pct,
        'revenue_per_hour': revenue_per_hour,
        'no_show_rate': no_show_rate,
        'completion_rate': completion_rate,
        'total_revenue': round(revenue, 2),
        'total_treatments': completed,
        'team_avg': team_avg,
        'trend': trend
    }


# ============================================================
# CSV-Export
# ============================================================

def export_to_csv(headers, rows):
    """Exportiert Auswertung als CSV"""
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';', quoting=csv.QUOTE_ALL)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    return output.getvalue()


# ============================================================
# Erweiterte KPI-Funktionen (Finanz, Termine, Monatsvergleich)
# ============================================================

def get_financial_kpis(org_id, period_start, period_end):
    """Finanz-KPIs: Umsatz, offene Forderungen, TP-Volumen"""
    # Umsatz (bezahlte Rechnungen im Zeitraum)
    revenue = db.session.query(func.sum(Payment.amount)).join(Invoice).filter(
        Invoice.organization_id == org_id,
        Payment.payment_date >= period_start,
        Payment.payment_date <= period_end,
    ).scalar() or 0

    # Offene Forderungen
    open_amount = db.session.query(func.sum(Invoice.amount_open)).filter(
        Invoice.organization_id == org_id,
        Invoice.status.in_(['sent', 'overdue']),
    ).scalar() or 0

    # Rechnungsvolumen im Zeitraum
    invoice_volume = db.session.query(func.sum(Invoice.amount_total)).filter(
        Invoice.organization_id == org_id,
        Invoice.created_at >= period_start,
        Invoice.created_at <= period_end,
    ).scalar() or 0

    # Anzahl Rechnungen
    invoice_count = Invoice.query.filter(
        Invoice.organization_id == org_id,
        Invoice.created_at >= period_start,
        Invoice.created_at <= period_end,
    ).count()

    return {
        'revenue': float(revenue),
        'open_amount': float(open_amount),
        'invoice_volume': float(invoice_volume),
        'invoice_count': invoice_count,
    }


def get_appointment_kpis(org_id, period_start, period_end):
    """Termin-KPIs: Auslastung, No-Show-Rate, Absagequote"""
    total = Appointment.query.join(Employee).filter(
        Employee.organization_id == org_id,
        Appointment.start_time >= period_start,
        Appointment.start_time <= period_end,
    ).count()

    completed = Appointment.query.join(Employee).filter(
        Employee.organization_id == org_id,
        Appointment.start_time >= period_start,
        Appointment.start_time <= period_end,
        Appointment.status.in_(['completed', 'appeared']),
    ).count()

    no_shows = Appointment.query.join(Employee).filter(
        Employee.organization_id == org_id,
        Appointment.start_time >= period_start,
        Appointment.start_time <= period_end,
        Appointment.status == 'no_show',
    ).count()

    cancelled = Appointment.query.join(Employee).filter(
        Employee.organization_id == org_id,
        Appointment.start_time >= period_start,
        Appointment.start_time <= period_end,
        Appointment.status == 'cancelled',
    ).count()

    return {
        'total': total,
        'completed': completed,
        'no_shows': no_shows,
        'cancelled': cancelled,
        'no_show_rate': round(no_shows / total * 100, 1) if total > 0 else 0,
        'cancel_rate': round(cancelled / total * 100, 1) if total > 0 else 0,
        'completion_rate': round(completed / total * 100, 1) if total > 0 else 0,
    }


def get_chart_data_monthly(org_id, year, category='revenue'):
    """Monatliche Daten fuer Diagramme (aktuelles Jahr + Vorjahr)"""
    data_current = []
    data_previous = []
    labels = ['Jan', 'Feb', 'Mar', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']

    for month in range(1, 13):
        start_current = date(year, month, 1)
        if month == 12:
            end_current = date(year + 1, 1, 1)
        else:
            end_current = date(year, month + 1, 1)

        start_previous = date(year - 1, month, 1)
        if month == 12:
            end_previous = date(year, 1, 1)
        else:
            end_previous = date(year - 1, month + 1, 1)

        if category == 'revenue':
            val_current = db.session.query(func.sum(Payment.amount)).join(Invoice).filter(
                Invoice.organization_id == org_id,
                Payment.payment_date >= start_current,
                Payment.payment_date < end_current,
            ).scalar() or 0
            val_previous = db.session.query(func.sum(Payment.amount)).join(Invoice).filter(
                Invoice.organization_id == org_id,
                Payment.payment_date >= start_previous,
                Payment.payment_date < end_previous,
            ).scalar() or 0
        elif category == 'appointments':
            val_current = Appointment.query.join(Employee).filter(
                Employee.organization_id == org_id,
                Appointment.start_time >= start_current,
                Appointment.start_time < end_current,
                Appointment.status.in_(['completed', 'appeared']),
            ).count()
            val_previous = Appointment.query.join(Employee).filter(
                Employee.organization_id == org_id,
                Appointment.start_time >= start_previous,
                Appointment.start_time < end_previous,
                Appointment.status.in_(['completed', 'appeared']),
            ).count()
        elif category == 'invoices':
            val_current = db.session.query(func.sum(Invoice.amount_total)).filter(
                Invoice.organization_id == org_id,
                Invoice.created_at >= start_current,
                Invoice.created_at < end_current,
            ).scalar() or 0
            val_previous = db.session.query(func.sum(Invoice.amount_total)).filter(
                Invoice.organization_id == org_id,
                Invoice.created_at >= start_previous,
                Invoice.created_at < end_previous,
            ).scalar() or 0
        else:
            val_current = 0
            val_previous = 0

        data_current.append(float(val_current))
        data_previous.append(float(val_previous))

    return {
        'labels': labels,
        'current_year': data_current,
        'previous_year': data_previous,
        'year': year,
    }


# ============================================================
# Cenplex KPI-System
# ============================================================

def get_kpi_data(org_id, kpi_type, date_from, date_to, location_id=None, employee_id=None):
    """
    Berechnet KPI-Daten nach Cenplex-Vorbild.

    kpi_type: 'appointments', 'billing', 'fitness', 'utilization', 'patients'
    """
    if kpi_type == 'appointments':
        return _kpi_appointments(org_id, date_from, date_to, location_id, employee_id)
    elif kpi_type == 'billing':
        return _kpi_billing(org_id, date_from, date_to, location_id, employee_id)
    elif kpi_type == 'utilization':
        return _kpi_utilization(org_id, date_from, date_to, location_id, employee_id)
    elif kpi_type == 'patients':
        return _kpi_patients(org_id, date_from, date_to, location_id)
    elif kpi_type == 'fitness':
        return _kpi_fitness(org_id, date_from, date_to, location_id)
    return {}


def _kpi_appointments(org_id, date_from, date_to, location_id=None, employee_id=None):
    """Termin-KPIs (Cenplex: KpiappointmentDto)"""
    query = Appointment.query.join(
        TreatmentSeries, Appointment.series_id == TreatmentSeries.id, isouter=True
    ).filter(
        Appointment.start_time >= date_from,
        Appointment.start_time <= date_to
    )

    # Filter
    if location_id:
        query = query.filter(Appointment.location_id == location_id)
    if employee_id:
        query = query.filter(Appointment.employee_id == employee_id)

    all_appts = query.all()

    total = len(all_appts)
    completed = sum(1 for a in all_appts if a.status == 'completed')
    cancelled = sum(1 for a in all_appts if a.status == 'cancelled')
    no_show = sum(1 for a in all_appts if a.status == 'no_show')
    online_booked = sum(1 for a in all_appts if a.was_booked_online)

    # Durchschnittliche Dauer
    durations = [a.duration_minutes for a in all_appts if a.duration_minutes]
    avg_duration = sum(durations) / len(durations) if durations else 0

    # Ersttermine vs. Folgetermine
    first_appts = sum(1 for a in all_appts if a.series_number == 1 or a.appointment_type == 'initial')

    cancel_rate = (cancelled / total * 100) if total > 0 else 0
    no_show_rate = (no_show / total * 100) if total > 0 else 0

    return {
        'total': total,
        'completed': completed,
        'cancelled': cancelled,
        'no_show': no_show,
        'cancel_rate': round(cancel_rate, 1),
        'no_show_rate': round(no_show_rate, 1),
        'online_booked': online_booked,
        'avg_duration': round(avg_duration, 1),
        'first_appointments': first_appts,
        'follow_up': total - first_appts
    }


def _kpi_billing(org_id, date_from, date_to, location_id=None, employee_id=None):
    """Abrechnungs-KPIs (Cenplex: KpisaleDto)"""
    query = Invoice.query.filter(
        Invoice.organization_id == org_id,
        Invoice.created_at >= date_from,
        Invoice.created_at <= date_to,
        Invoice.is_deleted != True
    )

    if employee_id:
        query = query.filter(Invoice.employee_id == employee_id)

    invoices = query.all()

    total_invoiced = sum(float(i.amount_total or 0) for i in invoices)
    total_paid = sum(float(i.amount_paid or 0) for i in invoices)
    total_open = sum(float(i.amount_open or 0) for i in invoices if i.status in ('sent', 'reminded'))
    total_overdue = sum(float(i.amount_open or 0) for i in invoices
                       if i.due_date and i.due_date < date.today() and i.status in ('sent', 'reminded'))

    # Nach Typ gruppieren
    by_type = {}
    for inv in invoices:
        type_key = inv.invoice_type or 0
        if type_key not in by_type:
            by_type[type_key] = {'count': 0, 'amount': 0}
        by_type[type_key]['count'] += 1
        by_type[type_key]['amount'] += float(inv.amount_total or 0)

    # Nach BillingCase gruppieren
    by_case = {}
    for inv in invoices:
        case_key = inv.billing_case or 0
        if case_key not in by_case:
            by_case[case_key] = {'count': 0, 'amount': 0}
        by_case[case_key]['count'] += 1
        by_case[case_key]['amount'] += float(inv.amount_total or 0)

    return {
        'total_invoiced': round(total_invoiced, 2),
        'total_paid': round(total_paid, 2),
        'total_open': round(total_open, 2),
        'total_overdue': round(total_overdue, 2),
        'invoice_count': len(invoices),
        'avg_invoice': round(total_invoiced / len(invoices), 2) if invoices else 0,
        'payment_ratio': round(total_paid / total_invoiced * 100, 1) if total_invoiced > 0 else 0,
        'by_type': by_type,
        'by_case': by_case
    }


def _kpi_utilization(org_id, date_from, date_to, location_id=None, employee_id=None):
    """Auslastungs-KPIs (Cenplex: KpicontrollingDto) - optimiert"""
    from models import Appointment, Employee, WorkSchedule

    employees_query = Employee.query.filter_by(organization_id=org_id, is_active=True)
    if employee_id:
        employees_query = employees_query.filter_by(id=employee_id)
    employees = employees_query.all()

    if not employees:
        return {'employees': [], 'avg_utilization': 0, 'total_planned_hours': 0, 'total_actual_hours': 0}

    emp_ids = [e.id for e in employees]

    # Alle WorkSchedules und Appointments auf einmal laden
    all_schedules = WorkSchedule.query.filter(
        WorkSchedule.employee_id.in_(emp_ids)
    ).all()
    schedules_by_emp = {}
    for s in all_schedules:
        schedules_by_emp.setdefault(s.employee_id, []).append(s)

    all_appts = Appointment.query.filter(
        Appointment.employee_id.in_(emp_ids),
        Appointment.start_time >= date_from,
        Appointment.start_time <= date_to,
        Appointment.status.in_(['completed', 'scheduled'])
    ).all()
    appts_by_emp = {}
    for a in all_appts:
        appts_by_emp.setdefault(a.employee_id, []).append(a)

    days = (date_to - date_from).days if hasattr(date_to, 'days') else (date_to - date_from).days
    weeks = max(1, days / 7)

    utilization = []
    for emp in employees:
        schedules = schedules_by_emp.get(emp.id, [])
        planned_minutes_per_week = sum(
            max(0, (datetime.combine(date.today(), s.end_time) - datetime.combine(date.today(), s.start_time)).total_seconds() / 60)
            for s in schedules if s.work_type in ('treatment', 'regular')
        )
        total_planned = planned_minutes_per_week * weeks

        appts = appts_by_emp.get(emp.id, [])
        total_actual = sum(a.duration_minutes or 30 for a in appts)

        rate = (total_actual / total_planned * 100) if total_planned > 0 else 0

        utilization.append({
            'employee_id': emp.id,
            'employee_name': f"{emp.user.first_name} {emp.user.last_name}" if emp.user else f"MA {emp.id}",
            'planned_hours': round(total_planned / 60, 1),
            'actual_hours': round(total_actual / 60, 1),
            'utilization_rate': round(rate, 1),
            'appointment_count': len(appts)
        })

    avg_rate = sum(u['utilization_rate'] for u in utilization) / len(utilization) if utilization else 0

    return {
        'employees': utilization,
        'avg_utilization': round(avg_rate, 1),
        'total_planned_hours': round(sum(u['planned_hours'] for u in utilization), 1),
        'total_actual_hours': round(sum(u['actual_hours'] for u in utilization), 1)
    }


def _kpi_patients(org_id, date_from, date_to, location_id=None):
    """Patienten-KPIs"""
    new_patients = Patient.query.filter(
        Patient.organization_id == org_id,
        Patient.created_at >= date_from,
        Patient.created_at <= date_to
    ).count()

    active_patients = Patient.query.filter_by(
        organization_id=org_id, is_active=True
    ).count()

    blacklisted = Patient.query.filter_by(
        organization_id=org_id, blacklisted=True
    ).count()

    # Aktive Serien
    active_series = TreatmentSeries.query.filter(
        TreatmentSeries.organization_id == org_id,
        TreatmentSeries.status == 'active'
    ).count()

    return {
        'new_patients': new_patients,
        'active_patients': active_patients,
        'blacklisted': blacklisted,
        'active_series': active_series
    }


def _kpi_fitness(org_id, date_from, date_to, location_id=None):
    """Fitness-KPIs (Cenplex: KpifitnessDto)"""
    from models import Subscription, FitnessVisit

    active_abos = Subscription.query.filter(
        Subscription.organization_id == org_id,
        Subscription.status == 'active'
    ).count()

    new_abos = Subscription.query.filter(
        Subscription.organization_id == org_id,
        Subscription.created_at >= date_from,
        Subscription.created_at <= date_to
    ).count()

    ended_abos = Subscription.query.filter(
        Subscription.organization_id == org_id,
        Subscription.end_date >= date_from,
        Subscription.end_date <= date_to,
        Subscription.status == 'expired'
    ).count()

    visits = FitnessVisit.query.filter(
        FitnessVisit.organization_id == org_id,
        FitnessVisit.check_in >= date_from,
        FitnessVisit.check_in <= date_to
    ).count()

    return {
        'active_abos': active_abos,
        'new_abos': new_abos,
        'ended_abos': ended_abos,
        'visits': visits
    }
