# Ressourcen-Routen: Räume, Geräte, Ressourcen-Kalender

from datetime import datetime, date, time, timedelta
from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required
from blueprints.resources import resources_bp
from models import db, Resource, Location, Appointment


@resources_bp.route('/')
@login_required
def index():
    """Alle Ressourcen anzeigen, gruppiert nach Standort."""
    locations = Location.query.filter_by(is_active=True).all()
    return render_template('resources/index.html', locations=locations)


@resources_bp.route('/neu', methods=['GET', 'POST'])
@login_required
def create():
    """Neue Ressource erstellen."""
    if request.method == 'POST':
        resource = Resource(
            location_id=int(request.form.get('location_id')),
            name=request.form.get('name', '').strip(),
            type=request.form.get('type', 'room'),
            capacity=int(request.form.get('capacity', 1)),
        )
        db.session.add(resource)
        db.session.commit()
        flash(f'Ressource "{resource.name}" erstellt', 'success')
        return redirect(url_for('resources.index'))

    locations = Location.query.filter_by(is_active=True).all()
    return render_template('resources/form.html', resource=None, locations=locations)


@resources_bp.route('/<int:id>/bearbeiten', methods=['GET', 'POST'])
@login_required
def edit(id):
    """Ressource bearbeiten."""
    resource = Resource.query.get_or_404(id)

    if request.method == 'POST':
        resource.name = request.form.get('name', '').strip()
        resource.type = request.form.get('type', 'room')
        resource.location_id = int(request.form.get('location_id'))
        resource.capacity = int(request.form.get('capacity', 1))
        resource.is_active = bool(request.form.get('is_active'))
        db.session.commit()
        flash(f'Ressource "{resource.name}" aktualisiert', 'success')
        return redirect(url_for('resources.index'))

    locations = Location.query.filter_by(is_active=True).all()
    return render_template('resources/form.html', resource=resource, locations=locations)


@resources_bp.route('/kalender')
@login_required
def calendar():
    """Ressourcen-Kalender (Wochenansicht)."""
    datum_str = request.args.get('datum')
    if datum_str:
        current_date = datetime.strptime(datum_str, '%Y-%m-%d').date()
    else:
        current_date = date.today()

    # Wochenstart (Montag) berechnen
    week_start = current_date - timedelta(days=current_date.weekday())
    week_end = week_start + timedelta(days=4)  # Freitag

    days = []
    for i in range(5):
        day = week_start + timedelta(days=i)
        days.append(day)

    # Ressourcen laden
    resources = Resource.query.filter_by(is_active=True).order_by(
        Resource.location_id, Resource.name
    ).all()

    # Termine pro Ressource und Tag laden
    week_start_dt = datetime.combine(week_start, time.min)
    week_end_dt = datetime.combine(week_end, time.max)

    resource_appointments = {}
    for res in resources:
        apts = Appointment.query.filter(
            Appointment.resource_id == res.id,
            Appointment.status != 'cancelled',
            Appointment.start_time >= week_start_dt,
            Appointment.start_time <= week_end_dt
        ).order_by(Appointment.start_time).all()
        resource_appointments[res.id] = apts

    prev_week = (week_start - timedelta(days=7)).isoformat()
    next_week = (week_start + timedelta(days=7)).isoformat()

    return render_template('resources/calendar.html',
                           resources=resources, days=days,
                           resource_appointments=resource_appointments,
                           week_start=week_start, prev_week=prev_week,
                           next_week=next_week)


@resources_bp.route('/api/verfuegbarkeit/<int:resource_id>')
@login_required
def api_availability(resource_id):
    """API: Ressourcen-Verfügbarkeit für einen bestimmten Tag."""
    datum_str = request.args.get('datum', date.today().isoformat())
    datum = datetime.strptime(datum_str, '%Y-%m-%d').date()

    start_dt = datetime.combine(datum, time.min)
    end_dt = datetime.combine(datum, time.max)

    resource = Resource.query.get_or_404(resource_id)

    apts = Appointment.query.filter(
        Appointment.resource_id == resource_id,
        Appointment.status != 'cancelled',
        Appointment.start_time >= start_dt,
        Appointment.start_time <= end_dt
    ).order_by(Appointment.start_time).all()

    return jsonify({
        'resource': resource.name,
        'datum': datum.strftime('%d.%m.%Y'),
        'kapazitaet': resource.capacity,
        'belegungen': [{
            'start': a.start_time.strftime('%H:%M'),
            'ende': a.end_time.strftime('%H:%M'),
            'patient': a.patient.full_name,
            'therapeut': a.employee.display_name,
        } for a in apts],
        'belegt': len(apts),
        'frei': resource.capacity - len(apts),
    })
