"""KI-Tools fuer den Gutsprachen-Bereich"""
import json
from datetime import datetime, date
from flask_login import current_user
from models import (db, CostApproval, CostApprovalItem, Patient, InsuranceProvider,
                    TreatmentSeries, Employee, Doctor)


COST_APPROVAL_TOOLS = [
    {
        'name': 'gutsprachen_auflisten',
        'description': 'Listet Gutsprachen auf, optional gefiltert nach Patient oder Status.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'patient_id': {'type': 'integer', 'description': 'ID des Patienten (optional)'},
                'status': {'type': 'string', 'description': 'Statusfilter: draft, sent, approved, partially_approved, rejected, cancelled'}
            },
            'required': []
        }
    },
    {
        'name': 'gutsprache_erstellen',
        'description': 'Erstellt eine neue Kostengutsprache fuer eine Behandlungsserie.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'serie_id': {'type': 'integer', 'description': 'ID der Behandlungsserie'},
                'positionen': {
                    'type': 'array',
                    'description': 'Liste der angefragten Positionen',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'tarifziffer': {'type': 'string'},
                            'beschreibung': {'type': 'string'},
                            'anzahl': {'type': 'number'},
                            'betrag': {'type': 'number'}
                        }
                    }
                },
                'begruendung': {'type': 'string', 'description': 'Begruendungstext'}
            },
            'required': ['serie_id']
        }
    },
    {
        'name': 'gutsprache_details',
        'description': 'Zeigt Details einer Gutsprache an.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'gutsprache_id': {'type': 'integer', 'description': 'ID der Gutsprache'}
            },
            'required': ['gutsprache_id']
        }
    },
    {
        'name': 'gutsprache_antwort_erfassen',
        'description': 'Erfasst die Antwort des Kostentraegers auf eine Gutsprache.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'gutsprache_id': {'type': 'integer', 'description': 'ID der Gutsprache'},
                'ergebnis': {'type': 'string', 'description': 'Ergebnis: approved, partially_approved, rejected'},
                'bewilligte_sitzungen': {'type': 'integer', 'description': 'Anzahl bewilligter Sitzungen'},
                'bewilligter_betrag': {'type': 'number', 'description': 'Bewilligter Betrag in CHF'},
                'gueltig_bis': {'type': 'string', 'description': 'Gueltigkeitsdatum (YYYY-MM-DD)'},
                'ablehnungsgrund': {'type': 'string', 'description': 'Grund bei Ablehnung'}
            },
            'required': ['gutsprache_id', 'ergebnis']
        }
    },
    {
        'name': 'gutsprache_senden',
        'description': 'Sendet eine erstellte Gutsprache ab (Status: draft -> sent).',
        'input_schema': {
            'type': 'object',
            'properties': {
                'gutsprache_id': {'type': 'integer', 'description': 'ID der Gutsprache'}
            },
            'required': ['gutsprache_id']
        }
    }
]


def cost_approval_tool_executor(tool_name, tool_input):
    """Fuehrt Gutsprachen-Tools aus"""
    org_id = current_user.organization_id

    if tool_name == 'gutsprachen_auflisten':
        patient_id = tool_input.get('patient_id')
        status = tool_input.get('status')

        query = CostApproval.query.filter_by(organization_id=org_id)
        if patient_id:
            query = query.filter_by(patient_id=patient_id)
        if status:
            query = query.filter_by(status=status)

        gutsprachen = query.order_by(CostApproval.created_at.desc()).limit(50).all()

        result = []
        for gs in gutsprachen:
            patient_name = f'{gs.patient.first_name} {gs.patient.last_name}' if gs.patient else 'Unbekannt'
            insurance_name = gs.insurance_provider.name if gs.insurance_provider else 'Keine'
            therapist_name = ''
            if gs.therapist and gs.therapist.user:
                therapist_name = f'{gs.therapist.user.first_name} {gs.therapist.user.last_name}'

            status_map = {
                'draft': 'Erstellt', 'sent': 'Gesendet', 'approved': 'Bewilligt',
                'partially_approved': 'Teilbewilligt', 'rejected': 'Abgelehnt', 'cancelled': 'Storniert'
            }
            result.append({
                'id': gs.id,
                'nummer': gs.approval_number,
                'patient': patient_name,
                'versicherung': insurance_name,
                'therapeut': therapist_name,
                'status': status_map.get(gs.status, gs.status),
                'datum': gs.created_at.strftime('%d.%m.%Y') if gs.created_at else '-',
                'angefragte_sitzungen': gs.requested_sessions,
                'bewilligte_sitzungen': gs.approved_sessions,
                'diagnose': f'{gs.diagnosis_code} {gs.diagnosis_text or ""}' if gs.diagnosis_code else '-'
            })

        return {'gutsprachen': result, 'anzahl': len(result)}

    elif tool_name == 'gutsprache_erstellen':
        serie_id = tool_input.get('serie_id')
        positionen = tool_input.get('positionen', [])
        begruendung = tool_input.get('begruendung', '')

        serie = TreatmentSeries.query.get(serie_id)
        if not serie:
            return {'error': f'Behandlungsserie {serie_id} nicht gefunden.'}

        patient = Patient.query.get(serie.patient_id)

        # Naechste Nummer
        last = CostApproval.query.order_by(CostApproval.id.desc()).first()
        next_nr = (last.id + 1) if last else 1

        gs = CostApproval(
            organization_id=org_id,
            approval_number=f'GS-{date.today().year}-{next_nr:04d}',
            series_id=serie_id,
            patient_id=serie.patient_id,
            insurance_provider_id=patient.insurance_provider_id if patient else None,
            doctor_id=serie.prescribing_doctor_id,
            therapist_id=serie.therapist_id,
            diagnosis_code=serie.diagnosis_code,
            diagnosis_text=serie.diagnosis_text,
            prescription_date=serie.prescription_date,
            justification=begruendung,
            status='draft',
            requested_date=date.today()
        )
        db.session.add(gs)
        db.session.flush()

        total = 0.0
        total_sessions = 0
        if positionen:
            for pos in positionen:
                qty = pos.get('anzahl', 1)
                amt = pos.get('betrag', 0)
                item = CostApprovalItem(
                    cost_approval_id=gs.id,
                    tariff_code=pos.get('tarifziffer', ''),
                    description=pos.get('beschreibung', ''),
                    quantity=qty,
                    amount=amt
                )
                db.session.add(item)
                total += amt * qty
                total_sessions += int(qty)
        else:
            # Standard-Position aus Serienvorlage
            tpl = serie.template
            if tpl:
                item = CostApprovalItem(
                    cost_approval_id=gs.id,
                    tariff_code=tpl.tariff_type or '7301',
                    description=tpl.name,
                    quantity=tpl.num_appointments or 9,
                    amount=48.0
                )
                db.session.add(item)
                total = 48.0 * (tpl.num_appointments or 9)
                total_sessions = tpl.num_appointments or 9

        gs.total_amount = total
        gs.requested_sessions = total_sessions
        db.session.commit()

        return {
            'success': True,
            'gutsprache_id': gs.id,
            'nummer': gs.approval_number,
            'message': f'Gutsprache {gs.approval_number} wurde erstellt.'
        }

    elif tool_name == 'gutsprache_details':
        gutsprache_id = tool_input.get('gutsprache_id')
        gs = CostApproval.query.get(gutsprache_id)
        if not gs or gs.organization_id != org_id:
            return {'error': f'Gutsprache {gutsprache_id} nicht gefunden.'}

        items = [{
            'tarifziffer': item.tariff_code,
            'beschreibung': item.description,
            'anzahl': item.quantity,
            'betrag': item.amount,
            'total': item.amount * item.quantity,
            'kommentar': item.comment
        } for item in gs.items.all()]

        status_map = {
            'draft': 'Erstellt', 'sent': 'Gesendet', 'approved': 'Bewilligt',
            'partially_approved': 'Teilbewilligt', 'rejected': 'Abgelehnt', 'cancelled': 'Storniert'
        }

        return {
            'id': gs.id,
            'nummer': gs.approval_number,
            'patient': f'{gs.patient.first_name} {gs.patient.last_name}' if gs.patient else '-',
            'versicherung': gs.insurance_provider.name if gs.insurance_provider else '-',
            'status': status_map.get(gs.status, gs.status),
            'diagnose': f'{gs.diagnosis_code} {gs.diagnosis_text}' if gs.diagnosis_code else '-',
            'angefragte_sitzungen': gs.requested_sessions,
            'bewilligte_sitzungen': gs.approved_sessions,
            'gesamtbetrag': gs.total_amount,
            'bewilligter_betrag': gs.approved_amount,
            'begruendung': gs.justification,
            'ablehnungsgrund': gs.rejection_reason,
            'gueltig_bis': gs.valid_until.strftime('%d.%m.%Y') if gs.valid_until else None,
            'positionen': items
        }

    elif tool_name == 'gutsprache_antwort_erfassen':
        gutsprache_id = tool_input.get('gutsprache_id')
        ergebnis = tool_input.get('ergebnis')
        gs = CostApproval.query.get(gutsprache_id)
        if not gs or gs.organization_id != org_id:
            return {'error': f'Gutsprache {gutsprache_id} nicht gefunden.'}

        if ergebnis == 'approved':
            gs.status = 'approved'
            gs.approved_sessions = tool_input.get('bewilligte_sitzungen', gs.requested_sessions)
            gs.approved_amount = tool_input.get('bewilligter_betrag', gs.total_amount)
        elif ergebnis == 'partially_approved':
            gs.status = 'partially_approved'
            gs.approved_sessions = tool_input.get('bewilligte_sitzungen')
            gs.approved_amount = tool_input.get('bewilligter_betrag')
        elif ergebnis == 'rejected':
            gs.status = 'rejected'
            gs.rejection_reason = tool_input.get('ablehnungsgrund', '')

        gs.response_date = date.today()

        gueltig_bis = tool_input.get('gueltig_bis')
        if gueltig_bis:
            try:
                gs.valid_until = datetime.strptime(gueltig_bis, '%Y-%m-%d').date()
            except ValueError:
                pass

        db.session.commit()
        status_map = {'approved': 'bewilligt', 'partially_approved': 'teilbewilligt', 'rejected': 'abgelehnt'}
        return {
            'success': True,
            'message': f'Gutsprache {gs.approval_number} wurde als {status_map.get(ergebnis, ergebnis)} erfasst.'
        }

    elif tool_name == 'gutsprache_senden':
        gutsprache_id = tool_input.get('gutsprache_id')
        gs = CostApproval.query.get(gutsprache_id)
        if not gs or gs.organization_id != org_id:
            return {'error': f'Gutsprache {gutsprache_id} nicht gefunden.'}

        if gs.status not in ('draft', 'cancelled'):
            return {'error': 'Gutsprache kann in diesem Status nicht gesendet werden.'}

        gs.status = 'sent'
        gs.sent_date = date.today()
        db.session.commit()
        return {'success': True, 'message': f'Gutsprache {gs.approval_number} wurde gesendet.'}

    return {'error': f'Unbekanntes Tool: {tool_name}'}
