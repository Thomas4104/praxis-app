"""KI-Tools fuer den Adressen-Bereich (Versicherungen, Aerzte, Kontakte)"""
import json
from datetime import datetime
from flask_login import current_user
from models import db, InsuranceProvider, Doctor, Contact, TreatmentSeries, Patient


ADDRESS_TOOLS = [
    {
        'name': 'aerzte_auflisten',
        'description': 'Listet alle Aerzte auf, optional gefiltert nach Fachrichtung.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'fachrichtung': {
                    'type': 'string',
                    'description': 'Fachrichtung zum Filtern (optional)'
                }
            },
            'required': []
        }
    },
    {
        'name': 'arzt_details',
        'description': 'Zeigt alle Details eines Arztes inkl. Zuweiserstatistik.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'arzt_id': {'type': 'integer', 'description': 'ID des Arztes'}
            },
            'required': ['arzt_id']
        }
    },
    {
        'name': 'versicherungen_auflisten',
        'description': 'Listet alle aktiven Versicherungen auf.',
        'input_schema': {
            'type': 'object',
            'properties': {},
            'required': []
        }
    },
    {
        'name': 'versicherung_details',
        'description': 'Zeigt alle Details einer Versicherung.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'versicherung_id': {'type': 'integer', 'description': 'ID der Versicherung'}
            },
            'required': ['versicherung_id']
        }
    },
    {
        'name': 'zuweiserstatistik',
        'description': 'Zeigt wie viele Patienten ein Arzt zugewiesen hat.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'arzt_id': {'type': 'integer', 'description': 'ID des Arztes'}
            },
            'required': ['arzt_id']
        }
    }
]


def address_tool_executor(tool_name, tool_input):
    """Fuehrt Adressen-Tools aus"""
    org_id = current_user.organization_id

    if tool_name == 'aerzte_auflisten':
        fachrichtung = tool_input.get('fachrichtung', '').strip()
        query = Doctor.query.filter_by(organization_id=org_id, is_active=True)
        if fachrichtung:
            query = query.filter(Doctor.specialty.ilike(f'%{fachrichtung}%'))
        doctors = query.order_by(Doctor.last_name).all()

        return {
            'anzahl': len(doctors),
            'aerzte': [{
                'id': d.id,
                'name': f'{d.salutation} {d.first_name} {d.last_name}',
                'fachrichtung': d.specialty,
                'gln': d.gln_number,
                'zsr': d.zsr_number,
                'telefon': d.phone,
                'email': d.email,
                'adresse': f'{d.address or ""}, {d.zip_code or ""} {d.city or ""}'.strip(', ')
            } for d in doctors]
        }

    elif tool_name == 'arzt_details':
        doctor = Doctor.query.get(tool_input.get('arzt_id'))
        if not doctor or doctor.organization_id != org_id:
            return {'error': 'Arzt nicht gefunden.'}

        patient_count = TreatmentSeries.query.filter_by(prescribing_doctor_id=doctor.id) \
            .with_entities(TreatmentSeries.patient_id).distinct().count()
        series_count = TreatmentSeries.query.filter_by(prescribing_doctor_id=doctor.id).count()

        return {
            'id': doctor.id,
            'anrede': doctor.salutation,
            'vorname': doctor.first_name,
            'nachname': doctor.last_name,
            'fachrichtung': doctor.specialty,
            'gln_nummer': doctor.gln_number,
            'zsr_nummer': doctor.zsr_number,
            'adresse': f'{doctor.address or ""}, {doctor.zip_code or ""} {doctor.city or ""}'.strip(', '),
            'telefon': doctor.phone,
            'email': doctor.email,
            'fax': doctor.fax,
            'anzahl_patienten_zugewiesen': patient_count,
            'anzahl_serien': series_count,
            'aktiv': doctor.is_active
        }

    elif tool_name == 'versicherungen_auflisten':
        insurances = InsuranceProvider.query.filter_by(organization_id=org_id, is_active=True) \
            .order_by(InsuranceProvider.name).all()

        return {
            'anzahl': len(insurances),
            'versicherungen': [{
                'id': i.id,
                'name': i.name,
                'gln': i.gln_number,
                'telefon': i.phone,
                'email': i.email,
                'e_billing': i.supports_electronic_billing,
                'anzahl_patienten': len(i.patients) if hasattr(i, 'patients') else 0
            } for i in insurances]
        }

    elif tool_name == 'versicherung_details':
        ins = InsuranceProvider.query.get(tool_input.get('versicherung_id'))
        if not ins or ins.organization_id != org_id:
            return {'error': 'Versicherung nicht gefunden.'}

        tiers_payant = []
        if ins.supports_tiers_payant_json:
            try:
                tiers_payant = json.loads(ins.supports_tiers_payant_json)
            except (json.JSONDecodeError, TypeError):
                pass

        patient_count = Patient.query.filter_by(
            insurance_provider_id=ins.id, is_active=True).count()

        return {
            'id': ins.id,
            'name': ins.name,
            'gln_nummer': ins.gln_number,
            'adresse': f'{ins.address or ""}, {ins.zip_code or ""} {ins.city or ""}'.strip(', '),
            'telefon': ins.phone,
            'email': ins.email,
            'fax': ins.fax,
            'elektronische_abrechnung': ins.supports_electronic_billing,
            'tiers_payant_fuer': tiers_payant,
            'anzahl_patienten': patient_count,
            'aktiv': ins.is_active
        }

    elif tool_name == 'zuweiserstatistik':
        doctor = Doctor.query.get(tool_input.get('arzt_id'))
        if not doctor or doctor.organization_id != org_id:
            return {'error': 'Arzt nicht gefunden.'}

        patient_count = TreatmentSeries.query.filter_by(prescribing_doctor_id=doctor.id) \
            .with_entities(TreatmentSeries.patient_id).distinct().count()
        series_count = TreatmentSeries.query.filter_by(prescribing_doctor_id=doctor.id).count()
        active_series = TreatmentSeries.query.filter_by(
            prescribing_doctor_id=doctor.id, status='active').count()

        # Letzte Zuweisungen
        recent = TreatmentSeries.query.filter_by(prescribing_doctor_id=doctor.id) \
            .order_by(TreatmentSeries.created_at.desc()).limit(5).all()

        return {
            'arzt': f'{doctor.salutation} {doctor.first_name} {doctor.last_name}',
            'fachrichtung': doctor.specialty,
            'patienten_zugewiesen': patient_count,
            'serien_gesamt': series_count,
            'serien_aktiv': active_series,
            'letzte_zuweisungen': [{
                'patient': f'{s.patient.first_name} {s.patient.last_name}' if s.patient else '-',
                'diagnose': s.diagnosis_text,
                'datum': s.created_at.strftime('%d.%m.%Y')
            } for s in recent]
        }

    return {'error': f'Unbekanntes Tool: {tool_name}'}
