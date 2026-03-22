# Behandlungs-Routen: Serien, Templates, Behandlungsplan, Warteliste, Gruppentherapie

from datetime import datetime, date, timedelta
from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from blueprints.treatment import treatment_bp
from models import (db, Patient, Employee, Doctor, TreatmentSeries,
                    TreatmentSeriesTemplate, Appointment, TreatmentGoal,
                    TreatmentMeasurement, WaitlistEntry, Resource)
from ai.constraint_solver import solver


# ============================================================
# Serien-Templates
# ============================================================

@treatment_bp.route('/templates')
@login_required
def templates():
    """Alle Behandlungsserien-Templates anzeigen."""
    templates = TreatmentSeriesTemplate.query.order_by(TreatmentSeriesTemplate.name).all()
    return render_template('treatment/templates.html', templates=templates)


@treatment_bp.route('/templates/neu', methods=['GET', 'POST'])
@login_required
def template_create():
    """Neues Template erstellen."""
    if request.method == 'POST':
        org_id = 1
        if current_user.employee:
            org_id = current_user.employee.organization_id

        template = TreatmentSeriesTemplate(
            organization_id=org_id,
            name=request.form.get('name', '').strip(),
            tariff_type=request.form.get('tariff_type', '311'),
            num_appointments=int(request.form.get('num_appointments', 9)),
            duration_minutes=int(request.form.get('duration_minutes', 30)),
            min_interval_days=int(request.form.get('min_interval_days', 1)),
            group_therapy=bool(request.form.get('group_therapy')),
            requires_resource=bool(request.form.get('requires_resource')),
        )
        db.session.add(template)
        db.session.commit()
        flash(f'Template "{template.name}" erstellt', 'success')
        return redirect(url_for('treatment.templates'))

    return render_template('treatment/template_form.html', template=None)


@treatment_bp.route('/templates/<int:id>/bearbeiten', methods=['GET', 'POST'])
@login_required
def template_edit(id):
    """Template bearbeiten."""
    template = TreatmentSeriesTemplate.query.get_or_404(id)

    if request.method == 'POST':
        template.name = request.form.get('name', '').strip()
        template.tariff_type = request.form.get('tariff_type', '311')
        template.num_appointments = int(request.form.get('num_appointments', 9))
        template.duration_minutes = int(request.form.get('duration_minutes', 30))
        template.min_interval_days = int(request.form.get('min_interval_days', 1))
        template.group_therapy = bool(request.form.get('group_therapy'))
        template.requires_resource = bool(request.form.get('requires_resource'))
        db.session.commit()
        flash(f'Template "{template.name}" aktualisiert', 'success')
        return redirect(url_for('treatment.templates'))

    return render_template('treatment/template_form.html', template=template)


# ============================================================
# Behandlungsserien
# ============================================================

@treatment_bp.route('/serien')
@login_required
def serien():
    """Alle aktiven Behandlungsserien anzeigen."""
    status_filter = request.args.get('status', 'active')
    query = TreatmentSeries.query

    if status_filter and status_filter != 'all':
        query = query.filter_by(status=status_filter)

    serien = query.order_by(TreatmentSeries.created_at.desc()).all()
    return render_template('treatment/serien.html', serien=serien, status_filter=status_filter)


@treatment_bp.route('/serien/neu', methods=['GET', 'POST'])
@login_required
def serie_create():
    """Neue Behandlungsserie starten."""
    if request.method == 'POST':
        patient_id = int(request.form.get('patient_id', 0))
        template_id = request.form.get('template_id')
        therapist_id = int(request.form.get('therapist_id', 0))

        patient = Patient.query.get(patient_id)
        if not patient:
            flash('Patient nicht gefunden', 'error')
            return redirect(url_for('treatment.serie_create'))

        serie = TreatmentSeries(
            patient_id=patient_id,
            template_id=int(template_id) if template_id else None,
            therapist_id=therapist_id,
            diagnosis=request.form.get('diagnosis', '').strip(),
            prescription_date=datetime.strptime(request.form['prescription_date'], '%Y-%m-%d').date() if request.form.get('prescription_date') else date.today(),
            prescription_type=request.form.get('prescription_type', 'initial'),
            insurance_type=request.form.get('insurance_type', 'KVG'),
            billing_model=request.form.get('billing_model', 'tiers_garant'),
        )

        doctor_id = request.form.get('doctor_id')
        if doctor_id:
            serie.prescribing_doctor_id = int(doctor_id)

        db.session.add(serie)
        db.session.commit()
        flash(f'Behandlungsserie für {patient.full_name} erstellt', 'success')
        return redirect(url_for('treatment.serie_detail', id=serie.id))

    templates = TreatmentSeriesTemplate.query.order_by(TreatmentSeriesTemplate.name).all()
    therapeuten = Employee.query.filter_by(is_active=True).all()
    aerzte = Doctor.query.all()
    patienten = Patient.query.filter_by(is_active=True).order_by(Patient.last_name).all()

    return render_template('treatment/serie_form.html',
                           serie=None, templates=templates,
                           therapeuten=therapeuten, aerzte=aerzte,
                           patienten=patienten)


@treatment_bp.route('/serien/<int:id>')
@login_required
def serie_detail(id):
    """Seriendetails anzeigen."""
    serie = TreatmentSeries.query.get_or_404(id)
    termine = serie.appointments.order_by(Appointment.start_time).all()
    ziele = serie.goals.order_by(TreatmentGoal.created_at).all()
    messungen = serie.measurements.order_by(TreatmentMeasurement.measured_at.desc()).limit(20).all()
    return render_template('treatment/serie_detail.html',
                           serie=serie, termine=termine,
                           ziele=ziele, messungen=messungen)


@treatment_bp.route('/serien/<int:id>/abschliessen', methods=['POST'])
@login_required
def serie_complete(id):
    """Serie abschliessen."""
    serie = TreatmentSeries.query.get_or_404(id)
    serie.status = 'completed'
    db.session.commit()
    flash(f'Serie für {serie.patient.full_name} abgeschlossen', 'success')
    return redirect(url_for('treatment.serie_detail', id=id))


@treatment_bp.route('/serien/<int:id>/abbrechen', methods=['POST'])
@login_required
def serie_cancel(id):
    """Serie abbrechen."""
    serie = TreatmentSeries.query.get_or_404(id)
    serie.status = 'cancelled'
    # Zukünftige Termine absagen
    future_apts = serie.appointments.filter(
        Appointment.start_time >= datetime.now(),
        Appointment.status == 'scheduled'
    ).all()
    for apt in future_apts:
        apt.status = 'cancelled'
        apt.cancellation_reason = 'Serie abgebrochen'
    db.session.commit()
    flash(f'Serie für {serie.patient.full_name} abgebrochen, {len(future_apts)} Termine abgesagt', 'warning')
    return redirect(url_for('treatment.serie_detail', id=id))


# ============================================================
# Planungsassistent (Wizard)
# ============================================================

@treatment_bp.route('/serien/<int:id>/planen', methods=['GET', 'POST'])
@login_required
def serie_planen(id):
    """Planungsassistent: Termine für eine Serie vorschlagen."""
    serie = TreatmentSeries.query.get_or_404(id)

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'vorschlagen':
            # Vorschläge generieren
            preferred_day = request.form.get('preferred_day')
            preferred_time = request.form.get('preferred_time')
            start_date_str = request.form.get('start_date')

            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else date.today() + timedelta(days=1)
            pref_day = int(preferred_day) if preferred_day else None

            result = solver.plan_series(
                patient_id=serie.patient_id,
                employee_id=serie.therapist_id,
                template_id=serie.template_id,
                start_date=start_date,
                preferred_day=pref_day,
                preferred_time=preferred_time or None,
                series_id=serie.id,
            )

            return render_template('treatment/serie_planen.html',
                                   serie=serie, vorschlaege=result.get('vorschlaege', []),
                                   result=result)

        elif action == 'buchen':
            # Alle vorgeschlagenen Termine buchen
            count = 0
            i = 0
            while True:
                datum_str = request.form.get(f'slot_datum_{i}')
                start_str = request.form.get(f'slot_start_{i}')
                ende_str = request.form.get(f'slot_ende_{i}')
                location_id = request.form.get(f'slot_location_{i}')
                resource_id = request.form.get(f'slot_resource_{i}')

                if not datum_str:
                    break

                try:
                    start_dt = datetime.strptime(f'{datum_str} {start_str}', '%Y-%m-%d %H:%M')
                    end_dt = datetime.strptime(f'{datum_str} {ende_str}', '%Y-%m-%d %H:%M')

                    termin = Appointment(
                        series_id=serie.id,
                        patient_id=serie.patient_id,
                        employee_id=serie.therapist_id,
                        location_id=int(location_id) if location_id else None,
                        resource_id=int(resource_id) if resource_id else None,
                        start_time=start_dt,
                        end_time=end_dt,
                        status='scheduled',
                        type='treatment',
                    )
                    db.session.add(termin)
                    count += 1
                except (ValueError, TypeError):
                    pass

                i += 1

            db.session.commit()
            flash(f'{count} Termine für die Serie gebucht', 'success')
            return redirect(url_for('treatment.serie_detail', id=serie.id))

    return render_template('treatment/serie_planen.html',
                           serie=serie, vorschlaege=None, result=None)


# ============================================================
# Behandlungsplan (Ziele, Messungen)
# ============================================================

@treatment_bp.route('/serien/<int:id>/ziel', methods=['POST'])
@login_required
def add_goal(id):
    """Behandlungsziel hinzufügen."""
    serie = TreatmentSeries.query.get_or_404(id)
    ziel = TreatmentGoal(
        series_id=serie.id,
        title=request.form.get('title', '').strip(),
        description=request.form.get('description', '').strip(),
        target_value=request.form.get('target_value', '').strip(),
        current_value=request.form.get('current_value', '').strip(),
        phase=serie.healing_phase,
    )
    db.session.add(ziel)
    db.session.commit()
    flash('Behandlungsziel hinzugefügt', 'success')
    return redirect(url_for('treatment.serie_detail', id=id))


@treatment_bp.route('/ziel/<int:id>/erreicht', methods=['POST'])
@login_required
def goal_achieved(id):
    """Ziel als erreicht markieren."""
    ziel = TreatmentGoal.query.get_or_404(id)
    ziel.status = 'achieved'
    ziel.achieved_at = datetime.utcnow()
    db.session.commit()
    flash('Ziel als erreicht markiert', 'success')
    return redirect(url_for('treatment.serie_detail', id=ziel.series_id))


@treatment_bp.route('/serien/<int:id>/messung', methods=['POST'])
@login_required
def add_measurement(id):
    """Messwert hinzufügen."""
    serie = TreatmentSeries.query.get_or_404(id)
    messung = TreatmentMeasurement(
        series_id=serie.id,
        measurement_type=request.form.get('measurement_type', 'single'),
        label=request.form.get('label', '').strip(),
        value=request.form.get('value', '').strip() or None,
        value_pair_left=request.form.get('value_pair_left', '').strip() or None,
        value_pair_right=request.form.get('value_pair_right', '').strip() or None,
        unit=request.form.get('unit', '').strip(),
        notes=request.form.get('notes', '').strip(),
    )

    goal_id = request.form.get('goal_id')
    if goal_id:
        messung.goal_id = int(goal_id)

    appointment_id = request.form.get('appointment_id')
    if appointment_id:
        messung.appointment_id = int(appointment_id)

    db.session.add(messung)
    db.session.commit()
    flash('Messwert erfasst', 'success')
    return redirect(url_for('treatment.serie_detail', id=id))


@treatment_bp.route('/serien/<int:id>/phase', methods=['POST'])
@login_required
def update_phase(id):
    """Heilungsphase aktualisieren."""
    serie = TreatmentSeries.query.get_or_404(id)
    serie.healing_phase = request.form.get('phase', 'initial')
    db.session.commit()
    flash(f'Phase auf "{TreatmentSeries.PHASE_NAMES.get(serie.healing_phase, serie.healing_phase)}" geändert', 'success')
    return redirect(url_for('treatment.serie_detail', id=id))


# ============================================================
# Warteliste
# ============================================================

@treatment_bp.route('/warteliste')
@login_required
def warteliste():
    """Warteliste anzeigen."""
    eintraege = WaitlistEntry.query.filter_by(status='waiting').order_by(
        WaitlistEntry.priority, WaitlistEntry.created_at
    ).all()
    return render_template('treatment/warteliste.html', eintraege=eintraege)


@treatment_bp.route('/warteliste/hinzufuegen', methods=['POST'])
@login_required
def warteliste_add():
    """Patient zur Warteliste hinzufügen."""
    entry = WaitlistEntry(
        patient_id=int(request.form.get('patient_id')),
        therapist_id=int(request.form.get('therapist_id')) if request.form.get('therapist_id') else None,
        duration_minutes=int(request.form.get('duration_minutes', 30)),
        priority=int(request.form.get('priority', 5)),
        notes=request.form.get('notes', '').strip(),
    )

    series_id = request.form.get('series_id')
    if series_id:
        entry.series_id = int(series_id)

    db.session.add(entry)
    db.session.commit()
    flash('Patient zur Warteliste hinzugefügt', 'success')
    return redirect(url_for('treatment.warteliste'))


@treatment_bp.route('/warteliste/<int:id>/entfernen', methods=['POST'])
@login_required
def warteliste_remove(id):
    """Eintrag von der Warteliste entfernen."""
    entry = WaitlistEntry.query.get_or_404(id)
    entry.status = 'cancelled'
    db.session.commit()
    flash('Von Warteliste entfernt', 'success')
    return redirect(url_for('treatment.warteliste'))


# ============================================================
# API-Endpunkte
# ============================================================

@treatment_bp.route('/api/serien/<int:patient_id>')
@login_required
def api_patient_serien(patient_id):
    """API: Serien eines Patienten."""
    serien = TreatmentSeries.query.filter_by(patient_id=patient_id).order_by(
        TreatmentSeries.created_at.desc()
    ).all()
    return jsonify([{
        'id': s.id,
        'template': s.template.name if s.template else 'Individuell',
        'therapeut': s.therapist.display_name if s.therapist else '',
        'diagnose': s.diagnosis or '',
        'status': s.status,
        'phase': s.healing_phase,
        'erstellt': s.created_at.strftime('%d.%m.%Y'),
    } for s in serien])


@treatment_bp.route('/api/verfuegbarkeit', methods=['POST'])
@login_required
def api_verfuegbarkeit():
    """API: Verfügbare Slots prüfen."""
    data = request.get_json()
    slots = solver.find_slots(
        employee_id=data.get('employee_id'),
        duration_minutes=data.get('duration_minutes', 30),
        num_slots=data.get('num_slots', 5),
        start_date=datetime.strptime(data['start_date'], '%Y-%m-%d').date() if data.get('start_date') else None,
        patient_id=data.get('patient_id'),
        series_id=data.get('series_id'),
    )
    return jsonify([s.to_dict() for s in slots])
