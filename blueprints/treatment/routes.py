"""Routen fuer Behandlungsplan und Serien-Verwaltung"""
import json
from datetime import datetime, date
from flask import render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from models import (db, TreatmentSeries, TreatmentSeriesTemplate, Appointment,
                    Patient, Employee, Doctor, Location, InsuranceProvider,
                    TherapyGoal, Milestone, Measurement, HealingPhase)
from blueprints.treatment import treatment_bp


# ============================================================
# Serien-Uebersicht
# ============================================================

@treatment_bp.route('/')
@login_required
def index():
    """Serien-Uebersicht mit Filtern"""
    return render_template('treatment/serien.html')


@treatment_bp.route('/api/serien')
@login_required
def api_serien():
    """API: Serien auflisten mit Filtern"""
    status = request.args.get('status', '')
    therapeut_id = request.args.get('therapeut_id', '', type=str)
    patient_id = request.args.get('patient_id', '', type=str)
    standort_id = request.args.get('standort_id', '', type=str)
    suche = request.args.get('suche', '').strip()

    query = TreatmentSeries.query

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
    serien = query.all()

    ergebnis = []
    for s in serien:
        total_termine = s.appointments.count()
        abgeschlossen = s.appointments.filter(Appointment.status == 'completed').count()
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
            'fortschritt_aktuell': abgeschlossen,
            'fortschritt_total': total_termine,
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
def serie_detail(serie_id):
    """Serie-Detail mit Drei-Spalten-Layout"""
    serie = TreatmentSeries.query.get_or_404(serie_id)
    termine = Appointment.query.filter_by(series_id=serie_id).order_by(Appointment.start_time).all()

    therapeuten = Employee.query.filter_by(is_active=True).all()
    standorte = Location.query.all()

    return render_template('treatment/serie_detail.html',
                           serie=serie, termine=termine,
                           therapeuten=therapeuten, standorte=standorte)


@treatment_bp.route('/api/serie/<int:serie_id>/termine')
@login_required
def api_serie_termine(serie_id):
    """API: Termine einer Serie"""
    termine = Appointment.query.filter_by(series_id=serie_id).order_by(Appointment.start_time).all()

    ergebnis = []
    for t in termine:
        ergebnis.append({
            'id': t.id,
            'datum': t.start_time.strftime('%d.%m.%Y'),
            'uhrzeit': t.start_time.strftime('%H:%M'),
            'end_zeit': t.end_time.strftime('%H:%M'),
            'status': t.status,
            'therapeut': f'{t.employee.user.first_name} {t.employee.user.last_name}' if t.employee and t.employee.user else '-',
            'raum': t.resource.name if t.resource else '-',
            'hat_soap': bool(t.soap_subjective or t.soap_objective or t.soap_assessment or t.soap_plan),
            'hat_notizen': bool(t.notes)
        })

    return jsonify(ergebnis)


@treatment_bp.route('/api/termin/<int:termin_id>')
@login_required
def api_termin_detail(termin_id):
    """API: Termin-Details inkl. SOAP-Notes"""
    t = Appointment.query.get_or_404(termin_id)

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
        'notes': t.notes or ''
    })


@treatment_bp.route('/api/termin/<int:termin_id>/soap', methods=['POST'])
@login_required
def api_soap_speichern(termin_id):
    """API: SOAP-Notes speichern"""
    t = Appointment.query.get_or_404(termin_id)
    data = request.get_json()

    if 'soap_subjective' in data:
        t.soap_subjective = data['soap_subjective']
    if 'soap_objective' in data:
        t.soap_objective = data['soap_objective']
    if 'soap_assessment' in data:
        t.soap_assessment = data['soap_assessment']
    if 'soap_plan' in data:
        t.soap_plan = data['soap_plan']
    if 'notes' in data:
        t.notes = data['notes']

    db.session.commit()
    return jsonify({'success': True, 'message': 'Gespeichert'})


@treatment_bp.route('/api/serie/<int:serie_id>/status', methods=['POST'])
@login_required
def api_serie_status(serie_id):
    """API: Serie-Status aendern (abschliessen/abbrechen)"""
    serie = TreatmentSeries.query.get_or_404(serie_id)
    data = request.get_json()
    neuer_status = data.get('status')

    if neuer_status not in ('completed', 'cancelled'):
        return jsonify({'error': 'Ungueltiger Status'}), 400

    serie.status = neuer_status
    if neuer_status == 'completed':
        serie.completed_at = datetime.utcnow()

    db.session.commit()
    return jsonify({'success': True, 'status': neuer_status})


# ============================================================
# Behandlungsplan
# ============================================================

@treatment_bp.route('/plan/<int:patient_id>')
@login_required
def treatment_plan(patient_id):
    """Behandlungsplan fuer einen Patienten"""
    patient = Patient.query.get_or_404(patient_id)
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
    therapeuten = Employee.query.filter_by(is_active=True).all()
    standorte = Location.query.all()

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
