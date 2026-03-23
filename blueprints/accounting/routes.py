"""Routen fuer die Finanzbuchhaltung"""
import json
from datetime import datetime, date, timedelta
from flask import render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from blueprints.accounting import accounting_bp
from models import (db, Account, JournalEntry, JournalEntryLine, CreditorInvoice,
                    FixedAsset, CostCenter, PeriodLock, Invoice, Payment, Contact)
from services.accounting_service import (
    get_next_entry_number, is_period_locked, get_account_balance,
    create_journal_entry, storno_entry, run_depreciation,
    generate_balance_sheet, generate_income_statement, generate_vat_report,
    get_open_debtors, get_open_creditors, get_liquidity
)
from utils.auth import check_org


# ============================================================
# Dashboard / Uebersicht
# ============================================================

@accounting_bp.route('/')
@login_required
def index():
    """Finanzbuchhaltung-Uebersicht"""
    org_id = current_user.organization_id
    today = date.today()
    month_start = date(today.year, today.month, 1)

    # Liquiditaet
    liquidity = get_liquidity(org_id)

    # Offene Debitoren
    debtors = get_open_debtors(org_id)
    total_debitoren = debtors.get('total', 0)

    # Offene Kreditoren
    creditors = get_open_creditors(org_id)
    total_kreditoren = sum(c['betrag'] for c in creditors)

    # Umsatz und Gewinn/Verlust aktueller Monat
    income_stmt = generate_income_statement(org_id, month_start, today)
    umsatz_monat = income_stmt['total_ertrag']
    gewinn_monat = income_stmt['gewinn_verlust']

    # Letzte Buchungen
    letzte_buchungen = JournalEntry.query.filter_by(organization_id=org_id) \
        .order_by(JournalEntry.date.desc(), JournalEntry.id.desc()).limit(10).all()

    return render_template('accounting/index.html',
                           liquidity=liquidity,
                           total_debitoren=total_debitoren,
                           total_kreditoren=total_kreditoren,
                           umsatz_monat=umsatz_monat,
                           gewinn_monat=gewinn_monat,
                           letzte_buchungen=letzte_buchungen)


# ============================================================
# Kontenplan
# ============================================================

@accounting_bp.route('/chart')
@login_required
def chart_of_accounts():
    """Kontenplan anzeigen"""
    org_id = current_user.organization_id
    search = request.args.get('search', '')

    query = Account.query.filter_by(organization_id=org_id)
    if search:
        query = query.filter(
            db.or_(
                Account.account_number.contains(search),
                Account.name.ilike(f'%{search}%')
            )
        )

    accounts = query.order_by(Account.account_number).all()

    # Salden berechnen (Batch-Query statt N+1)
    account_balances = {}
    if accounts:
        account_ids = [acc.id for acc in accounts]
        balance_results = db.session.query(
            JournalEntryLine.account_id,
            db.func.coalesce(db.func.sum(JournalEntryLine.debit), 0),
            db.func.coalesce(db.func.sum(JournalEntryLine.credit), 0)
        ).filter(
            JournalEntryLine.account_id.in_(account_ids)
        ).group_by(JournalEntryLine.account_id).all()
        for acc_id, total_debit, total_credit in balance_results:
            account_balances[acc_id] = total_debit - total_credit
        # Konten ohne Buchungen auf 0 setzen
        for acc in accounts:
            if acc.id not in account_balances:
                account_balances[acc.id] = 0

    # Kategorien
    categories = {
        '1': {'name': 'Aktiven', 'accounts': []},
        '2': {'name': 'Passiven', 'accounts': []},
        '3': {'name': 'Betriebsertrag', 'accounts': []},
        '4': {'name': 'Aufwand Material/Waren', 'accounts': []},
        '5': {'name': 'Personalaufwand', 'accounts': []},
        '6': {'name': 'Übriger Betriebsaufwand', 'accounts': []},
        '7': {'name': 'Betriebsfremder Ertrag/Aufwand', 'accounts': []},
        '8': {'name': 'Ausserordentlicher Ertrag/Aufwand', 'accounts': []},
        '9': {'name': 'Abschluss', 'accounts': []}
    }

    for acc in accounts:
        cat_key = acc.account_number[0] if acc.account_number else '9'
        if cat_key in categories:
            categories[cat_key]['accounts'].append(acc)

    return render_template('accounting/chart_of_accounts.html',
                           categories=categories,
                           account_balances=account_balances,
                           search=search)


@accounting_bp.route('/chart/create', methods=['POST'])
@login_required
def create_account():
    """Neues Konto erstellen"""
    org_id = current_user.organization_id
    number = request.form.get('account_number', '').strip()
    name = request.form.get('name', '').strip()
    account_type = request.form.get('account_type', 'expense')
    vat_code = request.form.get('vat_code', '')
    parent_id = request.form.get('parent_account_id')

    if not number or not name:
        flash('Kontonummer und Name sind erforderlich.', 'error')
        return redirect(url_for('accounting.chart_of_accounts'))

    existing = Account.query.filter_by(organization_id=org_id, account_number=number).first()
    if existing:
        flash(f'Konto {number} existiert bereits.', 'error')
        return redirect(url_for('accounting.chart_of_accounts'))

    account = Account(
        organization_id=org_id,
        account_number=number,
        name=name,
        account_type=account_type,
        vat_code=vat_code if vat_code else None,
        parent_account_id=int(parent_id) if parent_id else None
    )
    db.session.add(account)
    db.session.commit()
    flash(f'Konto {number} {name} wurde erstellt.', 'success')
    return redirect(url_for('accounting.chart_of_accounts'))


@accounting_bp.route('/chart/<int:id>/edit', methods=['POST'])
@login_required
def edit_account(id):
    """Konto bearbeiten"""
    account = Account.query.get_or_404(id)
    check_org(account)
    account.name = request.form.get('name', account.name).strip()
    account.account_type = request.form.get('account_type', account.account_type)
    account.vat_code = request.form.get('vat_code', '') or None
    account.is_active = request.form.get('is_active') == 'on'
    db.session.commit()
    flash(f'Konto {account.account_number} wurde aktualisiert.', 'success')
    return redirect(url_for('accounting.chart_of_accounts'))


@accounting_bp.route('/chart/<int:id>/statement')
@login_required
def account_statement(id):
    """Kontoauszug anzeigen"""
    account = Account.query.get_or_404(id)
    check_org(account)
    von = request.args.get('von', date(date.today().year, 1, 1).isoformat())
    bis = request.args.get('bis', date.today().isoformat())

    von_date = datetime.strptime(von, '%Y-%m-%d').date()
    bis_date = datetime.strptime(bis, '%Y-%m-%d').date()

    lines = JournalEntryLine.query.join(JournalEntry).filter(
        JournalEntryLine.account_id == id,
        JournalEntry.date >= von_date,
        JournalEntry.date <= bis_date
    ).order_by(JournalEntry.date, JournalEntry.id).all()

    balance = get_account_balance(id, bis_date)

    return render_template('accounting/account_statement.html',
                           account=account, lines=lines,
                           von=von, bis=bis, balance=balance)


# ============================================================
# Buchungsjournal
# ============================================================

@accounting_bp.route('/journal')
@login_required
def journal():
    """Buchungsjournal anzeigen"""
    org_id = current_user.organization_id
    von = request.args.get('von', date(date.today().year, 1, 1).isoformat())
    bis = request.args.get('bis', date.today().isoformat())
    search = request.args.get('search', '')
    konto = request.args.get('konto', '')

    von_date = datetime.strptime(von, '%Y-%m-%d').date()
    bis_date = datetime.strptime(bis, '%Y-%m-%d').date()

    query = JournalEntry.query.filter_by(organization_id=org_id) \
        .filter(JournalEntry.date >= von_date, JournalEntry.date <= bis_date)

    if search:
        query = query.filter(
            db.or_(
                JournalEntry.description.ilike(f'%{search}%'),
                JournalEntry.entry_number.ilike(f'%{search}%'),
                JournalEntry.reference.ilike(f'%{search}%')
            )
        )

    if konto:
        query = query.filter(
            JournalEntry.lines.any(JournalEntryLine.account_id == int(konto))
        )

    sort = request.args.get('sort', 'date_desc')
    if sort == 'date_asc':
        query = query.order_by(JournalEntry.date.asc(), JournalEntry.id.asc())
    else:
        query = query.order_by(JournalEntry.date.desc(), JournalEntry.id.desc())

    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = 25
    total = query.count()
    entries = query.offset((page - 1) * per_page).limit(per_page).all()
    total_pages = (total + per_page - 1) // per_page

    accounts = Account.query.filter_by(organization_id=org_id, is_active=True) \
        .order_by(Account.account_number).all()

    return render_template('accounting/journal.html',
                           entries=entries, accounts=accounts,
                           von=von, bis=bis, search=search, konto=konto, sort=sort,
                           page=page, total_pages=total_pages, total=total)


@accounting_bp.route('/journal/create', methods=['GET', 'POST'])
@login_required
def create_booking():
    """Neue Buchung erstellen"""
    org_id = current_user.organization_id
    accounts = Account.query.filter_by(organization_id=org_id, is_active=True) \
        .order_by(Account.account_number).all()
    cost_centers = CostCenter.query.filter_by(organization_id=org_id, is_active=True).all()

    if request.method == 'POST':
        entry_date_str = request.form.get('date', date.today().isoformat())
        entry_date = datetime.strptime(entry_date_str, '%Y-%m-%d').date()
        description = request.form.get('description', '').strip()
        reference = request.form.get('reference', '').strip()
        is_recurring = request.form.get('is_recurring') == 'on'
        recurring_interval = request.form.get('recurring_interval', '')

        if is_period_locked(org_id, entry_date):
            flash('Periode ist gesperrt. Keine Buchungen möglich.', 'error')
            return redirect(url_for('accounting.create_booking'))

        # Buchungszeilen aus Formular
        lines_data = []
        line_idx = 0
        while True:
            acc_id = request.form.get(f'lines-{line_idx}-account_id')
            if acc_id is None:
                break
            debit = float(request.form.get(f'lines-{line_idx}-debit', 0) or 0)
            credit = float(request.form.get(f'lines-{line_idx}-credit', 0) or 0)
            vat_code = request.form.get(f'lines-{line_idx}-vat_code', '')
            vat_amount = float(request.form.get(f'lines-{line_idx}-vat_amount', 0) or 0)
            cc_id = request.form.get(f'lines-{line_idx}-cost_center_id', '')
            line_desc = request.form.get(f'lines-{line_idx}-description', '')

            if int(acc_id) > 0 and (debit > 0 or credit > 0):
                lines_data.append({
                    'account_id': int(acc_id),
                    'debit': debit,
                    'credit': credit,
                    'vat_code': vat_code if vat_code else None,
                    'vat_amount': vat_amount,
                    'cost_center_id': int(cc_id) if cc_id else None,
                    'description': line_desc
                })
            line_idx += 1

        # Einfache Buchung (Soll/Haben-Felder)
        if not lines_data:
            soll_id = request.form.get('soll_account_id')
            haben_id = request.form.get('haben_account_id')
            betrag = float(request.form.get('betrag', 0) or 0)
            vat_code = request.form.get('vat_code', '')
            vat_amount = float(request.form.get('vat_amount', 0) or 0)

            if soll_id and haben_id and betrag > 0:
                lines_data = [
                    {'account_id': int(soll_id), 'debit': betrag, 'credit': 0,
                     'vat_code': vat_code if vat_code else None, 'vat_amount': vat_amount},
                    {'account_id': int(haben_id), 'debit': 0, 'credit': betrag}
                ]

        if not lines_data:
            flash('Mindestens eine Buchungszeile ist erforderlich.', 'error')
            return redirect(url_for('accounting.create_booking'))

        entry, error = create_journal_entry(
            org_id, entry_date, description, lines_data,
            reference=reference or None, created_by_id=current_user.id
        )

        if error:
            flash(error, 'error')
            return redirect(url_for('accounting.create_booking'))

        if is_recurring and recurring_interval:
            entry.is_recurring = True
            entry.recurring_interval = recurring_interval
            db.session.commit()

        flash(f'Buchung {entry.entry_number} wurde erstellt.', 'success')
        return redirect(url_for('accounting.journal'))

    next_number = get_next_entry_number(org_id)
    return render_template('accounting/booking_form.html',
                           accounts=accounts, cost_centers=cost_centers,
                           next_number=next_number)


@accounting_bp.route('/journal/<int:id>/storno', methods=['POST'])
@login_required
def storno_booking(id):
    """Buchung stornieren"""
    entry_obj = JournalEntry.query.get_or_404(id)
    check_org(entry_obj)
    entry, error = storno_entry(id, created_by_id=current_user.id)
    if error:
        flash(error, 'error')
    else:
        flash(f'Stornobuchung {entry.entry_number} wurde erstellt.', 'success')
    return redirect(url_for('accounting.journal'))


# ============================================================
# Debitoren
# ============================================================

@accounting_bp.route('/debtors')
@login_required
def debtors():
    """Debitoren-Uebersicht"""
    org_id = current_user.organization_id
    ageing = get_open_debtors(org_id)

    # Alle offenen Rechnungen (paginiert)
    page = request.args.get('page', 1, type=int)
    per_page = 25
    query = Invoice.query.filter(
        Invoice.organization_id == org_id,
        Invoice.status.in_(['sent', 'overdue', 'partially_paid']),
        Invoice.amount_open > 0
    ).order_by(Invoice.due_date)
    total = query.count()
    total_pages = (total + per_page - 1) // per_page
    invoices = query.offset((page - 1) * per_page).limit(per_page).all()

    return render_template('accounting/debtors.html',
                           ageing=ageing, invoices=invoices,
                           page=page, total_pages=total_pages)


# ============================================================
# Kreditoren
# ============================================================

@accounting_bp.route('/creditors')
@login_required
def creditors():
    """Kreditoren-Uebersicht"""
    org_id = current_user.organization_id
    status_filter = request.args.get('status', '')

    query = CreditorInvoice.query.filter_by(organization_id=org_id)
    if status_filter:
        query = query.filter_by(status=status_filter)

    page = request.args.get('page', 1, type=int)
    per_page = 25
    total = query.count()
    total_pages = (total + per_page - 1) // per_page
    creditor_invoices = query.order_by(CreditorInvoice.due_date).offset((page - 1) * per_page).limit(per_page).all()

    # Dropdowns fuer Formular (kleine Mengen, keine Pagination noetig)
    contacts = Contact.query.filter_by(organization_id=org_id).order_by(Contact.company_name, Contact.last_name).all()
    accounts = Account.query.filter_by(organization_id=org_id, is_active=True) \
        .filter(Account.account_number.like('4%') | Account.account_number.like('5%') |
                Account.account_number.like('6%')) \
        .order_by(Account.account_number).all()

    # Gesamtsumme offener Kreditoren (ueber alle, nicht nur aktuelle Seite)
    total_open = db.session.query(db.func.coalesce(db.func.sum(CreditorInvoice.amount), 0)).filter(
        CreditorInvoice.organization_id == org_id,
        CreditorInvoice.status.in_(['open', 'approved'])
    ).scalar()

    return render_template('accounting/creditors.html',
                           creditor_invoices=creditor_invoices,
                           contacts=contacts, accounts=accounts,
                           status_filter=status_filter, total_open=total_open,
                           page=page, total_pages=total_pages)


@accounting_bp.route('/creditors/create', methods=['POST'])
@login_required
def create_creditor():
    """Kreditoren-Rechnung erfassen"""
    org_id = current_user.organization_id

    contact_id = request.form.get('contact_id')
    creditor_name = request.form.get('creditor_name', '').strip()
    invoice_number = request.form.get('invoice_number', '').strip()
    invoice_date = datetime.strptime(request.form.get('invoice_date', date.today().isoformat()), '%Y-%m-%d').date()
    due_date_str = request.form.get('due_date', '')
    amount = float(request.form.get('amount', 0) or 0)
    vat_amount = float(request.form.get('vat_amount', 0) or 0)
    account_id = request.form.get('account_id')
    notes = request.form.get('notes', '')

    due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date() if due_date_str else invoice_date + timedelta(days=30)

    creditor = CreditorInvoice(
        organization_id=org_id,
        contact_id=int(contact_id) if contact_id else None,
        creditor_name=creditor_name,
        invoice_number=invoice_number,
        invoice_date=invoice_date,
        due_date=due_date,
        amount=amount,
        vat_amount=vat_amount,
        account_id=int(account_id) if account_id else None,
        notes=notes
    )
    db.session.add(creditor)
    db.session.flush()

    # Automatische Buchung: Aufwand an Kreditoren
    if account_id:
        kreditoren_account = Account.query.filter_by(
            organization_id=org_id, account_number='2000'
        ).first()
        aufwand_account = Account.query.filter_by(id=int(account_id), organization_id=org_id).first()

        if kreditoren_account and aufwand_account:
            lines = [
                {'account_id': aufwand_account.id, 'debit': amount, 'credit': 0,
                 'description': f'Lieferantenrechnung {invoice_number}'},
                {'account_id': kreditoren_account.id, 'debit': 0, 'credit': amount,
                 'description': f'Lieferantenrechnung {invoice_number}'}
            ]

            # Vorsteuer buchen
            if vat_amount > 0:
                vorsteuer_account = Account.query.filter_by(
                    organization_id=org_id, account_number='1170'
                ).first()
                if vorsteuer_account:
                    lines[0]['debit'] = amount - vat_amount
                    lines.append({
                        'account_id': vorsteuer_account.id, 'debit': vat_amount, 'credit': 0,
                        'vat_code': 'vorsteuer', 'vat_amount': vat_amount,
                        'description': f'Vorsteuer {invoice_number}'
                    })

            entry, error = create_journal_entry(
                org_id, invoice_date,
                f'Kreditor: {creditor_name or invoice_number}',
                lines, source='creditor', source_id=creditor.id
            )
            if entry:
                creditor.journal_entry_id = entry.id

    db.session.commit()
    flash(f'Kreditoren-Rechnung {invoice_number} wurde erfasst.', 'success')
    return redirect(url_for('accounting.creditors'))


@accounting_bp.route('/creditors/<int:id>/approve', methods=['POST'])
@login_required
def approve_creditor(id):
    """Kreditoren-Rechnung freigeben"""
    creditor = CreditorInvoice.query.get_or_404(id)
    check_org(creditor)
    creditor.status = 'approved'
    db.session.commit()
    flash('Rechnung wurde freigegeben.', 'success')
    return redirect(url_for('accounting.creditors'))


@accounting_bp.route('/creditors/<int:id>/pay', methods=['POST'])
@login_required
def pay_creditor(id):
    """Kreditoren-Rechnung als bezahlt markieren"""
    org_id = current_user.organization_id
    creditor = CreditorInvoice.query.get_or_404(id)
    check_org(creditor)

    # Buchung: Kreditoren an Bank
    kreditoren_account = Account.query.filter_by(
        organization_id=org_id, account_number='2000'
    ).first()
    bank_account = Account.query.filter_by(
        organization_id=org_id, account_number='1020'
    ).first()

    if kreditoren_account and bank_account:
        lines = [
            {'account_id': kreditoren_account.id, 'debit': creditor.amount, 'credit': 0,
             'description': f'Zahlung Kreditor {creditor.invoice_number}'},
            {'account_id': bank_account.id, 'debit': 0, 'credit': creditor.amount,
             'description': f'Zahlung Kreditor {creditor.invoice_number}'}
        ]
        entry, error = create_journal_entry(
            org_id, date.today(),
            f'Kreditor-Zahlung: {creditor.creditor_name or creditor.invoice_number}',
            lines, source='creditor_payment', source_id=creditor.id,
            created_by_id=current_user.id
        )
        if entry:
            creditor.payment_journal_entry_id = entry.id

    creditor.status = 'paid'
    db.session.commit()
    flash('Rechnung wurde als bezahlt markiert.', 'success')
    return redirect(url_for('accounting.creditors'))


@accounting_bp.route('/creditors/payment-run', methods=['POST'])
@login_required
def payment_run():
    """Zahlungslauf: Alle freigegebenen Kreditoren bezahlen"""
    org_id = current_user.organization_id
    approved = CreditorInvoice.query.filter_by(
        organization_id=org_id, status='approved'
    ).all()

    count = 0
    for creditor in approved:
        kreditoren_account = Account.query.filter_by(
            organization_id=org_id, account_number='2000'
        ).first()
        bank_account = Account.query.filter_by(
            organization_id=org_id, account_number='1020'
        ).first()

        if kreditoren_account and bank_account:
            lines = [
                {'account_id': kreditoren_account.id, 'debit': creditor.amount, 'credit': 0,
                 'description': f'Zahlungslauf: {creditor.creditor_name}'},
                {'account_id': bank_account.id, 'debit': 0, 'credit': creditor.amount,
                 'description': f'Zahlungslauf: {creditor.creditor_name}'}
            ]
            entry, error = create_journal_entry(
                org_id, date.today(),
                f'Zahlungslauf: {creditor.creditor_name or creditor.invoice_number}',
                lines, source='creditor_payment', source_id=creditor.id,
                created_by_id=current_user.id
            )
            if entry:
                creditor.payment_journal_entry_id = entry.id
                creditor.status = 'paid'
                count += 1

    db.session.commit()
    flash(f'Zahlungslauf abgeschlossen: {count} Rechnungen bezahlt.', 'success')
    return redirect(url_for('accounting.creditors'))


# ============================================================
# Mehrwertsteuer
# ============================================================

@accounting_bp.route('/vat')
@login_required
def vat():
    """MwSt-Uebersicht"""
    org_id = current_user.organization_id
    today = date.today()

    # Standard: aktuelles Quartal
    quarter = (today.month - 1) // 3
    quarter_start = date(today.year, quarter * 3 + 1, 1)
    if today.month <= 3:
        quarter_end = date(today.year, 3, 31)
    elif today.month <= 6:
        quarter_end = date(today.year, 6, 30)
    elif today.month <= 9:
        quarter_end = date(today.year, 9, 30)
    else:
        quarter_end = date(today.year, 12, 31)

    von = request.args.get('von', quarter_start.isoformat())
    bis = request.args.get('bis', quarter_end.isoformat())
    von_date = datetime.strptime(von, '%Y-%m-%d').date()
    bis_date = datetime.strptime(bis, '%Y-%m-%d').date()

    report = generate_vat_report(org_id, von_date, bis_date)

    # MwSt-relevante Buchungen
    vat_entries = JournalEntryLine.query.join(JournalEntry).filter(
        JournalEntry.organization_id == org_id,
        JournalEntry.date >= von_date,
        JournalEntry.date <= bis_date,
        JournalEntryLine.vat_code.isnot(None),
        JournalEntryLine.vat_code != ''
    ).order_by(JournalEntry.date).all()

    return render_template('accounting/vat.html',
                           report=report, vat_entries=vat_entries,
                           von=von, bis=bis)


# ============================================================
# Anlagenbuchhaltung
# ============================================================

@accounting_bp.route('/assets')
@login_required
def assets():
    """Anlagen-Uebersicht"""
    org_id = current_user.organization_id
    query = FixedAsset.query.filter_by(organization_id=org_id)
    page = request.args.get('page', 1, type=int)
    per_page = 25
    total = query.count()
    total_pages = (total + per_page - 1) // per_page
    fixed_assets = query.order_by(FixedAsset.category, FixedAsset.name) \
        .offset((page - 1) * per_page).limit(per_page).all()

    # Dropdowns fuer Formular
    accounts = Account.query.filter_by(organization_id=org_id, is_active=True) \
        .filter(Account.account_number.like('15%')) \
        .order_by(Account.account_number).all()

    depreciation_accounts = Account.query.filter_by(organization_id=org_id, is_active=True) \
        .filter(Account.account_number == '6800').all()

    # Gesamtsummen ueber alle Assets (nicht nur aktuelle Seite)
    totals = db.session.query(
        db.func.coalesce(db.func.sum(FixedAsset.acquisition_value), 0),
        db.func.coalesce(db.func.sum(FixedAsset.current_book_value), 0)
    ).filter_by(organization_id=org_id).first()
    total_acquisition = totals[0]
    total_book = totals[1]

    return render_template('accounting/assets.html',
                           fixed_assets=fixed_assets, accounts=accounts,
                           depreciation_accounts=depreciation_accounts,
                           total_acquisition=total_acquisition, total_book=total_book,
                           page=page, total_pages=total_pages)


@accounting_bp.route('/assets/create', methods=['POST'])
@login_required
def create_asset():
    """Anlagegut erfassen"""
    org_id = current_user.organization_id

    asset = FixedAsset(
        organization_id=org_id,
        name=request.form.get('name', '').strip(),
        category=request.form.get('category', 'furniture'),
        acquisition_date=datetime.strptime(request.form.get('acquisition_date', date.today().isoformat()), '%Y-%m-%d').date(),
        acquisition_value=float(request.form.get('acquisition_value', 0) or 0),
        useful_life_years=int(request.form.get('useful_life_years', 5) or 5),
        depreciation_method=request.form.get('depreciation_method', 'linear'),
        account_id=int(request.form.get('account_id')) if request.form.get('account_id') else None,
        depreciation_account_id=int(request.form.get('depreciation_account_id')) if request.form.get('depreciation_account_id') else None
    )
    asset.current_book_value = asset.acquisition_value
    db.session.add(asset)
    db.session.commit()
    flash(f'Anlagegut "{asset.name}" wurde erfasst.', 'success')
    return redirect(url_for('accounting.assets'))


@accounting_bp.route('/assets/depreciate', methods=['POST'])
@login_required
def depreciate():
    """Abschreibungslauf durchfuehren"""
    org_id = current_user.organization_id
    entries = run_depreciation(org_id, created_by_id=current_user.id)
    flash(f'Abschreibungslauf abgeschlossen: {len(entries)} Buchungen erstellt.', 'success')
    return redirect(url_for('accounting.assets'))


# ============================================================
# Kostenstellen
# ============================================================

@accounting_bp.route('/cost-centers')
@login_required
def cost_centers():
    """Kostenstellen-Uebersicht"""
    org_id = current_user.organization_id
    centers = CostCenter.query.filter_by(organization_id=org_id).order_by(CostCenter.code).all()

    # Auswertung pro Kostenstelle
    evaluations = {}
    today = date.today()
    year_start = date(today.year, 1, 1)

    for cc in centers:
        lines = JournalEntryLine.query.join(JournalEntry).filter(
            JournalEntryLine.cost_center_id == cc.id,
            JournalEntry.date >= year_start,
            JournalEntry.date <= today
        ).all()

        ertrag = sum(l.credit - l.debit for l in lines
                     if l.account and l.account.account_type == 'income')
        aufwand = sum(l.debit - l.credit for l in lines
                      if l.account and l.account.account_type == 'expense')

        evaluations[cc.id] = {
            'ertrag': round(ertrag, 2),
            'aufwand': round(aufwand, 2),
            'deckungsbeitrag': round(ertrag - aufwand, 2)
        }

    return render_template('accounting/cost_centers.html',
                           centers=centers, evaluations=evaluations)


@accounting_bp.route('/cost-centers/create', methods=['POST'])
@login_required
def create_cost_center():
    """Kostenstelle erstellen"""
    org_id = current_user.organization_id
    from models import Location

    cc = CostCenter(
        organization_id=org_id,
        code=request.form.get('code', '').strip(),
        name=request.form.get('name', '').strip(),
        location_id=int(request.form.get('location_id')) if request.form.get('location_id') else None
    )
    db.session.add(cc)
    db.session.commit()
    flash(f'Kostenstelle {cc.code} wurde erstellt.', 'success')
    return redirect(url_for('accounting.cost_centers'))


# ============================================================
# Abschluesse
# ============================================================

@accounting_bp.route('/closing')
@login_required
def closing():
    """Abschluss-Uebersicht"""
    org_id = current_user.organization_id
    today = date.today()

    # Periodensperre-Status
    locks = PeriodLock.query.filter_by(organization_id=org_id) \
        .order_by(PeriodLock.year.desc(), PeriodLock.month.desc()).all()

    # Bilanz und Erfolgsrechnung
    bilanz = generate_balance_sheet(org_id, today)
    erfolgsrechnung = generate_income_statement(org_id)

    # Soll == Haben Check
    all_lines = JournalEntryLine.query.join(JournalEntry).filter(
        JournalEntry.organization_id == org_id
    ).all()
    total_debit = sum(l.debit or 0 for l in all_lines)
    total_credit = sum(l.credit or 0 for l in all_lines)
    balance_ok = round(total_debit, 2) == round(total_credit, 2)

    return render_template('accounting/closing.html',
                           locks=locks, bilanz=bilanz,
                           erfolgsrechnung=erfolgsrechnung,
                           balance_ok=balance_ok,
                           total_debit=round(total_debit, 2),
                           total_credit=round(total_credit, 2))


@accounting_bp.route('/closing/lock-month', methods=['POST'])
@login_required
def lock_month():
    """Monat sperren"""
    org_id = current_user.organization_id
    year = int(request.form.get('year', date.today().year))
    month = int(request.form.get('month', date.today().month))

    existing = PeriodLock.query.filter_by(
        organization_id=org_id, year=year, month=month
    ).first()

    if existing and existing.locked_at:
        flash(f'Monat {month}/{year} ist bereits gesperrt.', 'warning')
    else:
        if not existing:
            existing = PeriodLock(organization_id=org_id, year=year, month=month)
            db.session.add(existing)
        existing.locked_at = datetime.utcnow()
        existing.locked_by_id = current_user.id
        db.session.commit()
        flash(f'Monat {month}/{year} wurde gesperrt.', 'success')

    return redirect(url_for('accounting.closing'))


@accounting_bp.route('/closing/lock-year', methods=['POST'])
@login_required
def lock_year():
    """Jahr sperren"""
    org_id = current_user.organization_id
    year = int(request.form.get('year', date.today().year))

    existing = PeriodLock.query.filter_by(
        organization_id=org_id, year=year, month=0
    ).first()

    if existing and existing.locked_at:
        flash(f'Jahr {year} ist bereits gesperrt.', 'warning')
    else:
        if not existing:
            existing = PeriodLock(organization_id=org_id, year=year, month=0)
            db.session.add(existing)
        existing.locked_at = datetime.utcnow()
        existing.locked_by_id = current_user.id
        db.session.commit()
        flash(f'Jahr {year} wurde gesperrt.', 'success')

    return redirect(url_for('accounting.closing'))


# ============================================================
# API-Endpunkte
# ============================================================

@accounting_bp.route('/api/account-balance/<int:account_id>')
@login_required
def api_account_balance(account_id):
    """API: Kontostand abfragen"""
    account = Account.query.get_or_404(account_id)
    check_org(account)
    balance = get_account_balance(account_id)
    return jsonify({
        'account_number': account.account_number,
        'name': account.name,
        'balance': balance
    })


@accounting_bp.route('/api/vat-calculate', methods=['POST'])
@login_required
def api_vat_calculate():
    """API: MwSt-Betrag berechnen"""
    data = request.get_json()
    betrag = float(data.get('betrag', 0))
    vat_code = data.get('vat_code', '')

    rates = {'8.1': 0.081, '3.8': 0.038, '2.6': 0.026}
    rate = rates.get(vat_code, 0)
    vat_amount = round(betrag * rate / (1 + rate), 2)  # MwSt aus Bruttobetrag

    return jsonify({'vat_amount': vat_amount, 'netto': round(betrag - vat_amount, 2)})


@accounting_bp.route('/api/dashboard-data')
@login_required
def api_dashboard_data():
    """API: Dashboard-Daten fuer Finanzen"""
    org_id = current_user.organization_id
    today = date.today()
    month_start = date(today.year, today.month, 1)

    liquidity = get_liquidity(org_id)
    debtors = get_open_debtors(org_id)
    creditors_data = get_open_creditors(org_id)
    income_stmt = generate_income_statement(org_id, month_start, today)

    return jsonify({
        'liquiditaet': liquidity['total'],
        'debitoren': debtors.get('total', 0),
        'kreditoren': sum(c['betrag'] for c in creditors_data),
        'umsatz_monat': income_stmt['total_ertrag'],
        'gewinn_monat': income_stmt['gewinn_verlust']
    })
