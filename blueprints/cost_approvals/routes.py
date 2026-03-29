"""Routen fuer Gutsprachen-Verwaltung (Cenplex: Kostengutsprache)
Erweitert um MediData XML 4.5, Blanko-KoGu, Tracking, erweiterte Filter"""
from datetime import datetime, date, timezone
import json
import uuid
import xml.etree.ElementTree as ET
from flask import render_template, request, jsonify, redirect, url_for, flash, Response
from flask_login import login_required, current_user
from blueprints.cost_approvals import cost_approvals_bp
from models import (db, CostApproval, CostApprovalItem, Patient, InsuranceProvider,
                    Doctor, Employee, TreatmentSeries, TreatmentSeriesTemplate,
                    MedidataResponse, MedidataTracking, Contact)
from utils.auth import check_org, get_org_id


# === Konstanten (Cenplex-Enums) ===

TREATMENT_REASONS = {
    0: 'Krankheit',
    1: 'Unfall',
    2: 'Mutterschaft',
    3: 'Prävention',
    4: 'Geburtsgebrechen',
    5: 'Unbekannt',
}

BILLING_CASES = {
    0: 'KVG',
    1: 'Suva/UVG',
    2: 'Militär',
    3: 'Privat',
    4: 'Spital',
    5: 'IV',
    6: 'VVG',
    7: 'Pauschal',
}

TARIF_CODES = {
    311: 'UVG alt',
    312: 'Physiotherapie Standard',
    313: 'UVG neu',
    325: 'Ergotherapie A',
    338: 'Ergotherapie B',
}

# Cenplex UserActionType fuer Kostengutsprache
ACTION_SEND = 19
ACTION_STORNO = 20
ACTION_PROLONG = 21
ACTION_RECONSIDER = 22
ACTION_DELETE = 35
ACTION_SEND_EMAIL = 37

ACTION_LABELS = {
    ACTION_SEND: 'Erstellt und gesendet',
    ACTION_STORNO: 'Storniert',
    ACTION_PROLONG: 'Verlängert',
    ACTION_RECONSIDER: 'Wiedererwägung',
    ACTION_DELETE: 'Gelöscht',
    ACTION_SEND_EMAIL: 'Per E-Mail gesendet',
}

STATUS_LABELS = {
    'draft': 'Erstellt',
    'sent': 'Gesendet',
    'approved': 'Bewilligt',
    'partially_approved': 'Teilbewilligt',
    'rejected': 'Abgelehnt',
    'cancelled': 'Storniert',
}


def _create_tracking(kogu_id, action_type, employee_id=None, request_id=None, params=None):
    """Tracking-Eintrag erstellen (Cenplex: MedidatatrackingDto)"""
    tracking = MedidataTracking(
        cost_approval_id=kogu_id,
        action_type=action_type,
        employee_id=employee_id or (current_user.employee.id if hasattr(current_user, 'employee') and current_user.employee else None),
        request_id=request_id,
        is_xml45=True,
        track_parameter=json.dumps(params) if params else None
    )
    db.session.add(tracking)
    return tracking


def _generate_request_id():
    """Eindeutige Request-ID fuer MediData generieren"""
    return f'KG-{uuid.uuid4().hex[:12].upper()}'


def _generate_xml45(gutsprache, items):
    """MediData XML 4.5 Kostengutsprache-Request generieren (Cenplex: requestType)"""
    ns = 'http://www.forum-datenaustausch.ch/credit'
    ET.register_namespace('', ns)
    ET.register_namespace('xsi', 'http://www.w3.org/2001/XMLSchema-instance')

    request_el = ET.Element('{%s}request' % ns)
    request_el.set('language', 'de')
    request_el.set('modus', 'production')
    request_el.set('validation_status', '0')

    # Processing
    processing = ET.SubElement(request_el, 'processing')
    transport = ET.SubElement(processing, 'transport')
    transport_from = ET.SubElement(transport, 'via')
    transport_from.set('via', 'OMNIA')
    transport_from.set('sequence_id', '1')

    # Payload
    payload = ET.SubElement(request_el, 'payload')
    payload_type = 'copy' if gutsprache.payload_type == 2 else 'new'
    payload.set('type', payload_type)
    payload.set('storno', 'true' if gutsprache.is_storno else 'false')
    payload.set('copy', 'true' if gutsprache.extension_of_id else 'false')

    # Credit-Referenz
    if gutsprache.extension_of_id and gutsprache.extension_of:
        credit_ref = ET.SubElement(payload, 'credit_ref')
        ref_req_id = ET.SubElement(credit_ref, 'request_id')
        ref_req_id.text = gutsprache.extension_of.request_id or ''

    # Credit
    credit = ET.SubElement(payload, 'credit')
    req_id = ET.SubElement(credit, 'request_id')
    req_id.text = gutsprache.request_id or ''
    req_date = ET.SubElement(credit, 'request_date')
    req_date.text = (gutsprache.sent_date or date.today()).isoformat()
    req_ts = ET.SubElement(credit, 'request_timestamp')
    req_ts.text = datetime.now().isoformat()

    # Body
    body = ET.SubElement(payload, 'body')
    # Behandlungsgrund
    treatment = ET.SubElement(body, 'treatment')
    reason = ET.SubElement(treatment, 'reason')
    reason.text = TREATMENT_REASONS.get(gutsprache.treatment_reason, 'Unbekannt')
    diagnosis = ET.SubElement(treatment, 'diagnosis')
    diag_type = ET.SubElement(diagnosis, 'type')
    diag_type.text = 'ICD'
    diag_code = ET.SubElement(diagnosis, 'code')
    diag_code.text = gutsprache.diagnosis_code or ''
    diag_name = ET.SubElement(diagnosis, 'name')
    diag_name.text = gutsprache.diagnosis_text or ''

    if gutsprache.treatment_title:
        title_el = ET.SubElement(treatment, 'title')
        title_el.text = gutsprache.treatment_title

    if gutsprache.measures:
        measures_el = ET.SubElement(treatment, 'measures')
        measures_el.text = gutsprache.measures

    # Patient
    if gutsprache.patient:
        patient_el = ET.SubElement(body, 'patient')
        p = gutsprache.patient
        if p.ahv_number:
            ssn = ET.SubElement(patient_el, 'ssn')
            ssn.text = p.ahv_number
        person = ET.SubElement(patient_el, 'person')
        ET.SubElement(person, 'familyname').text = p.last_name or ''
        ET.SubElement(person, 'givenname').text = p.first_name or ''
        if p.date_of_birth:
            ET.SubElement(person, 'birthdate').text = p.date_of_birth.isoformat()

    # Versicherung / Kostentraeger
    if gutsprache.insurance_provider:
        ins_el = ET.SubElement(body, 'insurance')
        ins = gutsprache.insurance_provider
        if ins.gln_number:
            ET.SubElement(ins_el, 'ean_party').text = ins.gln_number
        ET.SubElement(ins_el, 'company_name').text = ins.name or ''

    # Positionen / Services
    services = ET.SubElement(body, 'services')
    for item in items:
        svc = ET.SubElement(services, 'service')
        svc.set('tariff_type', str(gutsprache.tarif or 312))
        svc.set('code', item.tariff_code or '')
        svc.set('name', item.description or '')
        if item.comment:
            svc.set('remark', item.comment)

        cost_req = ET.SubElement(svc, 'cost_request')
        cost_req.set('base_amount', f'{float(item.amount):.2f}')
        cost_req.set('scale_factor', f'{float(item.tax_point_value or 1.0):.2f}')
        cost_req.set('quantity', str(int(item.quantity)))

    # Begruendung
    if gutsprache.justification:
        remark = ET.SubElement(body, 'remark')
        remark.text = gutsprache.justification

    return ET.tostring(request_el, encoding='unicode', xml_declaration=True)


def _parse_xml45_response(xml_str):
    """MediData XML 4.5 Response parsen (Cenplex: responseType)"""
    try:
        root = ET.fromstring(xml_str)
        ns = {'cr': 'http://www.forum-datenaustausch.ch/credit'}

        result_data = {
            'result': 1,  # Default: Pending
            'request_id': '',
            'response_id': '',
            'response_date': None,
        }

        # Credit-Referenz
        credit = root.find('.//credit', ns) or root.find('.//credit')
        if credit is not None:
            rid = credit.find('request_id')
            if rid is not None:
                result_data['request_id'] = rid.text or ''
            resp_id = credit.find('response_id')
            if resp_id is not None:
                result_data['response_id'] = resp_id.text or ''

        # Akzeptiert
        accepted = root.find('.//accepted', ns) or root.find('.//accepted')
        if accepted is not None:
            result_data['result'] = 0
            expl = accepted.find('explanation')
            result_data['accepted_explanation'] = expl.text if expl is not None else ''
            coverage = accepted.find('coverage')
            if coverage is not None:
                result_data['coverage_type'] = coverage.get('coverage_type', '')
                result_data['coverage_begin'] = coverage.get('coverage_begin', '')
                result_data['coverage_end'] = coverage.get('coverage_end', '')
                result_data['coverage_units'] = coverage.get('coverage_units', '')

        # Haengig
        pending = root.find('.//pending', ns) or root.find('.//pending')
        if pending is not None:
            result_data['result'] = 1
            notifications = []
            for notif in pending.findall('notification') or []:
                notifications.append({
                    'code': notif.get('code', ''),
                    'text': notif.get('text', '') or (notif.text or '')
                })
            result_data['pending_messages'] = json.dumps(notifications)

        # Abgelehnt
        rejected = root.find('.//rejected', ns) or root.find('.//rejected')
        if rejected is not None:
            result_data['result'] = 2
            errors = []
            for err in rejected.findall('error') or []:
                errors.append({
                    'code': err.get('code', ''),
                    'text': err.get('text', '') or (err.text or ''),
                    'error_value': err.get('error_value', ''),
                    'valid_value': err.get('valid_value', ''),
                    'record_id': err.get('record_id', '')
                })
            result_data['rejected_error'] = json.dumps(errors)

        return result_data
    except ET.ParseError:
        return None


# ============================================================
# Uebersicht
# ============================================================

@cost_approvals_bp.route('/')
@login_required
def index():
    """Gutsprachen-Uebersicht mit erweiterten Filtern (Cenplex: KostengutsprachenViewModel)"""
    search = request.args.get('search', '').strip()
    status = request.args.get('status', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    therapist_id = request.args.get('therapist_id', '', type=str)
    answer_filter = request.args.get('answer_filter', '')  # exist, dont_exist, unchecked
    billing_case = request.args.get('billing_case', '')

    query = CostApproval.query.filter_by(organization_id=current_user.organization_id)

    if search:
        # Cenplex: Suche ueber Patient, Versicherung, Nummer, ID
        # Join nur einmal ausfuehren, dann alle Terme als Filter anwenden
        query = query.join(Patient, CostApproval.patient_id == Patient.id, isouter=True)\
            .join(InsuranceProvider, CostApproval.insurance_provider_id == InsuranceProvider.id, isouter=True)
        search_terms = search.split()
        for term in search_terms:
            term_filter = f'%{term}%'
            # ID-Suche
            try:
                search_id = int(term)
                query = query.filter(db.or_(
                    CostApproval.id == search_id,
                    CostApproval.approval_number.ilike(term_filter)
                ))
                continue
            except ValueError:
                pass
            query = query.filter(db.or_(
                    Patient.first_name.ilike(term_filter),
                    Patient.last_name.ilike(term_filter),
                    InsuranceProvider.name.ilike(term_filter),
                    CostApproval.approval_number.ilike(term_filter)
                ))

    if status:
        query = query.filter(CostApproval.status == status)

    if therapist_id:
        query = query.filter(CostApproval.therapist_id == int(therapist_id))

    if billing_case:
        query = query.filter(CostApproval.ca_billing_case == int(billing_case))

    # Cenplex: Antwort-Filter (KoguAnswerFilter)
    if answer_filter == 'exist':
        query = query.filter(CostApproval.response_date.isnot(None))
    elif answer_filter == 'dont_exist':
        query = query.filter(CostApproval.response_date.is_(None))
    elif answer_filter == 'unchecked':
        # Hat Antworten, aber nicht alle als erledigt markiert
        query = query.filter(CostApproval.response_date.isnot(None))
        open_responses = db.session.query(MedidataResponse.cost_approval_id).filter(
            MedidataResponse.is_done == False
        ).distinct().scalar_subquery()
        query = query.filter(CostApproval.id.in_(open_responses))

    if date_from:
        try:
            df = datetime.strptime(date_from, '%Y-%m-%d').date()
            query = query.filter(CostApproval.created_at >= datetime.combine(df, datetime.min.time()))
        except ValueError:
            pass

    if date_to:
        try:
            dt = datetime.strptime(date_to, '%Y-%m-%d').date()
            query = query.filter(CostApproval.created_at <= datetime.combine(dt, datetime.max.time()))
        except ValueError:
            pass

    gutsprachen = query.order_by(CostApproval.created_at.desc()).all()

    # Therapeuten fuer Filter laden
    therapeuten = Employee.query.filter_by(
        organization_id=current_user.organization_id, is_active=True
    ).all()

    return render_template('cost_approvals/index.html',
                           gutsprachen=gutsprachen,
                           search=search,
                           status_filter=status,
                           date_from=date_from,
                           date_to=date_to,
                           therapist_id=therapist_id,
                           answer_filter=answer_filter,
                           billing_case=billing_case,
                           therapeuten=therapeuten,
                           billing_cases=BILLING_CASES,
                           status_labels=STATUS_LABELS)


# ============================================================
# Erstellen
# ============================================================

@cost_approvals_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    """Neue Gutsprache erstellen (Cenplex: KostengutspracheDialogViewModel)"""
    if request.method == 'POST':
        patient_id = request.form.get('patient_id', type=int)
        series_id = request.form.get('series_id', type=int)
        insurance_provider_id = request.form.get('insurance_provider_id', type=int)
        doctor_id = request.form.get('doctor_id', type=int)
        therapist_id = request.form.get('therapist_id', type=int)
        diagnosis_code = request.form.get('diagnosis_code', '').strip()
        diagnosis_text = request.form.get('diagnosis_text', '').strip()
        prescription_date_str = request.form.get('prescription_date', '')
        prescription_type = request.form.get('prescription_type', '')
        justification = request.form.get('justification', '').strip()

        # Cenplex-Felder
        treatment_title = request.form.get('treatment_title', '').strip()
        treatment_reason = request.form.get('treatment_reason', type=int)
        measures = request.form.get('measures', '').strip()
        tarif = request.form.get('tarif', type=int) or 312
        ca_billing_case = request.form.get('ca_billing_case', type=int) or 0
        kogu_type = request.form.get('kogu_type', type=int) or 0  # 0=normal, 2=blanko
        ca_receiver_email = request.form.get('ca_receiver_email', '').strip()
        extension_of_id = request.form.get('extension_of_id', type=int)

        # Validierung: Behandlungsgrund ist Pflichtfeld (Cenplex)
        if treatment_reason is None:
            flash('Behandlungsgrund ist ein Pflichtfeld.', 'error')
            return redirect(request.url)

        # Naechste Gutsprache-Nummer generieren
        last = CostApproval.query.filter_by(
            organization_id=current_user.organization_id
        ).order_by(CostApproval.id.desc()).first()
        next_nr = (last.id + 1) if last else 1
        approval_number = f'GS-{date.today().year}-{next_nr:04d}'

        prescription_date = None
        if prescription_date_str:
            try:
                prescription_date = datetime.strptime(prescription_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass

        # Request-ID generieren
        request_id = _generate_request_id()

        gutsprache = CostApproval(
            organization_id=current_user.organization_id,
            approval_number=approval_number,
            patient_id=patient_id,
            series_id=series_id,
            insurance_provider_id=insurance_provider_id,
            doctor_id=doctor_id,
            therapist_id=therapist_id,
            diagnosis_code=diagnosis_code,
            diagnosis_text=diagnosis_text,
            prescription_date=prescription_date,
            prescription_type=prescription_type,
            justification=justification,
            status='draft',
            requested_date=date.today(),
            # Cenplex-Felder
            treatment_title=treatment_title,
            treatment_reason=treatment_reason,
            measures=measures,
            tarif=tarif,
            ca_billing_case=ca_billing_case,
            kogu_type=kogu_type,
            ca_receiver_email=ca_receiver_email,
            extension_of_id=extension_of_id,
            request_id=request_id,
            is_xml45=True,
            payload_type=2 if extension_of_id else 0,
        )
        db.session.add(gutsprache)
        db.session.flush()

        # Positionen hinzufuegen (nicht bei Blanko-KoGu)
        total = 0.0
        total_sessions = 0
        if kogu_type != 2:
            tariff_codes = request.form.getlist('tariff_code[]')
            descriptions = request.form.getlist('item_description[]')
            quantities = request.form.getlist('quantity[]')
            amounts = request.form.getlist('amount[]')
            comments = request.form.getlist('item_comment[]')

            for i in range(len(tariff_codes)):
                if not tariff_codes[i] and not (descriptions[i] if i < len(descriptions) else ''):
                    continue
                qty = float(quantities[i]) if i < len(quantities) and quantities[i] else 1.0
                amt = float(amounts[i]) if i < len(amounts) and amounts[i] else 0.0
                comment = comments[i] if i < len(comments) else ''

                item = CostApprovalItem(
                    cost_approval_id=gutsprache.id,
                    tariff_code=tariff_codes[i],
                    description=descriptions[i] if i < len(descriptions) else '',
                    quantity=qty,
                    amount=amt,
                    comment=comment
                )
                db.session.add(item)
                total += amt * qty
                total_sessions += int(qty)

        # Behandlungstitel automatisch generieren wenn leer (Cenplex)
        if not gutsprache.treatment_title and total_sessions > 0:
            gutsprache.treatment_title = f'{total_sessions} Sitzungen'

        gutsprache.total_amount = total
        gutsprache.requested_sessions = total_sessions
        db.session.commit()
        flash('Gutsprache erfolgreich erstellt.', 'success')
        return redirect(url_for('cost_approvals.detail', id=gutsprache.id))

    # GET: Formulardaten laden
    patients = Patient.query.filter_by(
        organization_id=current_user.organization_id, is_active=True
    ).order_by(Patient.last_name).all()

    insurances = InsuranceProvider.query.filter_by(organization_id=current_user.organization_id, is_active=True).all()
    doctors = Doctor.query.filter_by(organization_id=current_user.organization_id, is_active=True).order_by(Doctor.last_name).all()
    employees = Employee.query.filter_by(
        organization_id=current_user.organization_id, is_active=True
    ).all()

    # Vorausgewaehlter Patient (aus URL-Parameter)
    preselect_patient_id = request.args.get('patient_id', type=int)
    preselect_series_id = request.args.get('series_id', type=int)

    # Fruehere Gutsprachen fuer Verlaengerung laden
    extensions = []
    if preselect_patient_id:
        extensions = CostApproval.query.filter(
            CostApproval.organization_id == current_user.organization_id,
            CostApproval.patient_id == preselect_patient_id,
            CostApproval.status.in_(['approved', 'partially_approved']),
            CostApproval.is_storno == False
        ).order_by(CostApproval.created_at.desc()).all()

    return render_template('cost_approvals/form.html',
                           patients=patients,
                           insurances=insurances,
                           doctors=doctors,
                           employees=employees,
                           preselect_patient_id=preselect_patient_id,
                           preselect_series_id=preselect_series_id,
                           extensions=extensions,
                           treatment_reasons=TREATMENT_REASONS,
                           billing_cases=BILLING_CASES,
                           tarif_codes=TARIF_CODES)


# ============================================================
# Detail
# ============================================================

@cost_approvals_bp.route('/detail/<int:id>')
@login_required
def detail(id):
    """Gutsprache-Detail (Cenplex: KostengutspracheDetailViewModel)"""
    gutsprache = CostApproval.query.get_or_404(id)
    check_org(gutsprache)
    items = gutsprache.items.all()

    # MediData-Antworten laden
    responses = gutsprache.medidata_responses.order_by(MedidataResponse.received.desc()).all()

    # Tracking-Historie laden
    trackings = gutsprache.medidata_trackings.order_by(MedidataTracking.action_date.desc()).all()

    # Verlaengerungen laden
    extensions = CostApproval.query.filter_by(extension_of_id=id).order_by(CostApproval.created_at.desc()).all()

    return render_template('cost_approvals/detail.html',
                           gutsprache=gutsprache,
                           items=items,
                           responses=responses,
                           trackings=trackings,
                           extensions=extensions,
                           treatment_reasons=TREATMENT_REASONS,
                           billing_cases=BILLING_CASES,
                           tarif_codes=TARIF_CODES,
                           action_labels=ACTION_LABELS,
                           status_labels=STATUS_LABELS)


# ============================================================
# Senden
# ============================================================

@cost_approvals_bp.route('/api/<int:id>/send', methods=['POST'])
@login_required
def send_approval(id):
    """Gutsprache senden mit MediData XML 4.5 (Cenplex: CreateSendKostengutspracheAsync)"""
    gutsprache = CostApproval.query.get_or_404(id)
    check_org(gutsprache)
    if gutsprache.status not in ('draft', 'cancelled'):
        return jsonify({'error': 'Gutsprache kann in diesem Status nicht gesendet werden.'}), 400

    items = gutsprache.items.all()

    # Validierung: Behandlungsgrund erforderlich
    if gutsprache.treatment_reason is None:
        return jsonify({'error': 'Behandlungsgrund muss angegeben werden.'}), 400

    # XML 4.5 generieren (ausser bei Blanko)
    if gutsprache.kogu_type != 2:
        if not items:
            return jsonify({'error': 'Keine Positionen vorhanden.'}), 400
        xml_content = _generate_xml45(gutsprache, items)
        gutsprache.is_xml45 = True
    else:
        xml_content = None

    gutsprache.status = 'sent'
    gutsprache.sent_date = date.today()
    if not gutsprache.request_id:
        gutsprache.request_id = _generate_request_id()

    # Tracking erstellen
    _create_tracking(
        gutsprache.id, ACTION_SEND,
        request_id=gutsprache.request_id,
        params={'xml_generated': xml_content is not None}
    )

    db.session.commit()
    return jsonify({'success': True, 'message': 'Gutsprache wurde gesendet.', 'request_id': gutsprache.request_id})


# ============================================================
# Antwort erfassen
# ============================================================

@cost_approvals_bp.route('/api/<int:id>/respond', methods=['POST'])
@login_required
def record_response(id):
    """Antwort erfassen (Cenplex: MedidataresponseDto + FinishAnswerAsync)"""
    gutsprache = CostApproval.query.get_or_404(id)
    check_org(gutsprache)
    data = request.get_json()

    result = data.get('result')  # approved, partially_approved, rejected
    approved_sessions = int(data.get('approved_sessions')) if data.get('approved_sessions') is not None else None
    approved_amount = float(data.get('approved_amount')) if data.get('approved_amount') is not None else None
    valid_until = data.get('valid_until', '')
    rejection_reason = data.get('rejection_reason', '')
    response_notes = data.get('response_notes', '')
    coverage_type = data.get('coverage_type', '')
    coverage_begin = data.get('coverage_begin', '')
    coverage_end = data.get('coverage_end', '')

    # MedidataResponse erstellen (Cenplex-Muster)
    result_code = 0 if result == 'approved' else (1 if result == 'partially_approved' else 2)
    medidata_resp = MedidataResponse(
        cost_approval_id=gutsprache.id,
        result=result_code,
        request_id=gutsprache.request_id,
        coverage_type=coverage_type or None,
    )

    if result == 'approved':
        gutsprache.status = 'approved'
        gutsprache.approved_sessions = approved_sessions or gutsprache.requested_sessions
        gutsprache.approved_amount = approved_amount or gutsprache.total_amount
        medidata_resp.accepted_explanation = response_notes
        medidata_resp.accepted_has_reimbursement = True
    elif result == 'partially_approved':
        gutsprache.status = 'partially_approved'
        gutsprache.approved_sessions = approved_sessions
        gutsprache.approved_amount = approved_amount
        medidata_resp.accepted_explanation = response_notes
    elif result == 'rejected':
        gutsprache.status = 'rejected'
        gutsprache.rejection_reason = rejection_reason
        medidata_resp.rejected_explanation = rejection_reason

    gutsprache.response_date = date.today()
    gutsprache.response_notes = response_notes

    if valid_until:
        try:
            gutsprache.valid_until = datetime.strptime(valid_until, '%Y-%m-%d').date()
        except ValueError:
            pass

    if coverage_begin:
        try:
            medidata_resp.coverage_begin = datetime.strptime(coverage_begin, '%Y-%m-%d').date()
        except ValueError:
            pass
    if coverage_end:
        try:
            medidata_resp.coverage_end = datetime.strptime(coverage_end, '%Y-%m-%d').date()
        except ValueError:
            pass

    db.session.add(medidata_resp)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Antwort wurde erfasst.'})


# ============================================================
# XML-Antwort importieren
# ============================================================

@cost_approvals_bp.route('/api/<int:id>/import-response', methods=['POST'])
@login_required
def import_xml_response(id):
    """MediData XML 4.5 Response importieren (Cenplex: Response-Verarbeitung)"""
    gutsprache = CostApproval.query.get_or_404(id)
    check_org(gutsprache)

    xml_data = request.form.get('xml_content', '')
    xml_file = request.files.get('xml_file')

    if xml_file:
        xml_data = xml_file.read().decode('utf-8')

    if not xml_data:
        return jsonify({'error': 'Keine XML-Daten vorhanden.'}), 400

    parsed = _parse_xml45_response(xml_data)
    if not parsed:
        return jsonify({'error': 'XML konnte nicht geparst werden.'}), 400

    # MedidataResponse erstellen
    medidata_resp = MedidataResponse(
        cost_approval_id=gutsprache.id,
        result=parsed['result'],
        request_id=parsed.get('request_id', gutsprache.request_id),
        response_document=xml_data.encode('utf-8'),
    )

    if parsed['result'] == 0:  # Accepted
        medidata_resp.accepted_explanation = parsed.get('accepted_explanation', '')
        medidata_resp.coverage_type = parsed.get('coverage_type', '')
        if parsed.get('coverage_begin'):
            try:
                medidata_resp.coverage_begin = datetime.strptime(parsed['coverage_begin'], '%Y-%m-%d').date()
            except ValueError:
                pass
        if parsed.get('coverage_end'):
            try:
                medidata_resp.coverage_end = datetime.strptime(parsed['coverage_end'], '%Y-%m-%d').date()
            except ValueError:
                pass
        if parsed.get('coverage_units'):
            try:
                medidata_resp.coverage_units = int(parsed['coverage_units'])
            except (ValueError, TypeError):
                pass
        gutsprache.status = 'approved'
        gutsprache.response_date = date.today()
    elif parsed['result'] == 1:  # Pending
        medidata_resp.pending_messages = parsed.get('pending_messages', '')
    elif parsed['result'] == 2:  # Rejected
        medidata_resp.rejected_explanation = parsed.get('rejected_explanation', '')
        medidata_resp.rejected_error = parsed.get('rejected_error', '')
        gutsprache.status = 'rejected'
        gutsprache.response_date = date.today()

    db.session.add(medidata_resp)
    db.session.commit()

    result_label = {0: 'Bewilligt', 1: 'Hängig', 2: 'Abgelehnt'}.get(parsed['result'], 'Unbekannt')
    return jsonify({'success': True, 'message': f'XML-Antwort importiert: {result_label}'})


# ============================================================
# Antwort als erledigt markieren
# ============================================================

@cost_approvals_bp.route('/api/response/<int:response_id>/done', methods=['POST'])
@login_required
def mark_response_done(response_id):
    """MediData-Antwort als erledigt markieren (Cenplex: FinishAnswerAsync)"""
    resp = MedidataResponse.query.get_or_404(response_id)
    gutsprache = CostApproval.query.get_or_404(resp.cost_approval_id)
    check_org(gutsprache)
    resp.is_done = True
    db.session.commit()
    return jsonify({'success': True, 'message': 'Antwort als erledigt markiert.'})


# ============================================================
# Storno
# ============================================================

@cost_approvals_bp.route('/api/<int:id>/cancel', methods=['POST'])
@login_required
def cancel_approval(id):
    """Gutsprache stornieren (Cenplex: CancelKostengutspracheAsync)"""
    gutsprache = CostApproval.query.get_or_404(id)
    check_org(gutsprache)
    gutsprache.is_storno = True
    gutsprache.status = 'cancelled'

    _create_tracking(gutsprache.id, ACTION_STORNO, request_id=gutsprache.request_id)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Gutsprache wurde storniert.'})


# ============================================================
# Erneut senden / Wiedererwaegung
# ============================================================

@cost_approvals_bp.route('/api/<int:id>/resend', methods=['POST'])
@login_required
def resend_approval(id):
    """Gutsprache erneut senden (Cenplex: ReconsiderSendKostengutspracheAsync)"""
    gutsprache = CostApproval.query.get_or_404(id)
    check_org(gutsprache)
    if gutsprache.status not in ('rejected', 'cancelled'):
        return jsonify({'error': 'Gutsprache kann nicht erneut gesendet werden.'}), 400

    # Neue Request-ID generieren (Cenplex: Reconsider erzeugt neue ID)
    gutsprache.request_id = _generate_request_id()
    gutsprache.status = 'sent'
    gutsprache.sent_date = date.today()
    gutsprache.response_date = None
    gutsprache.rejection_reason = None
    gutsprache.response_notes = None
    gutsprache.is_storno = False

    _create_tracking(gutsprache.id, ACTION_RECONSIDER, request_id=gutsprache.request_id)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Gutsprache wurde erneut gesendet.'})


# ============================================================
# Verlaengerung
# ============================================================

@cost_approvals_bp.route('/detail/<int:id>/extend', methods=['POST'])
@login_required
def extend_approval(id):
    """Kostengutsprache verlaengern (Cenplex: Extension mit PayloadType=2)"""
    original = CostApproval.query.get_or_404(id)
    check_org(original)

    # Naechste Gutsprache-Nummer generieren
    last = CostApproval.query.filter_by(
        organization_id=current_user.organization_id
    ).order_by(CostApproval.id.desc()).first()
    next_nr = (last.id + 1) if last else 1

    extension = CostApproval(
        organization_id=current_user.organization_id,
        approval_number=f'GS-{date.today().year}-{next_nr:04d}',
        series_id=original.series_id,
        patient_id=original.patient_id,
        insurance_provider_id=original.insurance_provider_id,
        doctor_id=original.doctor_id,
        therapist_id=original.therapist_id,
        diagnosis_code=original.diagnosis_code,
        diagnosis_text=original.diagnosis_text,
        prescription_date=original.prescription_date,
        prescription_type=original.prescription_type,
        justification=request.form.get('justification', original.justification),
        requested_sessions=int(request.form.get('requested_sessions', original.requested_sessions or 9)),
        total_amount=float(request.form.get('total_amount', 0)) if request.form.get('total_amount') else None,
        status='draft',
        requested_date=date.today(),
        extension_of_id=id,
        # Cenplex: Verlaengerung uebernimmt Cenplex-Felder
        treatment_title=original.treatment_title,
        treatment_reason=original.treatment_reason,
        measures=original.measures,
        tarif=original.tarif,
        ca_billing_case=original.ca_billing_case,
        kogu_type=original.kogu_type,
        ca_receiver_email=original.ca_receiver_email,
        payload_type=2,  # Cenplex: Extension
        request_id=_generate_request_id(),
        is_xml45=True,
    )

    db.session.add(extension)
    db.session.flush()

    # Positionen vom Original kopieren und Total berechnen
    total = 0.0
    total_sessions = 0
    for orig_item in original.items.all():
        item = CostApprovalItem(
            cost_approval_id=extension.id,
            tariff_code=orig_item.tariff_code,
            description=orig_item.description,
            quantity=orig_item.quantity,
            amount=orig_item.amount,
            tax_point_value=orig_item.tax_point_value,
            comment=orig_item.comment,
        )
        db.session.add(item)
        total += float(orig_item.amount or 0) * float(orig_item.quantity or 1)
        total_sessions += int(orig_item.quantity or 1)

    # Total aus kopierten Items setzen wenn nicht aus Form
    if not extension.total_amount:
        extension.total_amount = total
    if not extension.requested_sessions:
        extension.requested_sessions = total_sessions

    _create_tracking(extension.id, ACTION_PROLONG, request_id=extension.request_id,
                     params={'original_id': id})
    db.session.commit()

    flash('Verlängerung erstellt.', 'success')
    return redirect(url_for('cost_approvals.detail', id=extension.id))


# ============================================================
# XML-Download
# ============================================================

@cost_approvals_bp.route('/api/<int:id>/xml')
@login_required
def download_xml(id):
    """MediData XML 4.5 herunterladen"""
    gutsprache = CostApproval.query.get_or_404(id)
    check_org(gutsprache)
    items = gutsprache.items.all()
    xml_content = _generate_xml45(gutsprache, items)
    return Response(
        xml_content,
        mimetype='application/xml',
        headers={'Content-Disposition': f'attachment; filename=KoGu_{gutsprache.approval_number}.xml'}
    )


# ============================================================
# Per E-Mail senden
# ============================================================

@cost_approvals_bp.route('/api/<int:id>/send-email', methods=['POST'])
@login_required
def send_email(id):
    """Gutsprache per E-Mail an Versicherung senden (Cenplex: SendKoguEmailViewModel)"""
    gutsprache = CostApproval.query.get_or_404(id)
    check_org(gutsprache)

    data = request.get_json() or {}
    receiver_email = data.get('receiver_email', gutsprache.ca_receiver_email or '')

    if not receiver_email:
        # E-Mail der Versicherung verwenden
        if gutsprache.insurance_provider:
            receiver_email = getattr(gutsprache.insurance_provider, 'email_gutsprache', '') or gutsprache.insurance_provider.email or ''

    if not receiver_email:
        return jsonify({'error': 'Keine Empfänger-E-Mail angegeben.'}), 400

    gutsprache.ca_receiver_email = receiver_email

    # Tracking erstellen
    _create_tracking(
        gutsprache.id, ACTION_SEND_EMAIL,
        request_id=gutsprache.request_id,
        params={'receiver_email': receiver_email}
    )

    # Wenn noch Draft, auf gesendet setzen
    if gutsprache.status == 'draft':
        gutsprache.status = 'sent'
        gutsprache.sent_date = date.today()

    db.session.commit()
    return jsonify({
        'success': True,
        'message': f'E-Mail-Versand an {receiver_email} vorgemerkt.'
    })


# ============================================================
# API: Patientendaten
# ============================================================

@cost_approvals_bp.route('/api/patient/<int:patient_id>/series')
@login_required
def patient_series(patient_id):
    """Aktive Serien eines Patienten laden"""
    patient = Patient.query.get_or_404(patient_id)
    check_org(patient)
    serien = TreatmentSeries.query.filter_by(
        patient_id=patient_id, status='active'
    ).all()
    result = []
    for s in serien:
        template_name = s.template.name if s.template else 'Ohne Vorlage'
        result.append({
            'id': s.id,
            'name': f'{template_name} ({s.diagnosis_text or s.diagnosis_code or ""})',
            'diagnosis_code': s.diagnosis_code,
            'diagnosis_text': s.diagnosis_text,
            'therapist_id': s.therapist_id,
            'doctor_id': s.prescribing_doctor_id,
            'insurance_type': s.insurance_type,
            'prescription_date': s.prescription_date.strftime('%Y-%m-%d') if s.prescription_date else '',
            'prescription_type': s.prescription_type or '',
            'billing_case': s.billing_case if hasattr(s, 'billing_case') else 0,
        })
    return jsonify({'series': result})


@cost_approvals_bp.route('/api/patient/<int:patient_id>/insurance')
@login_required
def patient_insurance(patient_id):
    """Versicherung eines Patienten laden"""
    patient = Patient.query.get_or_404(patient_id)
    check_org(patient)
    result = {
        'insurance_provider_id': patient.insurance_provider_id,
        'insurance_type': patient.insurance_type,
        'insurance_number': patient.insurance_number
    }
    return jsonify(result)


@cost_approvals_bp.route('/api/patient/<int:patient_id>/extensions')
@login_required
def patient_extensions(patient_id):
    """Fruehere bewilligte Gutsprachen eines Patienten laden (Cenplex: GetKostengutspracheExtensionsAsync)"""
    patient = Patient.query.get_or_404(patient_id)
    check_org(patient)
    extensions = CostApproval.query.filter(
        CostApproval.organization_id == current_user.organization_id,
        CostApproval.patient_id == patient_id,
        CostApproval.status.in_(['approved', 'partially_approved']),
        CostApproval.is_storno == False
    ).order_by(CostApproval.created_at.desc()).all()

    result = []
    for ext in extensions:
        result.append({
            'id': ext.id,
            'approval_number': ext.approval_number,
            'date': ext.created_at.strftime('%d.%m.%Y') if ext.created_at else '',
            'status': ext.status,
            'sessions': ext.approved_sessions or ext.requested_sessions,
        })
    return jsonify({'extensions': result})
