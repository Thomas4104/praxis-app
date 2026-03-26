"""Routen fuer Behandlungsplan und Serien-Verwaltung"""
import json
from datetime import datetime, date
from flask import render_template, request, jsonify, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from models import (db, TreatmentSeries, TreatmentSeriesTemplate, Appointment,
                    Patient, Employee, Doctor, Location, InsuranceProvider,
                    TherapyGoal, Milestone, Measurement, HealingPhase,
                    SoapNoteHistory, AppointmentTariffPosition)
from blueprints.treatment import treatment_bp
from sqlalchemy import func as sa_func
from sqlalchemy.orm import joinedload
from utils.auth import check_org, get_org_id
from utils.permissions import require_permission
from services.audit_service import log_action


# ============================================================
# Serien-Uebersicht
# ============================================================

@treatment_bp.route('/')
@login_required
@require_permission('treatment.view')
def index():
    """Serien-Uebersicht mit Filtern"""
    return render_template('treatment/serien.html')


@treatment_bp.route('/api/serien')
@login_required
@require_permission('treatment.view')
def api_serien():
    """API: Serien auflisten mit Filtern"""
    org_id = get_org_id()
    status = request.args.get('status', '')
    therapeut_id = request.args.get('therapeut_id', '', type=str)
    patient_id = request.args.get('patient_id', '', type=str)
    standort_id = request.args.get('standort_id', '', type=str)
    suche = request.args.get('suche', '').strip()

    # Nur Serien von Patienten der eigenen Organisation
    query = TreatmentSeries.query.filter(
        TreatmentSeries.patient_id.in_(
            db.session.query(Patient.id).filter_by(organization_id=org_id)
        )
    )

    if status:
        query = query.filter(TreatmentSeries.status == status)
    if therapeut_id:
        query = query.filter(TreatmentSeries.therapist_id == int(therapeut_id))
    if patient_id:
        query = query.filter(TreatmentSeries.patient_id == int(patient_id))
    if standort_id:
        query = query.filter(TreatmentSeries.location_id == int(standort_id))
    if suche:
        # Suche in Patient-Name oder Diagnosecode
        query = query.join(Patient).filter(
            db.or_(
                Patient.first_name.ilike(f'%{suche}%'),
                Patient.last_name.ilike(f'%{suche}%'),
                TreatmentSeries.diagnosis_code.ilike(f'%{suche}%'),
                TreatmentSeries.diagnosis_text.ilike(f'%{suche}%')
            )
        )

    query = query.order_by(TreatmentSeries.created_at.desc())

    # Pagination fuer API
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 200, type=int), 200)
    serien = query.options(
        joinedload(TreatmentSeries.template),
        joinedload(TreatmentSeries.patient),
        joinedload(TreatmentSeries.therapist).joinedload(Employee.user)
    ).limit(per_page).offset((page - 1) * per_page).all()

    # Batch-Queries fuer Termin-Zaehlung (statt N+1)
    if serien:
        serie_ids = [s.id for s in serien]
        total_counts = dict(
            db.session.query(
                Appointment.series_id,
                sa_func.count(Appointment.id)
            ).filter(
                Appointment.series_id.in_(serie_ids)
            ).group_by(Appointment.series_id).all()
        )
        completed_counts = dict(
            db.session.query(
                Appointment.series_id,
                sa_func.count(Appointment.id)
            ).filter(
                Appointment.series_id.in_(serie_ids),
                Appointment.status == 'completed'
            ).group_by(Appointment.series_id).all()
        )
    else:
        total_counts = {}
        completed_counts = {}

    ergebnis = []
    for s in serien:
        template_name = s.template.name if s.template else '-'
        therapeut_name = ''
        if s.therapist and s.therapist.user:
            therapeut_name = f'{s.therapist.user.first_name} {s.therapist.user.last_name}'
        patient_name = f'{s.patient.first_name} {s.patient.last_name}' if s.patient else '-'

        ergebnis.append({
            'id': s.id,
            'patient_name': patient_name,
            'patient_id': s.patient_id,
            'vorlage': template_name,
            'therapeut': therapeut_name,
            'status': s.status,
            'fortschritt_aktuell': completed_counts.get(s.id, 0),
            'fortschritt_total': total_counts.get(s.id, 0),
            'diagnose_code': s.diagnosis_code or '',
            'diagnose_text': s.diagnosis_text or '',
            'erstellt': s.created_at.strftime('%d.%m.%Y') if s.created_at else ''
        })

    return jsonify(ergebnis)


# ============================================================
# Serie-Detail
# ============================================================

@treatment_bp.route('/serie/<int:serie_id>')
@login_required
@require_permission('treatment.view')
def serie_detail(serie_id):
    """Serie-Detail mit Drei-Spalten-Layout"""
    org_id = get_org_id()
    serie = TreatmentSeries.query.get_or_404(serie_id)
    check_org(serie.patient)
    termine = Appointment.query.filter_by(series_id=serie_id).order_by(Appointment.start_time).all()

    therapeuten = Employee.query.filter_by(organization_id=org_id, is_active=True).all()
    standorte = Location.query.filter_by(organization_id=org_id).all()

    return render_template('treatment/serie_detail.html',
                           serie=serie, termine=termine,
                           therapeuten=therapeuten, standorte=standorte)


@treatment_bp.route('/api/serie/<int:serie_id>/termine')
@login_required
def api_serie_termine(serie_id):
    """API: Termine einer Serie"""
    serie = TreatmentSeries.query.get_or_404(serie_id)
    check_org(serie.patient)
    termine = Appointment.query.filter_by(series_id=serie_id).order_by(Appointment.start_time).all()

    # Gesamtanzahl aus Template
    serie_total = serie.template.num_appointments if serie.template else len(termine)

    ergebnis = []
    termin_nr = 0
    for t in termine:
        is_t0 = t.is_termin_0 or False
        if not is_t0:
            termin_nr += 1
        ergebnis.append({
            'id': t.id,
            'datum': t.start_time.strftime('%d.%m.%Y'),
            'uhrzeit': t.start_time.strftime('%H:%M'),
            'end_zeit': t.end_time.strftime('%H:%M'),
            'status': t.status,
            'therapeut': f'{t.employee.user.first_name} {t.employee.user.last_name}' if t.employee and t.employee.user else '-',
            'raum': t.resource.name if t.resource else '-',
            'hat_soap': bool(t.soap_subjective or t.soap_objective or t.soap_assessment or t.soap_plan),
            'hat_notizen': bool(t.notes),
            'series_number': t.series_number or (termin_nr if not is_t0 else 0),
            'is_termin_0': is_t0,
            'charge_despite_cancel': t.charge_despite_cancel or False,
            'cancellation_reason': t.cancellation_reason or '',
            'is_documented': bool(t.soap_subjective or t.soap_objective or t.soap_assessment or t.soap_plan),
        })

    return jsonify({'termine': ergebnis, 'serie_total': serie_total})


@treatment_bp.route('/api/termin/<int:termin_id>')
@login_required
def api_termin_detail(termin_id):
    """API: Termin-Details inkl. SOAP-Notes"""
    t = Appointment.query.get_or_404(termin_id)
    check_org(t.patient)

    return jsonify({
        'id': t.id,
        'datum': t.start_time.strftime('%d.%m.%Y'),
        'uhrzeit': t.start_time.strftime('%H:%M'),
        'end_zeit': t.end_time.strftime('%H:%M'),
        'status': t.status,
        'therapeut': f'{t.employee.user.first_name} {t.employee.user.last_name}' if t.employee and t.employee.user else '-',
        'raum': t.resource.name if t.resource else '-',
        'titel': t.title or '',
        'soap_subjective': t.soap_subjective or '',
        'soap_objective': t.soap_objective or '',
        'soap_assessment': t.soap_assessment or '',
        'soap_plan': t.soap_plan or '',
        'notes': t.notes or '',
        'series_number': t.series_number,
        'is_termin_0': t.is_termin_0 or False,
        'charge_despite_cancel': t.charge_despite_cancel or False,
        'cancellation_reason': t.cancellation_reason or '',
        'tariff_positions_count': t.tariff_positions.count() if hasattr(t, 'tariff_positions') else 0,
    })


@treatment_bp.route('/api/termin/<int:termin_id>/soap', methods=['POST'])
@login_required
@require_permission('treatment.edit_soap')
def api_soap_speichern(termin_id):
    """API: SOAP-Notes speichern mit Versionierung"""
    t = Appointment.query.get_or_404(termin_id)
    check_org(t.patient)
    data = request.get_json()

    # 1. Alten Zustand sichern
    soap_fields = ['soap_subjective', 'soap_objective', 'soap_assessment', 'soap_plan']
    old_values = {f: getattr(t, f, None) for f in soap_fields}
    new_values = {f: data.get(f, old_values[f]) for f in soap_fields}

    # Pruefen ob sich SOAP-Felder geaendert haben
    has_soap_changes = any(old_values[k] != new_values[k] for k in soap_fields)

    if has_soap_changes:
        # 2. Aktuelle Version in History speichern (VOR der Aenderung)
        current_version = t.soap_history.count() + 1
        history = SoapNoteHistory(
            appointment_id=t.id,
            version=current_version,
            soap_subjective=old_values['soap_subjective'],
            soap_objective=old_values['soap_objective'],
            soap_assessment=old_values['soap_assessment'],
            soap_plan=old_values['soap_plan'],
            changed_by_id=current_user.id,
            change_reason=data.get('change_reason', ''),
        )
        history.compute_hash()
        db.session.add(history)

        # 3. Neue SOAP-Werte setzen
        for key, value in new_values.items():
            setattr(t, key, value)

        # 4. SOAP-Timestamp aktualisieren
        t.soap_updated_at = datetime.utcnow()
        t.soap_updated_by_id = current_user.id

        # 5. Audit-Log mit Diff
        changes = {}
        for key in soap_fields:
            if old_values[key] != new_values[key]:
                old_str = old_values[key] or ''
                new_str = new_values[key] or ''
                changes[key] = {
                    'old': old_str[:100] + '...' if len(old_str) > 100 else old_str,
                    'new': new_str[:100] + '...' if len(new_str) > 100 else new_str,
                }
        log_action('update', 'soap_notes', t.id, changes=changes)

    # Notes-Feld separat behandeln (kein Teil der SOAP-Versionierung)
    if 'notes' in data:
        old_notes = t.notes or ''
        new_notes = data['notes']
        if old_notes != new_notes:
            t.notes = new_notes
            log_action('update', 'appointment_notes', t.id, changes={
                'notes': {'old': old_notes[:100], 'new': new_notes[:100]}
            })

    db.session.commit()
    return jsonify({'success': True, 'message': 'Gespeichert'})


@treatment_bp.route('/api/termin/<int:termin_id>/soap/history')
@login_required
def api_soap_history(termin_id):
    """Gibt die SOAP-Noten-History fuer einen Termin zurueck."""
    appointment = Appointment.query.get_or_404(termin_id)
    check_org(appointment.patient)

    history = SoapNoteHistory.query.filter_by(
        appointment_id=termin_id
    ).order_by(SoapNoteHistory.version.desc()).all()

    return jsonify([{
        'version': h.version,
        'soap_subjective': h.soap_subjective,
        'soap_objective': h.soap_objective,
        'soap_assessment': h.soap_assessment,
        'soap_plan': h.soap_plan,
        'changed_by': f'{h.changed_by.first_name} {h.changed_by.last_name}' if h.changed_by else 'Unbekannt',
        'changed_at': h.changed_at.strftime('%d.%m.%Y %H:%M'),
        'change_reason': h.change_reason,
        'content_hash': h.content_hash,
    } for h in history])


@treatment_bp.route('/api/serie/<int:serie_id>/status', methods=['POST'])
@login_required
@require_permission('treatment.close_series')
def api_serie_status(serie_id):
    """API: Serie-Status aendern (abschliessen/abbrechen)"""
    serie = TreatmentSeries.query.get_or_404(serie_id)
    check_org(serie.patient)
    data = request.get_json()
    neuer_status = data.get('status')

    if neuer_status not in ('completed', 'cancelled'):
        return jsonify({'error': 'Ungueltiger Status'}), 400

    old_status = serie.status
    serie.status = neuer_status
    if neuer_status == 'completed':
        serie.completed_at = datetime.utcnow()

    log_action('update', 'treatment_series', serie.id, changes={'status': {'old': old_status, 'new': neuer_status}})
    db.session.commit()
    return jsonify({'success': True, 'status': neuer_status})


# ============================================================
# Behandlungsplan
# ============================================================

@treatment_bp.route('/plan/<int:patient_id>')
@login_required
@require_permission('treatment.view')
def treatment_plan(patient_id):
    """Behandlungsplan fuer einen Patienten"""
    patient = Patient.query.get_or_404(patient_id)
    check_org(patient)
    serien = TreatmentSeries.query.filter_by(patient_id=patient_id).order_by(TreatmentSeries.created_at.desc()).all()
    ziele = TherapyGoal.query.filter_by(patient_id=patient_id).order_by(TherapyGoal.created_at).all()
    meilensteine = Milestone.query.filter_by(patient_id=patient_id).order_by(Milestone.sort_order).all()
    messungen = Measurement.query.filter_by(patient_id=patient_id).order_by(Measurement.measured_at.desc()).all()

    return render_template('treatment/treatment_plan.html',
                           patient=patient, serien=serien, ziele=ziele,
                           meilensteine=meilensteine, messungen=messungen)


# ============================================================
# Therapieziele API
# ============================================================

@treatment_bp.route('/api/ziele/<int:patient_id>')
@login_required
def api_ziele(patient_id):
    """API: Therapieziele eines Patienten"""
    patient = Patient.query.get_or_404(patient_id)
    check_org(patient)
    ziele = TherapyGoal.query.filter_by(patient_id=patient_id).order_by(TherapyGoal.created_at).all()

    return jsonify([{
        'id': z.id,
        'series_id': z.series_id,
        'beschreibung': z.description,
        'zielwert': z.target_value or '',
        'aktueller_wert': z.current_value or '',
        'erreichung': z.achievement_percent,
        'status': z.status
    } for z in ziele])


@treatment_bp.route('/api/ziel', methods=['POST'])
@login_required
def api_ziel_erstellen():
    """API: Neues Therapieziel erstellen"""
    data = request.get_json()
    patient = Patient.query.get_or_404(data['patient_id'])
    check_org(patient)
    ziel = TherapyGoal(
        series_id=data.get('series_id'),
        patient_id=data['patient_id'],
        description=data['beschreibung'],
        target_value=data.get('zielwert', ''),
        current_value=data.get('aktueller_wert', ''),
        achievement_percent=data.get('erreichung', 0),
        status=data.get('status', 'open')
    )
    db.session.add(ziel)
    db.session.commit()
    return jsonify({'success': True, 'id': ziel.id})


@treatment_bp.route('/api/ziel/<int:ziel_id>', methods=['PUT'])
@login_required
def api_ziel_aktualisieren(ziel_id):
    """API: Therapieziel aktualisieren"""
    ziel = TherapyGoal.query.get_or_404(ziel_id)
    check_org(ziel.patient)
    data = request.get_json()

    if 'beschreibung' in data:
        ziel.description = data['beschreibung']
    if 'zielwert' in data:
        ziel.target_value = data['zielwert']
    if 'aktueller_wert' in data:
        ziel.current_value = data['aktueller_wert']
    if 'erreichung' in data:
        ziel.achievement_percent = data['erreichung']
    if 'status' in data:
        ziel.status = data['status']

    db.session.commit()
    return jsonify({'success': True})


@treatment_bp.route('/api/ziel/<int:ziel_id>', methods=['DELETE'])
@login_required
def api_ziel_loeschen(ziel_id):
    """API: Therapieziel loeschen"""
    ziel = TherapyGoal.query.get_or_404(ziel_id)
    check_org(ziel.patient)
    db.session.delete(ziel)
    db.session.commit()
    return jsonify({'success': True})


# ============================================================
# Meilensteine API
# ============================================================

@treatment_bp.route('/api/meilensteine/<int:patient_id>')
@login_required
def api_meilensteine(patient_id):
    """API: Meilensteine eines Patienten"""
    patient = Patient.query.get_or_404(patient_id)
    check_org(patient)
    meilensteine = Milestone.query.filter_by(patient_id=patient_id).order_by(Milestone.sort_order).all()

    return jsonify([{
        'id': m.id,
        'series_id': m.series_id,
        'name': m.name,
        'beschreibung': m.description or '',
        'zieldatum': m.target_date.strftime('%d.%m.%Y') if m.target_date else '',
        'zieldatum_iso': m.target_date.isoformat() if m.target_date else '',
        'erreicht_datum': m.achieved_date.strftime('%d.%m.%Y') if m.achieved_date else '',
        'kriterien': m.criteria or '',
        'status': m.status,
        'sort_order': m.sort_order
    } for m in meilensteine])


@treatment_bp.route('/api/meilenstein', methods=['POST'])
@login_required
def api_meilenstein_erstellen():
    """API: Neuen Meilenstein erstellen"""
    data = request.get_json()
    patient = Patient.query.get_or_404(data['patient_id'])
    check_org(patient)
    m = Milestone(
        series_id=data.get('series_id'),
        patient_id=data['patient_id'],
        name=data['name'],
        description=data.get('beschreibung', ''),
        target_date=datetime.strptime(data['zieldatum'], '%Y-%m-%d').date() if data.get('zieldatum') else None,
        criteria=data.get('kriterien', ''),
        status=data.get('status', 'open'),
        sort_order=data.get('sort_order', 0)
    )
    db.session.add(m)
    db.session.commit()
    return jsonify({'success': True, 'id': m.id})


@treatment_bp.route('/api/meilenstein/<int:meilenstein_id>', methods=['PUT'])
@login_required
def api_meilenstein_aktualisieren(meilenstein_id):
    """API: Meilenstein aktualisieren"""
    m = Milestone.query.get_or_404(meilenstein_id)
    check_org(m.patient)
    data = request.get_json()

    if 'name' in data:
        m.name = data['name']
    if 'beschreibung' in data:
        m.description = data['beschreibung']
    if 'zieldatum' in data:
        m.target_date = datetime.strptime(data['zieldatum'], '%Y-%m-%d').date() if data['zieldatum'] else None
    if 'kriterien' in data:
        m.criteria = data['kriterien']
    if 'status' in data:
        m.status = data['status']
        if data['status'] == 'achieved':
            m.achieved_date = date.today()

    db.session.commit()
    return jsonify({'success': True})


@treatment_bp.route('/api/meilenstein/<int:meilenstein_id>', methods=['DELETE'])
@login_required
def api_meilenstein_loeschen(meilenstein_id):
    """API: Meilenstein loeschen"""
    m = Milestone.query.get_or_404(meilenstein_id)
    check_org(m.patient)
    db.session.delete(m)
    db.session.commit()
    return jsonify({'success': True})


# ============================================================
# Messungen API
# ============================================================

@treatment_bp.route('/api/messungen/<int:patient_id>')
@login_required
def api_messungen(patient_id):
    """API: Messungen eines Patienten"""
    patient = Patient.query.get_or_404(patient_id)
    check_org(patient)
    typ = request.args.get('typ', '')
    query = Measurement.query.filter_by(patient_id=patient_id)
    if typ:
        query = query.filter(Measurement.measurement_type == typ)

    messungen = query.order_by(Measurement.measured_at).all()

    return jsonify([{
        'id': m.id,
        'series_id': m.series_id,
        'typ': m.measurement_type,
        'name': m.name or m.measurement_type.upper(),
        'werte': json.loads(m.value_json) if m.value_json else {},
        'einheit': m.unit or '',
        'datum': m.measured_at.strftime('%d.%m.%Y'),
        'datum_iso': m.measured_at.isoformat(),
        'gemessen_von': f'{m.measured_by.user.first_name} {m.measured_by.user.last_name}' if m.measured_by and m.measured_by.user else '-',
        'notizen': m.notes or ''
    } for m in messungen])


@treatment_bp.route('/api/messung', methods=['POST'])
@login_required
def api_messung_erstellen():
    """API: Neue Messung erfassen"""
    data = request.get_json()
    patient = Patient.query.get_or_404(data['patient_id'])
    check_org(patient)

    # Messwert als JSON
    werte = data.get('werte', {})
    if 'wert' in data and not werte:
        werte = {'value': data['wert']}

    emp = None
    if current_user.employee:
        emp = current_user.employee.id

    m = Measurement(
        patient_id=data['patient_id'],
        series_id=data.get('series_id'),
        appointment_id=data.get('appointment_id'),
        measurement_type=data['typ'],
        name=data.get('name', ''),
        value_json=json.dumps(werte),
        unit=data.get('einheit', ''),
        measured_at=datetime.fromisoformat(data['datum']) if data.get('datum') else datetime.utcnow(),
        measured_by_id=data.get('gemessen_von_id', emp),
        notes=data.get('notizen', '')
    )
    db.session.add(m)
    db.session.commit()
    return jsonify({'success': True, 'id': m.id})


# ============================================================
# Heilungsphasen API
# ============================================================

@treatment_bp.route('/api/heilungsphasen/<int:serie_id>')
@login_required
def api_heilungsphasen(serie_id):
    """API: Heilungsphasen einer Serie"""
    serie = TreatmentSeries.query.get_or_404(serie_id)
    check_org(serie.patient)
    phasen = HealingPhase.query.filter_by(series_id=serie_id).order_by(HealingPhase.start_date).all()

    return jsonify([{
        'id': p.id,
        'phase_type': p.phase_type,
        'start_date': p.start_date.isoformat() if p.start_date else '',
        'end_date': p.end_date.isoformat() if p.end_date else '',
        'notizen': p.notes or ''
    } for p in phasen])


@treatment_bp.route('/api/heilungsphase', methods=['POST'])
@login_required
def api_heilungsphase_setzen():
    """API: Heilungsphase setzen/aendern"""
    data = request.get_json()
    serie_id = data['serie_id']
    phase_type = data['phase_type']

    # IDOR-Schutz: Pruefen ob Serie zur Organisation gehoert
    serie_check = TreatmentSeries.query.get_or_404(serie_id)
    check_org(serie_check.patient)

    # Bestehende aktive Phase abschliessen (Phase ohne end_date)
    aktive_phasen = HealingPhase.query.filter_by(series_id=serie_id, end_date=None).all()
    for p in aktive_phasen:
        p.end_date = date.today()

    # Neue Phase anlegen
    neue_phase = HealingPhase(
        series_id=serie_id,
        phase_type=phase_type,
        start_date=date.today(),
        notes=data.get('notizen', '')
    )
    db.session.add(neue_phase)

    # Auch healing_phase auf der Serie aktualisieren
    serie = TreatmentSeries.query.get(serie_id)
    if serie:
        serie.healing_phase = phase_type

    db.session.commit()
    return jsonify({'success': True, 'id': neue_phase.id})


# ============================================================
# Hilfsdaten API
# ============================================================

@treatment_bp.route('/api/filter-optionen')
@login_required
def api_filter_optionen():
    """API: Optionen fuer Filter (Therapeuten, Standorte)"""
    org_id = get_org_id()
    therapeuten = Employee.query.filter_by(organization_id=org_id, is_active=True).all()
    standorte = Location.query.filter_by(organization_id=org_id).all()

    return jsonify({
        'therapeuten': [
            {'id': e.id, 'name': f'{e.user.first_name} {e.user.last_name}' if e.user else f'MA {e.id}'}
            for e in therapeuten if e.user
        ],
        'standorte': [
            {'id': s.id, 'name': s.name}
            for s in standorte
        ]
    })


# ============================================================================
# Tarmed-Positionen pro Termin
# ============================================================================

@treatment_bp.route('/api/termin/<int:termin_id>/tariff-positions')
@login_required
def api_tariff_positions(termin_id):
    """Tarmed-Positionen eines Termins laden"""
    appointment = Appointment.query.get_or_404(termin_id)
    check_org(appointment)

    positions = AppointmentTariffPosition.query.filter_by(
        appointment_id=termin_id
    ).order_by(AppointmentTariffPosition.position).all()

    return jsonify([{
        'id': p.id,
        'tariff_type': p.tariff_type,
        'tariff_code': p.tariff_code,
        'description': p.description,
        'quantity': float(p.quantity or 1),
        'tax_points': float(p.tax_points),
        'tax_point_value': float(p.tax_point_value),
        'amount': float(p.amount),
        'vat_rate': float(p.vat_rate or 0),
        'vat_amount': float(p.vat_amount or 0),
        'position': p.position,
    } for p in positions])


@treatment_bp.route('/api/termin/<int:termin_id>/tariff-positions', methods=['POST'])
@login_required
def api_tariff_position_create(termin_id):
    """Tarmed-Position zu Termin hinzufuegen"""
    appointment = Appointment.query.get_or_404(termin_id)
    check_org(appointment)

    data = request.get_json()
    if not data:
        return jsonify({'error': 'Keine Daten erhalten'}), 400

    # Validierung
    required = ['tariff_type', 'tariff_code', 'tax_points', 'tax_point_value']
    for field in required:
        if field not in data:
            return jsonify({'error': f'Pflichtfeld fehlt: {field}'}), 400

    quantity = float(data.get('quantity', 1))
    tax_points = float(data['tax_points'])
    tp_value = float(data['tax_point_value'])
    amount = round(quantity * tax_points * tp_value, 2)
    vat_rate = float(data.get('vat_rate', 0))
    vat_amount = round(amount * vat_rate / 100, 2)

    # Naechste Position bestimmen
    max_pos = db.session.query(db.func.max(AppointmentTariffPosition.position)).filter_by(
        appointment_id=termin_id
    ).scalar() or 0

    position = AppointmentTariffPosition(
        appointment_id=termin_id,
        tariff_type=data['tariff_type'],
        tariff_code=data['tariff_code'],
        description=data.get('description', ''),
        quantity=quantity,
        tax_points=tax_points,
        tax_point_value=tp_value,
        amount=amount,
        vat_rate=vat_rate,
        vat_amount=vat_amount,
        position=max_pos + 1,
        created_by_id=current_user.id,
    )
    db.session.add(position)
    db.session.commit()

    log_action('create', 'tariff_position', position.id, changes={
        'appointment_id': {'new': termin_id},
        'tariff_code': {'new': data['tariff_code']},
        'amount': {'new': str(amount)},
    })

    return jsonify({
        'id': position.id,
        'amount': float(position.amount),
        'message': 'Tarmed-Position hinzugefuegt'
    }), 201


@treatment_bp.route('/api/tariff-position/<int:position_id>', methods=['PUT'])
@login_required
def api_tariff_position_update(position_id):
    """Tarmed-Position bearbeiten"""
    position = AppointmentTariffPosition.query.get_or_404(position_id)
    # Org-Check ueber Appointment
    check_org(position.appointment)

    data = request.get_json()
    if not data:
        return jsonify({'error': 'Keine Daten erhalten'}), 400

    if 'tariff_type' in data:
        position.tariff_type = data['tariff_type']
    if 'tariff_code' in data:
        position.tariff_code = data['tariff_code']
    if 'description' in data:
        position.description = data['description']
    if 'quantity' in data:
        position.quantity = float(data['quantity'])
    if 'tax_points' in data:
        position.tax_points = float(data['tax_points'])
    if 'tax_point_value' in data:
        position.tax_point_value = float(data['tax_point_value'])
    if 'vat_rate' in data:
        position.vat_rate = float(data['vat_rate'])

    # Betrag neu berechnen
    position.amount = round(float(position.quantity) * float(position.tax_points) * float(position.tax_point_value), 2)
    position.vat_amount = round(float(position.amount) * float(position.vat_rate or 0) / 100, 2)

    db.session.commit()
    return jsonify({'message': 'Position aktualisiert', 'amount': float(position.amount)})


@treatment_bp.route('/api/tariff-position/<int:position_id>', methods=['DELETE'])
@login_required
def api_tariff_position_delete(position_id):
    """Tarmed-Position loeschen"""
    position = AppointmentTariffPosition.query.get_or_404(position_id)
    check_org(position.appointment)

    log_action('delete', 'tariff_position', position_id, changes={
        'appointment_id': {'old': position.appointment_id},
        'tariff_code': {'old': position.tariff_code},
        'amount': {'old': str(position.amount)},
    })

    db.session.delete(position)
    db.session.commit()
    return jsonify({'message': 'Position geloescht'})


# ============================================================
# Behandlungsplan (Cenplex: TreatmentPlan)
# ============================================================

@treatment_bp.route('/plan/create/<int:series_id>', methods=['GET', 'POST'])
@login_required
def create_plan(series_id):
    """Neuen Behandlungsplan fuer eine Serie erstellen"""
    from models import TreatmentSeries, TreatmentPlan, TreatmentPhase, Employee, Contact
    from utils.auth import check_org, get_org_id

    series = TreatmentSeries.query.get_or_404(series_id)
    check_org(series.patient)

    if request.method == 'POST':
        plan = TreatmentPlan(
            organization_id=get_org_id(),
            patient_id=series.patient_id,
            series_id=series_id,
            location_id=series.location_id,
            responsible_id=int(request.form.get('responsible_id')) if request.form.get('responsible_id') else series.therapist_id,
            created_by_id=current_user.employee.id if hasattr(current_user, 'employee') and current_user.employee else None,
            title=request.form.get('title', series.title or ''),
            diagnosis=request.form.get('diagnosis', ''),
            hypothesis=request.form.get('hypothesis', ''),
            affected_side=int(request.form.get('affected_side', 0)),
            icd_codes_json=request.form.get('icd_codes', ''),
            start_date=datetime.strptime(request.form['start_date'], '%Y-%m-%d').date() if request.form.get('start_date') else datetime.now().date()
        )
        db.session.add(plan)
        db.session.flush()

        # Phasen erstellen falls angegeben
        phase_titles = request.form.getlist('phase_title[]')
        phase_durations = request.form.getlist('phase_duration[]')
        for i, title in enumerate(phase_titles):
            if title.strip():
                phase = TreatmentPhase(
                    treatment_plan_id=plan.id,
                    title=title,
                    position=i + 1,
                    default_duration_days=int(phase_durations[i]) if i < len(phase_durations) and phase_durations[i] else None
                )
                db.session.add(phase)

        db.session.commit()
        flash('Behandlungsplan erstellt.', 'success')
        return redirect(url_for('treatment.plan_detail', plan_id=plan.id))

    employees = Employee.query.filter_by(organization_id=get_org_id(), is_active=True).all()
    doctors = Contact.query.filter_by(organization_id=get_org_id(), contact_type='doctor').all()

    return render_template('treatment/plan_form.html',
                          series=series,
                          patient=series.patient,
                          employees=employees,
                          doctors=doctors)


@treatment_bp.route('/plan/detail/<int:plan_id>')
@login_required
def plan_detail(plan_id):
    """Behandlungsplan-Detail mit Phasen und Assessments"""
    from models import TreatmentPlan, TreatmentPhase, Assessment, AssessmentResult, TherapyGoal, Measurement
    from utils.auth import check_org

    plan = TreatmentPlan.query.get_or_404(plan_id)
    check_org(plan)

    phases = TreatmentPhase.query.filter_by(treatment_plan_id=plan_id).order_by(TreatmentPhase.position).all()
    assessments = Assessment.query.filter_by(treatment_plan_id=plan_id).all()
    goals = TherapyGoal.query.filter_by(series_id=plan.series_id).order_by(TherapyGoal.created_at).all() if plan.series_id else []
    measurements = Measurement.query.filter_by(series_id=plan.series_id).order_by(Measurement.measured_at.desc()).all() if plan.series_id else []

    # Phasen-Fortschritt berechnen
    total_phases = len(phases)
    completed_phases = sum(1 for p in phases if p.end_date and p.finished_by_id)
    phase_progress = int(completed_phases / total_phases * 100) if total_phases > 0 else 0

    return render_template('treatment/plan_detail.html',
                          plan=plan,
                          phases=phases,
                          assessments=assessments,
                          goals=goals,
                          measurements=measurements,
                          phase_progress=phase_progress)


@treatment_bp.route('/plan/<int:plan_id>/phase', methods=['POST'])
@login_required
def add_phase(plan_id):
    """Phase zu Behandlungsplan hinzufuegen"""
    from models import TreatmentPlan, TreatmentPhase
    from utils.auth import check_org

    plan = TreatmentPlan.query.get_or_404(plan_id)
    check_org(plan)

    max_pos = db.session.query(db.func.max(TreatmentPhase.position)).filter_by(treatment_plan_id=plan_id).scalar() or 0

    phase = TreatmentPhase(
        treatment_plan_id=plan_id,
        title=request.form.get('title', 'Neue Phase'),
        position=max_pos + 1,
        default_duration_days=int(request.form.get('duration_days', 14)),
        start_date=datetime.strptime(request.form['start_date'], '%Y-%m-%d').date() if request.form.get('start_date') else None
    )
    db.session.add(phase)
    db.session.commit()

    flash('Phase hinzugefuegt.', 'success')
    return redirect(url_for('treatment.plan_detail', plan_id=plan_id))


@treatment_bp.route('/plan/<int:plan_id>/phase/<int:phase_id>/complete', methods=['POST'])
@login_required
def complete_phase(plan_id, phase_id):
    """Phase als abgeschlossen markieren"""
    from models import TreatmentPhase, TreatmentPlan
    from utils.auth import check_org

    plan = TreatmentPlan.query.get_or_404(plan_id)
    if plan.organization_id != current_user.organization_id:
        abort(403)
    phase = TreatmentPhase.query.get_or_404(phase_id)
    if phase.treatment_plan_id != plan_id:
        abort(404)
    phase.end_date = datetime.now().date()
    phase.finished_by_id = current_user.employee.id if hasattr(current_user, 'employee') and current_user.employee else None
    db.session.commit()

    flash('Phase abgeschlossen.', 'success')
    return redirect(url_for('treatment.plan_detail', plan_id=plan_id))


@treatment_bp.route('/plan/<int:plan_id>/assessment', methods=['POST'])
@login_required
def add_assessment(plan_id):
    """Assessment zu Behandlungsplan hinzufuegen"""
    from models import TreatmentPlan, Assessment
    from utils.auth import check_org

    plan = TreatmentPlan.query.get_or_404(plan_id)
    check_org(plan)

    assessment = Assessment(
        treatment_plan_id=plan_id,
        title=request.form.get('title', ''),
        assessment_type=int(request.form.get('assessment_type', 0)),
        created_by_id=current_user.employee.id if hasattr(current_user, 'employee') and current_user.employee else None
    )
    db.session.add(assessment)
    db.session.commit()

    flash('Assessment hinzugefuegt.', 'success')
    return redirect(url_for('treatment.plan_detail', plan_id=plan_id))


@treatment_bp.route('/plan/<int:plan_id>/assessment/<int:assessment_id>/result', methods=['POST'])
@login_required
def add_assessment_result(plan_id, assessment_id):
    """Ergebnis zu Assessment hinzufuegen"""
    from models import AssessmentResult, TreatmentPlan
    from utils.auth import check_org

    plan = TreatmentPlan.query.get_or_404(plan_id)
    if plan.organization_id != current_user.organization_id:
        abort(403)

    result = AssessmentResult(
        assessment_id=assessment_id,
        text_value=request.form.get('text_value', ''),
        calculated_value=float(request.form.get('calculated_value')) if request.form.get('calculated_value') else None,
        created_by_id=current_user.employee.id if hasattr(current_user, 'employee') and current_user.employee else None
    )
    db.session.add(result)
    db.session.commit()

    flash('Ergebnis erfasst.', 'success')
    return redirect(url_for('treatment.plan_detail', plan_id=plan_id))


@treatment_bp.route('/api/tariff-codes')
@login_required
def api_tariff_codes():
    """Gaengige Tarmed-Tarifziffern zurueckgeben (fuer Autocomplete)"""
    codes = [
        {'type': 'Tarif 590', 'code': '7301', 'description': 'Physiotherapie Einzelbehandlung', 'default_tp': 48},
        {'type': 'Tarif 590', 'code': '7311', 'description': 'Physiotherapie Gruppenbehandlung', 'default_tp': 28},
        {'type': 'Tarif 590', 'code': '7320', 'description': 'Physiotherapie Erstbefunderhebung', 'default_tp': 65},
        {'type': 'Tarif 590', 'code': '7330', 'description': 'Manuelle Lymphdrainage', 'default_tp': 60},
        {'type': 'Tarif 590', 'code': '7340', 'description': 'Atemtherapie', 'default_tp': 48},
        {'type': 'Tarif 590', 'code': '7350', 'description': 'Medizinische Trainingstherapie', 'default_tp': 24},
        {'type': 'Tarif 312', 'code': '5901', 'description': 'Komplementaermedizin Einzelbehandlung', 'default_tp': 72},
        {'type': 'TarReha', 'code': '9501', 'description': 'Ambulante Rehabilitation', 'default_tp': 48},
    ]
    q = request.args.get('q', '').lower()
    if q:
        codes = [c for c in codes if q in c['code'] or q in c['description'].lower()]
    return jsonify(codes)


# ============================================================================
# Klinische Befunde
# ============================================================================

@treatment_bp.route('/befunde/<int:patient_id>')
@login_required
def befunde(patient_id):
    """Befund-Uebersicht fuer einen Patienten"""
    patient = Patient.query.get_or_404(patient_id)
    check_org(patient)
    return render_template('treatment/befunde.html', patient=patient)


@treatment_bp.route('/api/befund-vorlagen')
@login_required
def api_befund_vorlagen():
    """Verfuegbare Befund-Vorlagen laden"""
    from models import FindingTemplate
    org_id = current_user.organization_id

    templates = FindingTemplate.query.filter_by(
        organization_id=org_id,
        is_active=True
    ).order_by(FindingTemplate.sort_order, FindingTemplate.name).all()

    return jsonify([{
        'id': t.id,
        'name': t.name,
        'template_type': t.template_type,
        'location_id': t.location_id,
        'location_name': t.location.name if t.location else 'Alle Standorte',
        'fields': json.loads(t.fields_json) if t.fields_json else [],
        'is_default': t.is_default,
    } for t in templates])


@treatment_bp.route('/api/befunde/<int:patient_id>')
@login_required
def api_befunde(patient_id):
    """Alle Befunde eines Patienten laden"""
    from models import ClinicalFinding
    patient = Patient.query.get_or_404(patient_id)
    check_org(patient)

    findings = ClinicalFinding.query.filter_by(
        patient_id=patient_id
    ).order_by(ClinicalFinding.created_at.desc()).all()

    return jsonify([{
        'id': f.id,
        'finding_type': f.finding_type,
        'template_name': f.template.name if f.template else 'Ohne Vorlage',
        'series_id': f.series_id,
        'data': json.loads(f.data_json) if f.data_json else {},
        'created_by': f'{f.created_by.first_name} {f.created_by.last_name}' if f.created_by else '',
        'created_at': f.created_at.strftime('%d.%m.%Y %H:%M') if f.created_at else '',
        'updated_at': f.updated_at.strftime('%d.%m.%Y %H:%M') if f.updated_at else '',
    } for f in findings])


@treatment_bp.route('/api/befund', methods=['POST'])
@login_required
def api_befund_erstellen():
    """Neuen klinischen Befund erstellen"""
    from models import ClinicalFinding

    data = request.get_json()
    if not data:
        return jsonify({'error': 'Keine Daten erhalten'}), 400

    patient_id = data.get('patient_id')
    if not patient_id:
        return jsonify({'error': 'patient_id erforderlich'}), 400

    patient = Patient.query.get_or_404(patient_id)
    check_org(patient)

    finding = ClinicalFinding(
        patient_id=patient_id,
        series_id=data.get('series_id'),
        appointment_id=data.get('appointment_id'),
        template_id=data.get('template_id'),
        finding_type=data.get('finding_type', 'erstbefund'),
        data_json=json.dumps(data.get('data', {}), ensure_ascii=False),
        created_by_id=current_user.id,
    )
    db.session.add(finding)
    db.session.commit()

    log_action('create', 'clinical_finding', finding.id)

    return jsonify({'id': finding.id, 'message': 'Befund erstellt'}), 201


@treatment_bp.route('/api/befund/<int:befund_id>', methods=['PUT'])
@login_required
def api_befund_aktualisieren(befund_id):
    """Befund bearbeiten"""
    from models import ClinicalFinding

    finding = ClinicalFinding.query.get_or_404(befund_id)
    check_org(finding.patient)

    data = request.get_json()
    if data and 'data' in data:
        finding.data_json = json.dumps(data['data'], ensure_ascii=False)
    if data and 'finding_type' in data:
        finding.finding_type = data['finding_type']

    db.session.commit()

    log_action('update', 'clinical_finding', finding.id)

    return jsonify({'message': 'Befund aktualisiert'})


@treatment_bp.route('/api/befund/<int:befund_id>', methods=['DELETE'])
@login_required
def api_befund_loeschen(befund_id):
    """Befund loeschen"""
    from models import ClinicalFinding
    finding = ClinicalFinding.query.get_or_404(befund_id)
    check_org(finding.patient)

    log_action('delete', 'clinical_finding', befund_id)

    db.session.delete(finding)
    db.session.commit()
    return jsonify({'message': 'Befund geloescht'})


# ============================================================================
# Behandlungsplan-Vorlagen
# ============================================================================

@treatment_bp.route('/api/plan-vorlagen')
@login_required
def api_plan_vorlagen():
    """Behandlungsplan-Vorlagen laden"""
    from models import TreatmentPlanTemplate
    import json

    org_id = current_user.organization_id
    insurance_type = request.args.get('insurance_type')

    query = TreatmentPlanTemplate.query.filter_by(
        organization_id=org_id,
        is_active=True
    )
    if insurance_type:
        query = query.filter(
            db.or_(
                TreatmentPlanTemplate.insurance_type == insurance_type,
                TreatmentPlanTemplate.insurance_type.is_(None)
            )
        )

    templates = query.order_by(TreatmentPlanTemplate.sort_order).all()

    return jsonify([{
        'id': t.id,
        'name': t.name,
        'description': t.description,
        'goals': json.loads(t.goals_json) if t.goals_json else [],
        'measures': json.loads(t.measures_json) if t.measures_json else [],
        'frequency': json.loads(t.frequency_json) if t.frequency_json else {},
        'insurance_type': t.insurance_type,
    } for t in templates])


@treatment_bp.route('/api/iv-status')
@login_required
def api_iv_status():
    """IV-Status-Zusammenfassung"""
    from services.iv_monitoring_service import get_iv_status_summary
    summary = get_iv_status_summary(current_user.organization_id)
    return jsonify(summary)


# ============================================================================
# Arztberichte
# ============================================================================

@treatment_bp.route('/arztbericht/<int:serie_id>')
@login_required
def arztbericht(serie_id):
    """Arztbericht-Vorschau"""
    from services.medical_report_service import generate_report_data
    series = TreatmentSeries.query.get_or_404(serie_id)
    check_org(series.patient)

    data, error = generate_report_data(serie_id)
    if error:
        flash(f'Fehler beim Erstellen des Berichts: {error}', 'error')
        return redirect(url_for('treatment.serie_detail', serie_id=serie_id))

    return render_template('treatment/arztbericht.html', report=data, serie=series)


@treatment_bp.route('/arztbericht/<int:serie_id>/pdf')
@login_required
def arztbericht_pdf(serie_id):
    """Arztbericht als PDF herunterladen"""
    from services.medical_report_service import generate_report_pdf
    series = TreatmentSeries.query.get_or_404(serie_id)
    check_org(series.patient)

    filepath, error = generate_report_pdf(serie_id)
    if error:
        flash(f'Fehler beim PDF-Erstellen: {error}', 'error')
        return redirect(url_for('treatment.arztbericht', serie_id=serie_id))

    import os
    from flask import send_file
    return send_file(filepath, as_attachment=True,
                    download_name=f'Arztbericht_{series.patient.last_name}_{series.patient.first_name}.pdf')
