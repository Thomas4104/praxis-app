# Mitarbeiter-Routen: CRUD, Arbeitszeiten

from datetime import time
from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required
from blueprints.employees import employees_bp
from models import db, Employee, User, WorkSchedule, Location


@employees_bp.route('/')
@login_required
def index():
    """Mitarbeiterliste."""
    mitarbeiter = Employee.query.filter_by(is_active=True).all()
    return render_template('employees/index.html', mitarbeiter=mitarbeiter)


@employees_bp.route('/neu', methods=['GET', 'POST'])
@login_required
def create():
    """Neuen Mitarbeiter erstellen."""
    if request.method == 'POST':
        # Benutzer erstellen
        user = User(
            username=request.form.get('username', '').strip(),
            name=request.form.get('name', '').strip(),
            email=request.form.get('email', '').strip(),
            role=request.form.get('role', 'therapist'),
        )
        user.set_password(request.form.get('password', 'omnia2024'))

        db.session.add(user)
        db.session.flush()

        # Mitarbeiter erstellen
        employee = Employee(
            user_id=user.id,
            organization_id=1,  # Standard-Organisation
            pensum_percent=int(request.form.get('pensum', 100)),
            color_code=request.form.get('color_code', '#4a90d9'),
            employment_model=request.form.get('employment_model', 'employed'),
            zsr_number=request.form.get('zsr_number', '').strip(),
            gln_number=request.form.get('gln_number', '').strip(),
        )

        db.session.add(employee)
        db.session.commit()

        flash(f'Mitarbeiter {user.name} erstellt', 'success')
        return redirect(url_for('employees.edit', id=employee.id))

    locations = Location.query.filter_by(is_active=True).all()
    return render_template('employees/form.html', employee=None, locations=locations)


@employees_bp.route('/<int:id>/bearbeiten', methods=['GET', 'POST'])
@login_required
def edit(id):
    """Mitarbeiter bearbeiten + Arbeitszeiten verwalten."""
    employee = Employee.query.get_or_404(id)

    if request.method == 'POST':
        action = request.form.get('action', '')

        if action == 'update_profile':
            employee.user.name = request.form.get('name', '').strip()
            employee.user.email = request.form.get('email', '').strip()
            employee.user.role = request.form.get('role', employee.user.role)
            employee.pensum_percent = int(request.form.get('pensum', 100))
            employee.color_code = request.form.get('color_code', employee.color_code)
            employee.employment_model = request.form.get('employment_model', employee.employment_model)
            employee.zsr_number = request.form.get('zsr_number', '').strip()
            employee.gln_number = request.form.get('gln_number', '').strip()
            db.session.commit()
            flash('Profil aktualisiert', 'success')

        elif action == 'add_schedule':
            schedule = WorkSchedule(
                employee_id=employee.id,
                location_id=int(request.form.get('location_id', 1)),
                day_of_week=int(request.form.get('day_of_week', 0)),
                start_time=time.fromisoformat(request.form.get('start_time', '08:00')),
                end_time=time.fromisoformat(request.form.get('end_time', '17:00')),
                work_type=request.form.get('work_type', 'working'),
            )
            db.session.add(schedule)
            db.session.commit()
            flash('Arbeitszeit hinzugefügt', 'success')

        elif action == 'delete_schedule':
            schedule_id = int(request.form.get('schedule_id', 0))
            schedule = WorkSchedule.query.get(schedule_id)
            if schedule and schedule.employee_id == employee.id:
                db.session.delete(schedule)
                db.session.commit()
                flash('Arbeitszeit gelöscht', 'success')

        return redirect(url_for('employees.edit', id=employee.id))

    schedules = WorkSchedule.query.filter_by(employee_id=employee.id).order_by(
        WorkSchedule.day_of_week, WorkSchedule.start_time
    ).all()
    locations = Location.query.filter_by(is_active=True).all()

    return render_template('employees/form.html',
                           employee=employee,
                           schedules=schedules,
                           locations=locations)
