"""KI-Tools fuer den HR- und Lohnbuchhaltungs-Bereich"""
from datetime import datetime, date
from models import db, Employee, User, EmployeeSalary, EmployeeChild, EmployeeContract, \
    PayrollRun, Payslip, TimeEntry, OvertimeAccount, Expense, AbsenceQuota


HR_TOOLS = [
    {
        'name': 'lohnabrechnung_erstellen',
        'description': 'Startet einen neuen Lohnlauf fuer einen bestimmten Monat und Jahr. Berechnet automatisch alle Lohnabrechnungen.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'monat': {'type': 'integer', 'description': 'Monat (1-12)'},
                'jahr': {'type': 'integer', 'description': 'Jahr (z.B. 2026)'}
            },
            'required': ['monat', 'jahr']
        }
    },
    {
        'name': 'lohnabrechnung_mitarbeiter',
        'description': 'Zeigt die Lohnabrechnung eines bestimmten Mitarbeiters fuer einen Monat an.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'employee_id': {'type': 'integer', 'description': 'Mitarbeiter-ID'},
                'monat': {'type': 'integer', 'description': 'Monat (1-12)'},
                'jahr': {'type': 'integer', 'description': 'Jahr'}
            },
            'required': ['employee_id', 'monat', 'jahr']
        }
    },
    {
        'name': 'personalkosten_monat',
        'description': 'Zeigt die gesamten Personalkosten fuer einen Monat (Brutto, Netto, AG-Beitraege).',
        'input_schema': {
            'type': 'object',
            'properties': {
                'monat': {'type': 'integer', 'description': 'Monat (1-12)'},
                'jahr': {'type': 'integer', 'description': 'Jahr'}
            },
            'required': ['monat', 'jahr']
        }
    },
    {
        'name': 'ueberstunden_anzeigen',
        'description': 'Zeigt das Ueberstundenkonto eines Mitarbeiters an.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'employee_id': {'type': 'integer', 'description': 'Mitarbeiter-ID'}
            },
            'required': ['employee_id']
        }
    },
    {
        'name': 'zeiterfassung_heute',
        'description': 'Zeigt die heutige Arbeitszeit eines Mitarbeiters an.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'employee_id': {'type': 'integer', 'description': 'Mitarbeiter-ID'}
            },
            'required': ['employee_id']
        }
    },
    {
        'name': 'spesen_auflisten',
        'description': 'Listet alle Spesen eines Mitarbeiters auf, optional nach Status gefiltert.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'employee_id': {'type': 'integer', 'description': 'Mitarbeiter-ID'},
                'status': {'type': 'string', 'description': 'Filter nach Status: submitted, approved, rejected, paid'}
            },
            'required': ['employee_id']
        }
    },
    {
        'name': 'spesen_genehmigen',
        'description': 'Genehmigt eine eingereichte Spese.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'spesen_id': {'type': 'integer', 'description': 'Spesen-ID'}
            },
            'required': ['spesen_id']
        }
    },
    {
        'name': 'ferienanspruch',
        'description': 'Zeigt den restlichen Ferienanspruch eines Mitarbeiters.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'employee_id': {'type': 'integer', 'description': 'Mitarbeiter-ID'}
            },
            'required': ['employee_id']
        }
    },
    {
        'name': 'sozialversicherungen_berechnen',
        'description': 'Berechnet die Sozialversicherungsbeitraege fuer einen gegebenen Bruttolohn.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'bruttolohn': {'type': 'number', 'description': 'Monatlicher Bruttolohn in CHF'}
            },
            'required': ['bruttolohn']
        }
    },
    {
        'name': 'lohnausweis_generieren',
        'description': 'Generiert einen Jahres-Lohnausweis fuer einen Mitarbeiter.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'employee_id': {'type': 'integer', 'description': 'Mitarbeiter-ID'},
                'jahr': {'type': 'integer', 'description': 'Jahr'}
            },
            'required': ['employee_id', 'jahr']
        }
    }
]


def hr_tool_executor(tool_name, tool_input):
    """Fuehrt HR-Tools aus"""
    from flask_login import current_user
    org_id = current_user.organization_id

    if tool_name == 'lohnabrechnung_erstellen':
        monat = tool_input['monat']
        jahr = tool_input['jahr']
        from services.payroll_service import create_payroll_run
        run, error = create_payroll_run(org_id, jahr, monat)
        if error:
            return {'error': error}
        slips = Payslip.query.filter_by(payroll_run_id=run.id).all()
        return {
            'ergebnis': f'Lohnlauf {monat}/{jahr} erstellt',
            'status': run.status,
            'brutto_total': run.total_gross,
            'netto_total': run.total_net,
            'ag_beitraege': run.total_employer_contributions,
            'anzahl_mitarbeiter': len(slips)
        }

    elif tool_name == 'lohnabrechnung_mitarbeiter':
        emp_id = tool_input['employee_id']
        monat = tool_input['monat']
        jahr = tool_input['jahr']
        emp = Employee.query.get(emp_id)
        if not emp or emp.organization_id != org_id:
            return {'error': 'Mitarbeiter nicht gefunden'}

        slip = Payslip.query.join(PayrollRun).filter(
            Payslip.employee_id == emp_id,
            PayrollRun.month == monat,
            PayrollRun.year == jahr
        ).first()

        if not slip:
            return {'error': f'Keine Lohnabrechnung fuer {monat}/{jahr} gefunden'}

        return {
            'mitarbeiter': f'{emp.user.first_name} {emp.user.last_name}',
            'monat': monat,
            'jahr': jahr,
            'grundlohn': slip.gross_salary,
            'dreizehnter_monatslohn': slip.thirteenth_month,
            'kinderzulagen': slip.child_allowance,
            'brutto_total': slip.gross_total,
            'ahv_iv_eo': slip.ahv_iv_eo,
            'alv': slip.alv,
            'bvg': slip.bvg,
            'nbuv': slip.nbuv,
            'ktg': slip.ktg,
            'abzuege_total': slip.deductions_total,
            'nettolohn': slip.net_salary,
            'ag_beitraege_total': slip.employer_total
        }

    elif tool_name == 'personalkosten_monat':
        monat = tool_input['monat']
        jahr = tool_input['jahr']

        run = PayrollRun.query.filter_by(
            organization_id=org_id, year=jahr, month=monat
        ).first()

        if not run:
            return {'error': f'Kein Lohnlauf fuer {monat}/{jahr} gefunden'}

        slips = Payslip.query.filter_by(payroll_run_id=run.id).join(Employee).join(User).all()
        details = []
        for s in slips:
            details.append({
                'mitarbeiter': f'{s.employee.user.first_name} {s.employee.user.last_name}',
                'brutto': s.gross_total,
                'netto': s.net_salary,
                'ag_beitraege': s.employer_total
            })

        return {
            'monat': monat,
            'jahr': jahr,
            'brutto_total': run.total_gross,
            'netto_total': run.total_net,
            'ag_beitraege_total': run.total_employer_contributions,
            'gesamtkosten': round(run.total_gross + run.total_employer_contributions, 2),
            'details': details
        }

    elif tool_name == 'ueberstunden_anzeigen':
        emp_id = tool_input['employee_id']
        emp = Employee.query.get(emp_id)
        if not emp or emp.organization_id != org_id:
            return {'error': 'Mitarbeiter nicht gefunden'}

        accounts = OvertimeAccount.query.filter_by(
            employee_id=emp_id
        ).order_by(OvertimeAccount.year.desc(), OvertimeAccount.month.desc()).limit(6).all()

        if not accounts:
            return {
                'mitarbeiter': f'{emp.user.first_name} {emp.user.last_name}',
                'ergebnis': 'Kein Ueberstundenkonto vorhanden',
                'kumuliert_minuten': 0
            }

        return {
            'mitarbeiter': f'{emp.user.first_name} {emp.user.last_name}',
            'kumuliert_minuten': accounts[0].cumulative_overtime if accounts else 0,
            'kumuliert_stunden': round((accounts[0].cumulative_overtime or 0) / 60, 1),
            'monate': [{
                'monat': a.month,
                'jahr': a.year,
                'soll_minuten': a.target_minutes,
                'ist_minuten': a.actual_minutes,
                'differenz_minuten': a.overtime_minutes
            } for a in accounts]
        }

    elif tool_name == 'zeiterfassung_heute':
        emp_id = tool_input['employee_id']
        emp = Employee.query.get(emp_id)
        if not emp or emp.organization_id != org_id:
            return {'error': 'Mitarbeiter nicht gefunden'}

        today = date.today()
        entries = TimeEntry.query.filter_by(
            employee_id=emp_id, date=today
        ).all()

        total_mins = sum(e.worked_minutes or 0 for e in entries)
        return {
            'mitarbeiter': f'{emp.user.first_name} {emp.user.last_name}',
            'datum': today.strftime('%d.%m.%Y'),
            'eintraege': [{
                'von': e.clock_in.strftime('%H:%M') if e.clock_in else '-',
                'bis': e.clock_out.strftime('%H:%M') if e.clock_out else 'offen',
                'pause_minuten': e.break_minutes,
                'gearbeitet_minuten': e.worked_minutes
            } for e in entries],
            'total_minuten': total_mins,
            'total_stunden': round(total_mins / 60, 1)
        }

    elif tool_name == 'spesen_auflisten':
        emp_id = tool_input['employee_id']
        status = tool_input.get('status')
        emp = Employee.query.get(emp_id)
        if not emp or emp.organization_id != org_id:
            return {'error': 'Mitarbeiter nicht gefunden'}

        query = Expense.query.filter_by(employee_id=emp_id)
        if status:
            query = query.filter_by(status=status)

        expenses = query.order_by(Expense.date.desc()).limit(20).all()
        return {
            'mitarbeiter': f'{emp.user.first_name} {emp.user.last_name}',
            'anzahl': len(expenses),
            'spesen': [{
                'id': e.id,
                'datum': e.date.strftime('%d.%m.%Y'),
                'beschreibung': e.description,
                'kategorie': e.category,
                'betrag': e.amount,
                'status': e.status
            } for e in expenses],
            'total': round(sum(e.amount for e in expenses), 2)
        }

    elif tool_name == 'spesen_genehmigen':
        spesen_id = tool_input['spesen_id']
        expense = Expense.query.get(spesen_id)
        if not expense:
            return {'error': 'Spese nicht gefunden'}
        if expense.status != 'submitted':
            return {'error': f'Spese hat Status "{expense.status}" und kann nicht genehmigt werden'}

        expense.status = 'approved'
        expense.approved_at = datetime.now()
        db.session.commit()
        return {
            'ergebnis': 'Spese genehmigt',
            'spesen_id': spesen_id,
            'betrag': expense.amount,
            'beschreibung': expense.description
        }

    elif tool_name == 'ferienanspruch':
        emp_id = tool_input['employee_id']
        emp = Employee.query.get(emp_id)
        if not emp or emp.organization_id != org_id:
            return {'error': 'Mitarbeiter nicht gefunden'}

        quota = AbsenceQuota.query.filter_by(
            employee_id=emp_id, year=date.today().year, absence_type='vacation'
        ).first()

        if not quota:
            return {
                'mitarbeiter': f'{emp.user.first_name} {emp.user.last_name}',
                'ergebnis': 'Kein Ferienkontingent definiert'
            }

        return {
            'mitarbeiter': f'{emp.user.first_name} {emp.user.last_name}',
            'jahr': date.today().year,
            'total_tage': quota.total_days,
            'bezogen_tage': quota.used_days,
            'uebertrag_tage': quota.carryover_days,
            'rest_tage': quota.total_days - quota.used_days + quota.carryover_days
        }

    elif tool_name == 'sozialversicherungen_berechnen':
        bruttolohn = tool_input['bruttolohn']
        from services.payroll_service import calculate_social_insurance
        result = calculate_social_insurance(bruttolohn)
        return result

    elif tool_name == 'lohnausweis_generieren':
        emp_id = tool_input['employee_id']
        jahr = tool_input['jahr']
        emp = Employee.query.get(emp_id)
        if not emp or emp.organization_id != org_id:
            return {'error': 'Mitarbeiter nicht gefunden'}

        slips = Payslip.query.join(PayrollRun).filter(
            Payslip.employee_id == emp_id,
            PayrollRun.year == jahr
        ).all()

        if not slips:
            return {'error': f'Keine Lohnabrechnungen fuer {jahr} gefunden'}

        total_gross = sum(s.gross_total for s in slips)
        total_ahv = sum(s.ahv_iv_eo for s in slips)
        total_alv = sum(s.alv for s in slips)
        total_bvg = sum(s.bvg for s in slips)
        total_nbuv = sum(s.nbuv for s in slips)
        total_net = sum(s.net_salary for s in slips)

        return {
            'mitarbeiter': f'{emp.user.first_name} {emp.user.last_name}',
            'jahr': jahr,
            'monate': len(slips),
            'bruttolohn_jahres': round(total_gross, 2),
            'ahv_iv_eo_total': round(total_ahv, 2),
            'alv_total': round(total_alv, 2),
            'bvg_total': round(total_bvg, 2),
            'nbuv_total': round(total_nbuv, 2),
            'nettolohn_jahres': round(total_net, 2)
        }

    return {'error': f'Unbekanntes Tool: {tool_name}'}
