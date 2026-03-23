"""HR und Lohnbuchhaltung - Routen"""
from datetime import datetime, date, time, timedelta
from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from blueprints.hr import hr_bp
from models import db, Employee, User, EmployeeContract, EmployeeSalary, EmployeeChild, \
    PayrollRun, Payslip, TimeEntry, OvertimeAccount, Expense, Certificate, AbsenceQuota, Absence


# ============================================================
# HR-Uebersicht
# ============================================================

@hr_bp.route('/')
@login_required
def index():
    """HR-Dashboard"""
    org_id = current_user.organization_id

    # Statistiken
    total_employees = Employee.query.filter_by(organization_id=org_id).count()
    active_employees = Employee.query.filter_by(organization_id=org_id, is_active=True).count()

    # Personalkosten aktueller Monat
    today = date.today()
    current_run = PayrollRun.query.filter_by(
        organization_id=org_id, year=today.year, month=today.month
    ).first()
    monthly_costs = current_run.total_gross if current_run else 0

    # Offene Ferienantraege
    pending_absences = Absence.query.join(Employee).filter(
        Employee.organization_id == org_id,
        Absence.absence_type == 'vacation',
        Absence.status == 'pending'
    ).count()

    # Ablaufende Zertifikate (naechste 90 Tage)
    expiring_certs = Certificate.query.join(Employee).filter(
        Employee.organization_id == org_id,
        Certificate.expiry_date.isnot(None),
        Certificate.expiry_date <= today + timedelta(days=90),
        Certificate.expiry_date >= today
    ).count()

    # Letzte Lohnlaeufe
    recent_runs = PayrollRun.query.filter_by(
        organization_id=org_id
    ).order_by(PayrollRun.year.desc(), PayrollRun.month.desc()).limit(6).all()

    # Offene Spesen
    pending_expenses = Expense.query.join(Employee).filter(
        Employee.organization_id == org_id,
        Expense.status == 'submitted'
    ).count()

    return render_template('hr/index.html',
        total_employees=total_employees,
        active_employees=active_employees,
        monthly_costs=monthly_costs,
        pending_absences=pending_absences,
        expiring_certs=expiring_certs,
        recent_runs=recent_runs,
        pending_expenses=pending_expenses
    )


# ============================================================
# Personalakte
# ============================================================

@hr_bp.route('/personnel/<int:employee_id>')
@login_required
def personnel_file(employee_id):
    """Personalakte eines Mitarbeiters"""
    emp = Employee.query.get_or_404(employee_id)
    user = emp.user

    # Vertragsdaten
    contract = EmployeeContract.query.filter_by(
        employee_id=emp.id
    ).order_by(EmployeeContract.start_date.desc()).first()

    # Lohndaten
    salary = EmployeeSalary.query.filter(
        EmployeeSalary.employee_id == emp.id,
        db.or_(EmployeeSalary.valid_to.is_(None), EmployeeSalary.valid_to >= date.today())
    ).order_by(EmployeeSalary.valid_from.desc()).first()

    # Kinder
    children = EmployeeChild.query.filter_by(employee_id=emp.id).all()

    # Lohnhistorie
    salary_history = EmployeeSalary.query.filter_by(
        employee_id=emp.id
    ).order_by(EmployeeSalary.valid_from.desc()).all()

    # Letzte Lohnabrechnungen
    payslips = Payslip.query.filter_by(
        employee_id=emp.id
    ).join(PayrollRun).order_by(PayrollRun.year.desc(), PayrollRun.month.desc()).limit(12).all()

    # Vertragshistorie
    contracts = EmployeeContract.query.filter_by(
        employee_id=emp.id
    ).order_by(EmployeeContract.start_date.desc()).all()

    # Ferienkontingent
    absence_quota = AbsenceQuota.query.filter_by(
        employee_id=emp.id, year=date.today().year, absence_type='vacation'
    ).first()

    tab = request.args.get('tab', 'contract')

    return render_template('hr/personnel_file.html',
        employee=emp, user=user, contract=contract, salary=salary,
        children=children, salary_history=salary_history, payslips=payslips,
        contracts=contracts, absence_quota=absence_quota, tab=tab
    )


@hr_bp.route('/personnel/<int:employee_id>/contract', methods=['POST'])
@login_required
def save_contract(employee_id):
    """Vertragsdaten speichern"""
    emp = Employee.query.get_or_404(employee_id)

    contract = EmployeeContract.query.filter_by(employee_id=emp.id).order_by(
        EmployeeContract.start_date.desc()
    ).first()

    if not contract:
        contract = EmployeeContract(employee_id=emp.id)
        db.session.add(contract)

    contract.contract_type = request.form.get('contract_type', 'permanent')
    start_str = request.form.get('start_date')
    if start_str:
        contract.start_date = datetime.strptime(start_str, '%Y-%m-%d').date()
    end_str = request.form.get('end_date')
    contract.end_date = datetime.strptime(end_str, '%Y-%m-%d').date() if end_str else None
    probation_str = request.form.get('probation_end')
    contract.probation_end = datetime.strptime(probation_str, '%Y-%m-%d').date() if probation_str else None
    contract.notice_period_months = int(request.form.get('notice_period_months', 1))
    contract.pensum_percent = int(request.form.get('pensum_percent', 100))
    contract.vacation_days = int(request.form.get('vacation_days', 20))

    db.session.commit()
    flash('Vertragsdaten gespeichert.', 'success')
    return redirect(url_for('hr.personnel_file', employee_id=emp.id, tab='contract'))


@hr_bp.route('/personnel/<int:employee_id>/salary', methods=['POST'])
@login_required
def save_salary(employee_id):
    """Lohndaten speichern"""
    emp = Employee.query.get_or_404(employee_id)

    # Pruefen ob sich der Lohn aendert
    current_salary = EmployeeSalary.query.filter(
        EmployeeSalary.employee_id == emp.id,
        db.or_(EmployeeSalary.valid_to.is_(None), EmployeeSalary.valid_to >= date.today())
    ).order_by(EmployeeSalary.valid_from.desc()).first()

    new_amount = float(request.form.get('amount', 0))
    valid_from_str = request.form.get('valid_from')
    valid_from = datetime.strptime(valid_from_str, '%Y-%m-%d').date() if valid_from_str else date.today()

    # Wenn es einen bestehenden Lohn gibt und der Betrag sich aendert: alten abschliessen
    if current_salary and current_salary.amount != new_amount:
        current_salary.valid_to = valid_from - timedelta(days=1)

    # Neuen Lohn anlegen oder bestehenden aktualisieren
    if not current_salary or current_salary.amount != new_amount:
        salary = EmployeeSalary(employee_id=emp.id)
        db.session.add(salary)
    else:
        salary = current_salary

    salary.salary_type = request.form.get('salary_type', 'monthly')
    salary.amount = new_amount
    hourly = request.form.get('hourly_rate')
    salary.hourly_rate = float(hourly) if hourly else None
    salary.thirteenth_month = request.form.get('thirteenth_month') == 'on'
    salary.iban = request.form.get('iban', '')
    salary.ahv_number = request.form.get('ahv_number', '')
    salary.withholding_tax = request.form.get('withholding_tax') == 'on'
    salary.withholding_tax_code = request.form.get('withholding_tax_code', '')
    salary.withholding_tax_canton = request.form.get('withholding_tax_canton', '')
    bvg = request.form.get('bvg_rate')
    salary.bvg_rate = float(bvg) if bvg else 7.0
    nbuv = request.form.get('nbuv_rate')
    salary.nbuv_rate = float(nbuv) if nbuv else 1.5
    ktg = request.form.get('ktg_rate')
    salary.ktg_rate = float(ktg) if ktg else 0.5
    salary.valid_from = valid_from

    db.session.commit()
    flash('Lohndaten gespeichert.', 'success')
    return redirect(url_for('hr.personnel_file', employee_id=emp.id, tab='salary'))


@hr_bp.route('/personnel/<int:employee_id>/child', methods=['POST'])
@login_required
def save_child(employee_id):
    """Kind hinzufuegen"""
    emp = Employee.query.get_or_404(employee_id)

    child = EmployeeChild(employee_id=emp.id)
    child.first_name = request.form.get('first_name', '')
    child.last_name = request.form.get('last_name', '')
    dob_str = request.form.get('date_of_birth')
    child.date_of_birth = datetime.strptime(dob_str, '%Y-%m-%d').date() if dob_str else None
    child.allowance_type = request.form.get('allowance_type', 'child')
    child.allowance_amount = float(request.form.get('allowance_amount', 200))

    db.session.add(child)
    db.session.commit()
    flash('Kind hinzugefügt.', 'success')
    return redirect(url_for('hr.personnel_file', employee_id=emp.id, tab='salary'))


@hr_bp.route('/personnel/<int:employee_id>/child/<int:child_id>/delete', methods=['POST'])
@login_required
def delete_child(employee_id, child_id):
    """Kind entfernen"""
    child = EmployeeChild.query.get_or_404(child_id)
    db.session.delete(child)
    db.session.commit()
    flash('Kind entfernt.', 'success')
    return redirect(url_for('hr.personnel_file', employee_id=employee_id, tab='salary'))


# ============================================================
# Lohnlauf
# ============================================================

@hr_bp.route('/payroll')
@login_required
def payroll():
    """Lohnlauf-Uebersicht"""
    org_id = current_user.organization_id
    runs = PayrollRun.query.filter_by(
        organization_id=org_id
    ).order_by(PayrollRun.year.desc(), PayrollRun.month.desc()).all()

    return render_template('hr/payroll.html', runs=runs)


@hr_bp.route('/payroll/create', methods=['GET', 'POST'])
@login_required
def payroll_create():
    """Neuen Lohnlauf erstellen"""
    if request.method == 'POST':
        year = int(request.form.get('year', date.today().year))
        month = int(request.form.get('month', date.today().month))

        from services.payroll_service import create_payroll_run
        run, error = create_payroll_run(current_user.organization_id, year, month)

        if error:
            flash(f'Fehler: {error}', 'error')
            return redirect(url_for('hr.payroll'))

        flash(f'Lohnlauf {month}/{year} erstellt und berechnet.', 'success')
        return redirect(url_for('hr.payroll_detail', run_id=run.id))

    today = date.today()
    return render_template('hr/payroll_create.html',
        current_year=today.year, current_month=today.month)


@hr_bp.route('/payroll/<int:run_id>')
@login_required
def payroll_detail(run_id):
    """Lohnlauf-Detail"""
    run = PayrollRun.query.get_or_404(run_id)
    payslips = Payslip.query.filter_by(payroll_run_id=run.id).join(Employee).join(User).all()

    from services.payroll_service import MONTH_NAMES
    month_name = MONTH_NAMES.get(run.month, str(run.month))

    return render_template('hr/payroll_detail.html',
        run=run, payslips=payslips, month_name=month_name)


@hr_bp.route('/payroll/<int:run_id>/approve', methods=['POST'])
@login_required
def payroll_approve(run_id):
    """Lohnlauf freigeben"""
    run = PayrollRun.query.get_or_404(run_id)
    run.status = 'approved'
    run.approved_by_id = current_user.id
    run.approved_at = datetime.now()
    db.session.commit()
    flash('Lohnlauf freigegeben.', 'success')
    return redirect(url_for('hr.payroll_detail', run_id=run.id))


@hr_bp.route('/payroll/<int:run_id>/pay', methods=['POST'])
@login_required
def payroll_pay(run_id):
    """Lohnlauf als ausbezahlt markieren und buchen"""
    run = PayrollRun.query.get_or_404(run_id)
    run.status = 'paid'
    run.paid_at = datetime.now()

    # Spesen als ausbezahlt markieren
    for slip in run.payslips:
        expenses = Expense.query.filter_by(
            employee_id=slip.employee_id, status='approved'
        ).filter(Expense.paid_via.is_(None)).all()
        for exp in expenses:
            exp.status = 'paid'
            exp.paid_via = 'payroll'
            exp.payroll_run_id = run.id

    # In Finanzbuchhaltung buchen
    from services.payroll_service import book_payroll
    entry, error = book_payroll(run, current_user.id)
    if error:
        flash(f'Lohnlauf ausbezahlt, aber Buchung fehlgeschlagen: {error}', 'warning')
    else:
        flash('Lohnlauf ausbezahlt und gebucht.', 'success')

    db.session.commit()
    return redirect(url_for('hr.payroll_detail', run_id=run.id))


@hr_bp.route('/payroll/<int:run_id>/recalculate', methods=['POST'])
@login_required
def payroll_recalculate(run_id):
    """Lohnlauf neu berechnen"""
    run = PayrollRun.query.get_or_404(run_id)
    if run.status not in ('draft', 'calculated'):
        flash('Freigegebene Lohnläufe können nicht neu berechnet werden.', 'error')
        return redirect(url_for('hr.payroll_detail', run_id=run.id))

    # Bestehende Payslips loeschen
    Payslip.query.filter_by(payroll_run_id=run.id).delete()

    from services.payroll_service import calculate_payslip

    employees = Employee.query.filter_by(
        organization_id=run.organization_id, is_active=True
    ).all()

    total_gross = 0
    total_net = 0
    total_employer = 0

    for emp in employees:
        data = calculate_payslip(emp, run.month, run.year)
        if not data:
            continue

        payslip = Payslip(
            payroll_run_id=run.id, employee_id=emp.id,
            gross_salary=data['gross_salary'], thirteenth_month=data['thirteenth_month'],
            child_allowance=data['child_allowance'], bonuses=data['bonuses'],
            expenses_total=data['expenses_total'], overtime_payout=data['overtime_payout'],
            gross_total=data['gross_total'], ahv_iv_eo=data['ahv_iv_eo'],
            alv=data['alv'], alv2=data.get('alv2', 0), bvg=data['bvg'],
            nbuv=data['nbuv'], ktg=data['ktg'],
            withholding_tax=data['withholding_tax'],
            deductions_total=data['deductions_total'], net_salary=data['net_salary'],
            employer_ahv_iv_eo=data['employer_ahv_iv_eo'], employer_alv=data['employer_alv'],
            employer_bvg=data['employer_bvg'], employer_uvg=data['employer_uvg'],
            employer_ktg=data['employer_ktg'], employer_fak=data['employer_fak'],
            employer_vk=data['employer_vk'], employer_total=data['employer_total'],
            details_json=str(data)
        )
        db.session.add(payslip)
        total_gross += data['gross_total']
        total_net += data['net_salary']
        total_employer += data['employer_total']

    run.total_gross = round(total_gross, 2)
    run.total_net = round(total_net, 2)
    run.total_employer_contributions = round(total_employer, 2)
    run.status = 'calculated'
    db.session.commit()

    flash('Lohnlauf neu berechnet.', 'success')
    return redirect(url_for('hr.payroll_detail', run_id=run.id))


# ============================================================
# Lohnabrechnung (Payslip)
# ============================================================

@hr_bp.route('/payslip/<int:payslip_id>')
@login_required
def payslip_detail(payslip_id):
    """Lohnabrechnung Detail"""
    payslip = Payslip.query.get_or_404(payslip_id)
    run = payslip.payroll_run
    emp = Employee.query.get(payslip.employee_id)
    user = emp.user
    salary = EmployeeSalary.query.filter(
        EmployeeSalary.employee_id == emp.id,
        db.or_(EmployeeSalary.valid_to.is_(None), EmployeeSalary.valid_to >= date(run.year, run.month, 1))
    ).order_by(EmployeeSalary.valid_from.desc()).first()

    from services.payroll_service import MONTH_NAMES
    month_name = MONTH_NAMES.get(run.month, str(run.month))

    return render_template('hr/payslip.html',
        payslip=payslip, run=run, employee=emp, user=user,
        salary=salary, month_name=month_name)


# ============================================================
# Zeiterfassung
# ============================================================

@hr_bp.route('/time-tracking')
@login_required
def time_tracking():
    """Zeiterfassung"""
    org_id = current_user.organization_id
    employee_id = request.args.get('employee_id', type=int)

    # Wenn kein MA angegeben, eigenen nehmen
    if not employee_id and current_user.employee:
        employee_id = current_user.employee.id

    employee = Employee.query.get(employee_id) if employee_id else None

    # Alle Mitarbeiter fuer Dropdown
    employees = Employee.query.filter_by(
        organization_id=org_id, is_active=True
    ).join(User).order_by(User.last_name).all()

    # Zeiteintraege der aktuellen Woche
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    entries = []
    overtime = None
    if employee_id:
        entries = TimeEntry.query.filter(
            TimeEntry.employee_id == employee_id,
            TimeEntry.date >= week_start,
            TimeEntry.date <= week_end
        ).order_by(TimeEntry.date, TimeEntry.clock_in).all()

        # Ueberstundenkonto
        overtime = OvertimeAccount.query.filter_by(
            employee_id=employee_id, year=today.year, month=today.month
        ).first()

    # Heutiger Eintrag (fuer Stempeluhr)
    today_entry = None
    if employee_id:
        today_entry = TimeEntry.query.filter_by(
            employee_id=employee_id, date=today
        ).order_by(TimeEntry.clock_in.desc()).first()

    # Wochentage aufbauen
    week_days = []
    for i in range(7):
        d = week_start + timedelta(days=i)
        day_entries = [e for e in entries if e.date == d]
        total_mins = sum(e.worked_minutes or 0 for e in day_entries)
        # Soll: Mo-Fr 8.4h (504 Min) bei 100%, angepasst an Pensum
        pensum = employee.pensum_percent if employee else 100
        target_mins = int(504 * (pensum / 100.0)) if i < 5 else 0
        week_days.append({
            'date': d,
            'name': ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'][i],
            'entries': day_entries,
            'total_minutes': total_mins,
            'target_minutes': target_mins,
            'diff_minutes': total_mins - target_mins
        })

    return render_template('hr/time_tracking.html',
        employee=employee, employees=employees, entries=entries,
        week_days=week_days, today_entry=today_entry, overtime=overtime,
        week_start=week_start, week_end=week_end, today=today)


@hr_bp.route('/time-tracking/clock', methods=['POST'])
@login_required
def clock_in_out():
    """Ein-/Ausstempeln"""
    employee_id = request.form.get('employee_id', type=int)
    if not employee_id and current_user.employee:
        employee_id = current_user.employee.id

    if not employee_id:
        flash('Kein Mitarbeiter zugeordnet.', 'error')
        return redirect(url_for('hr.time_tracking'))

    today = date.today()
    now = datetime.now().time()

    # Pruefen ob heute ein offener Eintrag existiert
    open_entry = TimeEntry.query.filter(
        TimeEntry.employee_id == employee_id,
        TimeEntry.date == today,
        TimeEntry.clock_out.is_(None)
    ).first()

    if open_entry:
        # Ausstempeln
        open_entry.clock_out = now
        # Arbeitszeit berechnen
        cin = datetime.combine(today, open_entry.clock_in)
        cout = datetime.combine(today, now)
        diff = cout - cin
        worked = int(diff.total_seconds() / 60) - (open_entry.break_minutes or 0)
        open_entry.worked_minutes = max(0, worked)
        open_entry.entry_type = 'clock'
        flash('Ausgestempelt.', 'success')
    else:
        # Einstempeln
        entry = TimeEntry(
            employee_id=employee_id,
            date=today,
            clock_in=now,
            entry_type='clock'
        )
        db.session.add(entry)
        flash('Eingestempelt.', 'success')

    db.session.commit()
    return redirect(url_for('hr.time_tracking', employee_id=employee_id))


@hr_bp.route('/time-tracking/manual', methods=['POST'])
@login_required
def time_manual():
    """Manuelle Zeiterfassung"""
    employee_id = request.form.get('employee_id', type=int)
    date_str = request.form.get('date')
    clock_in_str = request.form.get('clock_in')
    clock_out_str = request.form.get('clock_out')
    break_mins = int(request.form.get('break_minutes', 0))
    notes = request.form.get('notes', '')

    if not all([employee_id, date_str, clock_in_str, clock_out_str]):
        flash('Bitte alle Felder ausfüllen.', 'error')
        return redirect(url_for('hr.time_tracking', employee_id=employee_id))

    entry_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    cin = datetime.strptime(clock_in_str, '%H:%M').time()
    cout = datetime.strptime(clock_out_str, '%H:%M').time()

    # Arbeitszeit berechnen
    cin_dt = datetime.combine(entry_date, cin)
    cout_dt = datetime.combine(entry_date, cout)
    diff = cout_dt - cin_dt
    worked = int(diff.total_seconds() / 60) - break_mins

    entry = TimeEntry(
        employee_id=employee_id,
        date=entry_date,
        clock_in=cin,
        clock_out=cout,
        break_minutes=break_mins,
        worked_minutes=max(0, worked),
        entry_type='manual',
        notes=notes
    )
    db.session.add(entry)
    db.session.commit()

    flash('Zeiteintrag gespeichert.', 'success')
    return redirect(url_for('hr.time_tracking', employee_id=employee_id))


# ============================================================
# Spesen
# ============================================================

@hr_bp.route('/expenses')
@login_required
def expenses():
    """Spesenliste"""
    org_id = current_user.organization_id
    status_filter = request.args.get('status', '')
    employee_id = request.args.get('employee_id', type=int)

    query = Expense.query.join(Employee).filter(
        Employee.organization_id == org_id
    )

    if status_filter:
        query = query.filter(Expense.status == status_filter)
    if employee_id:
        query = query.filter(Expense.employee_id == employee_id)

    expenses_list = query.order_by(Expense.date.desc()).all()

    employees = Employee.query.filter_by(
        organization_id=org_id, is_active=True
    ).join(User).order_by(User.last_name).all()

    return render_template('hr/expenses.html',
        expenses=expenses_list, employees=employees,
        status_filter=status_filter, employee_id=employee_id)


@hr_bp.route('/expenses/create', methods=['POST'])
@login_required
def expense_create():
    """Neue Spese einreichen"""
    employee_id = request.form.get('employee_id', type=int)
    if not employee_id and current_user.employee:
        employee_id = current_user.employee.id

    date_str = request.form.get('date')
    expense = Expense(
        employee_id=employee_id,
        date=datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else date.today(),
        description=request.form.get('description', ''),
        category=request.form.get('category', 'other'),
        amount=float(request.form.get('amount', 0)),
        vat_amount=float(request.form.get('vat_amount', 0)),
        notes=request.form.get('notes', ''),
        status='submitted'
    )
    db.session.add(expense)
    db.session.commit()

    flash('Spese eingereicht.', 'success')
    return redirect(url_for('hr.expenses'))


@hr_bp.route('/expenses/<int:expense_id>/approve', methods=['POST'])
@login_required
def expense_approve(expense_id):
    """Spese genehmigen"""
    expense = Expense.query.get_or_404(expense_id)
    expense.status = 'approved'
    expense.approved_by_id = current_user.id
    expense.approved_at = datetime.now()
    db.session.commit()
    flash('Spese genehmigt.', 'success')
    return redirect(url_for('hr.expenses'))


@hr_bp.route('/expenses/<int:expense_id>/reject', methods=['POST'])
@login_required
def expense_reject(expense_id):
    """Spese ablehnen"""
    expense = Expense.query.get_or_404(expense_id)
    expense.status = 'rejected'
    expense.approved_by_id = current_user.id
    expense.approved_at = datetime.now()
    db.session.commit()
    flash('Spese abgelehnt.', 'success')
    return redirect(url_for('hr.expenses'))


# ============================================================
# API-Endpunkte
# ============================================================

@hr_bp.route('/api/personnel-list')
@login_required
def api_personnel_list():
    """Personalakte-Liste fuer HR-Uebersicht"""
    org_id = current_user.organization_id
    employees = Employee.query.filter_by(
        organization_id=org_id, is_active=True
    ).join(User).order_by(User.last_name).all()

    result = []
    for emp in employees:
        salary = EmployeeSalary.query.filter(
            EmployeeSalary.employee_id == emp.id,
            db.or_(EmployeeSalary.valid_to.is_(None), EmployeeSalary.valid_to >= date.today())
        ).order_by(EmployeeSalary.valid_from.desc()).first()

        result.append({
            'id': emp.id,
            'name': f'{emp.user.first_name} {emp.user.last_name}',
            'pensum': emp.pensum_percent,
            'salary': salary.amount if salary else 0,
            'salary_type': salary.salary_type if salary else '-'
        })

    return jsonify(result)
