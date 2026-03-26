"""Lohnberechnungs-Service fuer Schweizer Lohnbuchhaltung"""
import json
from datetime import date, datetime
from models import db, Employee, EmployeeSalary, EmployeeChild, Payslip, PayrollRun, \
    Expense, TimeEntry, OvertimeAccount, JournalEntry, JournalEntryLine, Account, User

# Schweizer Sozialversicherungssaetze 2026
AHV_IV_EO_RATE = 0.053       # je 5.3% AN und AG
ALV_RATE = 0.011              # je 1.1% bis Grenze
ALV_CEILING = 148200          # Jahresmaximum fuer ALV
ALV2_RATE = 0.005             # Solidaritaetsbeitrag ueber Ceiling
BVG_COORDINATION_DEDUCTION = 25725  # Koordinationsabzug 2026
BVG_MIN_SALARY = 22050        # BVG-Eintrittsschwelle
FAK_RATE = 0.02               # Familienzulagen-Beitrag AG (ca. 2% je nach Kanton)
VK_AHV_RATE = 0.004           # Verwaltungskosten AHV AG (0.3-0.5%)
UVG_RATE = 0.015              # Berufsunfallversicherung AG

MONTH_NAMES = {
    1: 'Januar', 2: 'Februar', 3: 'März', 4: 'April',
    5: 'Mai', 6: 'Juni', 7: 'Juli', 8: 'August',
    9: 'September', 10: 'Oktober', 11: 'November', 12: 'Dezember'
}


def get_current_salary(employee_id, ref_date=None):
    """Holt das aktuelle Lohnprofil eines Mitarbeiters"""
    if ref_date is None:
        ref_date = date.today()
    salary = EmployeeSalary.query.filter(
        EmployeeSalary.employee_id == employee_id,
        EmployeeSalary.valid_from <= ref_date,
        db.or_(EmployeeSalary.valid_to.is_(None), EmployeeSalary.valid_to >= ref_date)
    ).order_by(EmployeeSalary.valid_from.desc()).first()
    return salary


def calculate_payslip(employee, month, year, bonus=0):
    """Berechnet Lohnabrechnung fuer einen Mitarbeiter"""
    ref_date = date(year, month, 1)
    salary = get_current_salary(employee.id, ref_date)
    if not salary:
        return None

    pensum = employee.pensum_percent or 100
    pensum_factor = pensum / 100.0

    # 1. Grundlohn
    if salary.salary_type == 'monthly':
        gross_salary = salary.amount * pensum_factor
    else:
        # Stundenlohn: Stunden aus Zeiterfassung
        time_entries = TimeEntry.query.filter(
            TimeEntry.employee_id == employee.id,
            db.extract('year', TimeEntry.date) == year,
            db.extract('month', TimeEntry.date) == month
        ).all()
        total_hours = sum(e.worked_minutes or 0 for e in time_entries) / 60.0
        gross_salary = total_hours * (salary.hourly_rate or salary.amount)

    # 2. 13. Monatslohn-Anteil (1/12)
    thirteenth_month = 0
    if salary.thirteenth_month:
        annual_salary = salary.amount * 12 * pensum_factor if salary.salary_type == 'monthly' else gross_salary
        thirteenth_month = round(annual_salary / 12, 2)  # 1/12 pro Monat

    # 3. Kinderzulagen
    children = EmployeeChild.query.filter_by(employee_id=employee.id).all()
    child_allowance = sum(c.allowance_amount or 0 for c in children)

    # 4. Spesen (genehmigte, noch nicht ausbezahlte)
    approved_expenses = Expense.query.filter(
        Expense.employee_id == employee.id,
        Expense.status == 'approved',
        Expense.paid_via.is_(None)
    ).all()
    expenses_total = sum(e.amount for e in approved_expenses)

    # 5. Ueberstunden-Auszahlung (0 default, manuell setzbar)
    overtime_payout = 0

    # 6. Boni
    bonuses = bonus

    # === Bruttolohn Total ===
    gross_total = round(gross_salary + thirteenth_month + child_allowance + bonuses + expenses_total + overtime_payout, 2)

    # === Abzuege AN ===
    # Basis fuer SV-Beitraege: Brutto ohne Spesen und Kinderzulagen
    sv_basis = gross_salary + thirteenth_month + bonuses + overtime_payout

    # AHV/IV/EO: 5.3%
    ahv_iv_eo = round(sv_basis * AHV_IV_EO_RATE, 2)

    # ALV: 1.1% bis Ceiling (Jahresbasis pruefen)
    annual_salary_for_alv = sv_basis * 12
    if annual_salary_for_alv <= ALV_CEILING:
        alv = round(sv_basis * ALV_RATE, 2)
        alv2 = 0
    else:
        alv = round((ALV_CEILING / 12) * ALV_RATE, 2)
        excess = sv_basis - (ALV_CEILING / 12)
        alv2 = round(excess * ALV2_RATE, 2) if excess > 0 else 0

    # BVG: gemäss Beitragssatz auf koordiniertem Lohn
    bvg_rate = (salary.bvg_rate or 7.0) / 100.0
    annual_salary_for_bvg = sv_basis * 12
    if annual_salary_for_bvg >= BVG_MIN_SALARY:
        coordinated_salary = max(0, annual_salary_for_bvg - BVG_COORDINATION_DEDUCTION)
        bvg = round((coordinated_salary * bvg_rate) / 12, 2)
    else:
        bvg = 0

    # NBUV: gemäss Satz
    nbuv_rate = (salary.nbuv_rate or 1.5) / 100.0
    nbuv = round(sv_basis * nbuv_rate, 2)

    # KTG: gemäss Satz (AN-Anteil, 50% des Gesamtsatzes)
    ktg_rate = (salary.ktg_rate or 0.5) / 100.0
    ktg = round(sv_basis * ktg_rate, 2)

    # Quellensteuer
    withholding_tax = 0
    if salary.withholding_tax:
        # Vereinfacht: Pauschal 10% als Platzhalter (wird korrekt mit Tarif-Tabelle berechnet)
        withholding_tax = round(sv_basis * 0.10, 2)

    deductions_total = round(ahv_iv_eo + alv + alv2 + bvg + nbuv + ktg + withholding_tax, 2)

    # === Nettolohn ===
    net_salary = round(gross_total - deductions_total, 2)

    # === Arbeitgeber-Beitraege ===
    employer_ahv_iv_eo = round(sv_basis * AHV_IV_EO_RATE, 2)
    employer_alv = alv  # Gleich wie AN
    employer_bvg = bvg  # Gleich wie AN (paritaetisch)
    employer_uvg = round(sv_basis * UVG_RATE, 2)
    employer_ktg = ktg  # Gleich wie AN
    employer_fak = round(sv_basis * FAK_RATE, 2)
    employer_vk = round(sv_basis * VK_AHV_RATE, 2)
    employer_total = round(employer_ahv_iv_eo + employer_alv + employer_bvg +
                          employer_uvg + employer_ktg + employer_fak + employer_vk, 2)

    return {
        'gross_salary': gross_salary,
        'thirteenth_month': thirteenth_month,
        'child_allowance': child_allowance,
        'bonuses': bonuses,
        'expenses_total': expenses_total,
        'overtime_payout': overtime_payout,
        'gross_total': gross_total,
        'ahv_iv_eo': ahv_iv_eo,
        'alv': alv,
        'alv2': alv2,
        'bvg': bvg,
        'nbuv': nbuv,
        'ktg': ktg,
        'withholding_tax': withholding_tax,
        'deductions_total': deductions_total,
        'net_salary': net_salary,
        'employer_ahv_iv_eo': employer_ahv_iv_eo,
        'employer_alv': employer_alv,
        'employer_bvg': employer_bvg,
        'employer_uvg': employer_uvg,
        'employer_ktg': employer_ktg,
        'employer_fak': employer_fak,
        'employer_vk': employer_vk,
        'employer_total': employer_total,
        'sv_basis': sv_basis,
        'pensum_percent': pensum,
        'salary_type': salary.salary_type,
        'iban': salary.iban,
        'ahv_number': salary.ahv_number,
    }


def create_payroll_run(org_id, year, month, employee_ids=None):
    """Erstellt einen neuen Lohnlauf und berechnet alle Lohnabrechnungen"""
    # Pruefen ob bereits ein Lohnlauf existiert
    existing = PayrollRun.query.filter_by(
        organization_id=org_id, year=year, month=month
    ).first()
    if existing:
        return existing, 'Lohnlauf existiert bereits'

    run = PayrollRun(
        organization_id=org_id,
        year=year,
        month=month,
        status='draft'
    )
    db.session.add(run)
    db.session.flush()

    # Mitarbeiter laden
    if employee_ids:
        employees = Employee.query.filter(
            Employee.organization_id == org_id,
            Employee.id.in_(employee_ids),
            Employee.is_active == True
        ).all()
    else:
        employees = Employee.query.filter_by(
            organization_id=org_id, is_active=True
        ).all()

    total_gross = 0
    total_net = 0
    total_employer = 0

    for emp in employees:
        data = calculate_payslip(emp, month, year)
        if not data:
            continue

        payslip = Payslip(
            payroll_run_id=run.id,
            employee_id=emp.id,
            gross_salary=data['gross_salary'],
            thirteenth_month=data['thirteenth_month'],
            child_allowance=data['child_allowance'],
            bonuses=data['bonuses'],
            expenses_total=data['expenses_total'],
            overtime_payout=data['overtime_payout'],
            gross_total=data['gross_total'],
            ahv_iv_eo=data['ahv_iv_eo'],
            alv=data['alv'],
            alv2=data.get('alv2', 0),
            bvg=data['bvg'],
            nbuv=data['nbuv'],
            ktg=data['ktg'],
            withholding_tax=data['withholding_tax'],
            deductions_total=data['deductions_total'],
            net_salary=data['net_salary'],
            employer_ahv_iv_eo=data['employer_ahv_iv_eo'],
            employer_alv=data['employer_alv'],
            employer_bvg=data['employer_bvg'],
            employer_uvg=data['employer_uvg'],
            employer_ktg=data['employer_ktg'],
            employer_fak=data['employer_fak'],
            employer_vk=data['employer_vk'],
            employer_total=data['employer_total'],
            details_json=json.dumps(data, default=str, ensure_ascii=False)
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
    return run, None


def book_payroll(payroll_run, user_id=None):
    """Bucht Lohnlauf in die Finanzbuchhaltung"""
    org_id = payroll_run.organization_id

    # Konten finden
    konto_loehne = Account.query.filter_by(organization_id=org_id, account_number='5000').first()
    konto_sv_ag = Account.query.filter_by(organization_id=org_id, account_number='5700').first()
    konto_bank = Account.query.filter_by(organization_id=org_id, account_number='1020').first()
    konto_sv_verb = Account.query.filter_by(organization_id=org_id, account_number='2270').first()

    if not all([konto_loehne, konto_bank]):
        return None, 'Konten 5000 oder 1020 nicht gefunden'

    # Falls SV-Konten fehlen, auf Bank buchen
    if not konto_sv_ag:
        konto_sv_ag = konto_loehne
    if not konto_sv_verb:
        konto_sv_verb = konto_bank

    month_name = MONTH_NAMES.get(payroll_run.month, str(payroll_run.month))

    # Naechste Buchungsnummer
    from services.accounting_service import get_next_entry_number
    entry_number = get_next_entry_number(org_id)

    entry = JournalEntry(
        organization_id=org_id,
        entry_number=entry_number,
        date=date(payroll_run.year, payroll_run.month, 25),
        description=f'Lohnlauf {month_name} {payroll_run.year}',
        source='salary',
        source_id=payroll_run.id,
        created_by_id=user_id
    )
    db.session.add(entry)
    db.session.flush()

    # Soll: Loehne (Brutto)
    db.session.add(JournalEntryLine(
        entry_id=entry.id,
        account_id=konto_loehne.id,
        debit=payroll_run.total_gross,
        credit=0,
        description=f'Bruttolöhne {month_name} {payroll_run.year}'
    ))

    # Soll: Sozialversicherungen AG
    if payroll_run.total_employer_contributions > 0:
        db.session.add(JournalEntryLine(
            entry_id=entry.id,
            account_id=konto_sv_ag.id,
            debit=payroll_run.total_employer_contributions,
            credit=0,
            description=f'AG-Beiträge SV {month_name} {payroll_run.year}'
        ))

    # Haben: Bank (Nettolohn-Auszahlung)
    db.session.add(JournalEntryLine(
        entry_id=entry.id,
        account_id=konto_bank.id,
        debit=0,
        credit=payroll_run.total_net,
        description=f'Lohnauszahlung {month_name} {payroll_run.year}'
    ))

    # Haben: SV-Verbindlichkeiten (AN-Abzuege + AG-Beitraege)
    sv_total = round(payroll_run.total_gross - payroll_run.total_net + payroll_run.total_employer_contributions, 2)
    if sv_total > 0:
        db.session.add(JournalEntryLine(
            entry_id=entry.id,
            account_id=konto_sv_verb.id,
            debit=0,
            credit=sv_total,
            description=f'SV-Verbindlichkeiten {month_name} {payroll_run.year}'
        ))

    payroll_run.journal_entry_id = entry.id
    db.session.commit()
    return entry, None


def calculate_social_insurance(bruttolohn):
    """Berechnet SV-Beitraege fuer einen gegebenen Bruttolohn (Hilfsfunktion)"""
    ahv = round(bruttolohn * AHV_IV_EO_RATE, 2)
    annual = bruttolohn * 12
    if annual <= ALV_CEILING:
        alv = round(bruttolohn * ALV_RATE, 2)
    else:
        alv = round((ALV_CEILING / 12) * ALV_RATE, 2)

    # BVG (Standard 7%)
    if annual >= BVG_MIN_SALARY:
        coord = max(0, annual - BVG_COORDINATION_DEDUCTION)
        bvg = round((coord * 0.07) / 12, 2)
    else:
        bvg = 0

    return {
        'bruttolohn': bruttolohn,
        'ahv_iv_eo_an': ahv,
        'ahv_iv_eo_ag': ahv,
        'alv_an': alv,
        'alv_ag': alv,
        'bvg_an': bvg,
        'bvg_ag': bvg,
        'total_an': round(ahv + alv + bvg, 2),
        'total_ag': round(ahv + alv + bvg, 2),
    }
