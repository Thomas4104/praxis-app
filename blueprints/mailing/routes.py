"""Mailing-Blueprint: E-Mail-Verwaltung, SMS, Spam, Konten (Cenplex-Abgleich Phase 10)"""
import math
from datetime import datetime
from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from blueprints.mailing import mailing_bp
from models import (db, Email, EmailAttachment, EmailFolder, EmailTemplate,
                     EmailLog, SmsLog, SpamList, EmailMapping, EmailInbox,
                     Patient, TreatmentSeries, Invoice, Organization,
                     CostApproval, Appointment, SystemSetting, Employee, Location)
from utils.auth import check_org, get_org_id
from services.user_rights_service import require_right


# ============================================================
# E-Mail-Uebersicht
# ============================================================

@mailing_bp.route('/')
@login_required
@require_right('mailing', 'can_read')
def index():
    """E-Mail-Uebersicht mit Ordner-Navigation und E-Mail-Liste"""
    folder = request.args.get('folder', 'inbox')
    search = request.args.get('search', '').strip()
    sort_by = request.args.get('sort', 'date_desc')
    page = request.args.get('page', 1, type=int)
    per_page = 25

    org_id = current_user.organization_id

    query = Email.query.filter_by(organization_id=org_id, folder=folder)

    # Suche
    if search:
        query = query.filter(
            db.or_(
                Email.subject.ilike(f'%{search}%'),
                Email.from_address.ilike(f'%{search}%'),
                Email.to_address.ilike(f'%{search}%'),
                Email.body_text.ilike(f'%{search}%')
            )
        )

    # Sortierung
    if sort_by == 'date_asc':
        query = query.order_by(Email.created_at.asc())
    elif sort_by == 'sender':
        query = query.order_by(Email.from_address.asc())
    elif sort_by == 'subject':
        query = query.order_by(Email.subject.asc())
    else:
        query = query.order_by(Email.created_at.desc())

    emails = query.paginate(page=page, per_page=per_page, error_out=False)

    # Ordner-Zaehler (eine Query statt N+1)
    folder_count_rows = db.session.query(
        Email.folder, db.func.count(Email.id)
    ).filter_by(organization_id=org_id).group_by(Email.folder).all()
    folder_counts = {row[0]: row[1] for row in folder_count_rows}
    # Sicherstellen dass alle Standard-Ordner vorhanden sind
    for f in ['inbox', 'drafts', 'sent', 'archive', 'trash']:
        folder_counts.setdefault(f, 0)

    # Ungelesene im Posteingang
    unread_count = Email.query.filter_by(
        organization_id=org_id, folder='inbox'
    ).filter(Email.read_at.is_(None)).count()

    # Bounce-Zaehler
    bounce_count = EmailLog.query.filter_by(
        organization_id=org_id, status='bounced'
    ).count()

    # Spam-Zaehler
    spam_count = SpamList.query.filter_by(organization_id=org_id).count()

    # Eigene Ordner
    custom_folders = EmailFolder.query.filter_by(
        organization_id=org_id
    ).order_by(EmailFolder.sort_order, EmailFolder.name).all()

    for cf in custom_folders:
        folder_counts.setdefault(f'custom_{cf.id}', 0)

    return render_template('mailing/index.html',
                           emails=emails,
                           current_folder=folder,
                           folder_counts=folder_counts,
                           unread_count=unread_count,
                           bounce_count=bounce_count,
                           spam_count=spam_count,
                           custom_folders=custom_folders,
                           search=search,
                           sort_by=sort_by)


# ============================================================
# E-Mail lesen
# ============================================================

@mailing_bp.route('/<int:email_id>')
@login_required
def detail(email_id):
    """E-Mail-Detailansicht"""
    email = Email.query.get_or_404(email_id)
    check_org(email)

    # Als gelesen markieren
    if not email.read_at:
        email.read_at = datetime.utcnow()
        db.session.commit()

    # Verknuepfte Objekte laden
    patient = Patient.query.get(email.linked_patient_id) if email.linked_patient_id else None
    series = TreatmentSeries.query.get(email.linked_series_id) if email.linked_series_id else None
    invoice = Invoice.query.get(email.linked_invoice_id) if email.linked_invoice_id else None
    attachments = email.attachments.all()

    # Alle Ordner fuer Verschieben-Dropdown
    custom_folders = EmailFolder.query.filter_by(
        organization_id=current_user.organization_id
    ).order_by(EmailFolder.sort_order, EmailFolder.name).all()

    # Alle Patienten fuer Verknuepfung
    patients = Patient.query.filter_by(
        organization_id=current_user.organization_id,
        is_active=True
    ).order_by(Patient.last_name).all()

    # Farb-Optionen fuer Cenplex-kompatible Farbmarkierung
    color_options = [
        {'value': 0, 'label': 'Keine', 'color': 'transparent'},
        {'value': 1, 'label': 'Rot', 'color': '#ef4444'},
        {'value': 2, 'label': 'Orange', 'color': '#f97316'},
        {'value': 3, 'label': 'Gelb', 'color': '#eab308'},
        {'value': 4, 'label': 'Gruen', 'color': '#22c55e'},
        {'value': 5, 'label': 'Blau', 'color': '#3b82f6'},
        {'value': 6, 'label': 'Lila', 'color': '#a855f7'},
    ]

    return render_template('mailing/detail.html',
                           email=email,
                           patient=patient,
                           series=series,
                           invoice=invoice,
                           attachments=attachments,
                           custom_folders=custom_folders,
                           patients=patients,
                           color_options=color_options)


# ============================================================
# E-Mail verfassen
# ============================================================

@mailing_bp.route('/compose')
@login_required
@require_right('mailing', 'can_edit')
def compose():
    """E-Mail verfassen"""
    org_id = current_user.organization_id

    # Vorbefuellung aus URL-Parametern
    to_address = request.args.get('to', '')
    subject = request.args.get('subject', '')
    body = request.args.get('body', '')
    patient_id = request.args.get('patient_id', None, type=int)
    series_id = request.args.get('series_id', None, type=int)
    invoice_id = request.args.get('invoice_id', None, type=int)
    reply_to = request.args.get('reply_to', None, type=int)
    forward_id = request.args.get('forward', None, type=int)
    draft_id = request.args.get('draft_id', None, type=int)
    template_type = request.args.get('template', '')

    # Entwurf laden
    draft = None
    if draft_id:
        draft = Email.query.get(draft_id)
        if draft:
            check_org(draft)
            to_address = draft.to_address or ''
            subject = draft.subject or ''
            body = draft.body_html or ''
            patient_id = draft.linked_patient_id
            series_id = draft.linked_series_id
            invoice_id = draft.linked_invoice_id

    # Antworten
    if reply_to:
        original = Email.query.get(reply_to)
        if original:
            check_org(original)
            to_address = original.from_address or ''
            subject = f'Re: {original.subject}' if not (original.subject or '').startswith('Re:') else original.subject
            body = f'<br><br><hr><p><strong>Von:</strong> {original.from_address}<br><strong>Datum:</strong> {original.created_at.strftime("%d.%m.%Y %H:%M")}<br><strong>Betreff:</strong> {original.subject}</p>{original.body_html or original.body_text or ""}'

    # Weiterleiten
    if forward_id:
        original = Email.query.get(forward_id)
        if original:
            check_org(original)
            subject = f'Fwd: {original.subject}' if not (original.subject or '').startswith('Fwd:') else original.subject
            body = f'<br><br><hr><p><strong>Weitergeleitete Nachricht</strong><br><strong>Von:</strong> {original.from_address}<br><strong>Datum:</strong> {original.created_at.strftime("%d.%m.%Y %H:%M")}<br><strong>Betreff:</strong> {original.subject}</p>{original.body_html or original.body_text or ""}'

    # Vorlage laden und Platzhalter ersetzen
    if template_type and patient_id:
        template = EmailTemplate.query.filter_by(
            organization_id=org_id,
            template_type=template_type,
            is_active=True
        ).first()
        patient = Patient.query.get(patient_id)
        if template and patient:
            org = Organization.query.get(org_id)
            subject = template.subject or subject
            body = template.body_html or ''
            # Platzhalter ersetzen
            replacements = _build_placeholder_replacements(patient, org, patient_id, series_id, invoice_id)
            for key, val in replacements.items():
                subject = subject.replace(key, val)
                body = body.replace(key, val)

    # E-Mail-Vorlagen laden (nur E-Mail, nicht SMS)
    templates = EmailTemplate.query.filter_by(
        organization_id=org_id,
        is_active=True
    ).filter(db.or_(EmailTemplate.is_sms == False, EmailTemplate.is_sms.is_(None))).order_by(EmailTemplate.name).all()

    # Absender-Konfiguration aus Einstellungen
    sender_setting = SystemSetting.query.filter_by(
        organization_id=org_id, key='email_sender_address'
    ).first()
    sender_address = sender_setting.value if sender_setting else ''

    sender_name_setting = SystemSetting.query.filter_by(
        organization_id=org_id, key='email_sender_name'
    ).first()
    sender_name = sender_name_setting.value if sender_name_setting else ''

    # E-Mail-Konten (Mappings) fuer Absender-Auswahl
    email_mappings = EmailMapping.query.filter_by(
        organization_id=org_id
    ).all()

    # Patienten fuer Autocomplete
    patients = Patient.query.filter_by(
        organization_id=org_id, is_active=True
    ).order_by(Patient.last_name).all()

    return render_template('mailing/compose.html',
                           to_address=to_address,
                           subject=subject,
                           body=body,
                           patient_id=patient_id,
                           series_id=series_id,
                           invoice_id=invoice_id,
                           draft=draft,
                           templates=templates,
                           sender_address=sender_address,
                           sender_name=sender_name,
                           email_mappings=email_mappings,
                           patients=patients)


def _build_placeholder_replacements(patient, org, patient_id=None, series_id=None, invoice_id=None):
    """Erstellt ein Dictionary mit Platzhalter-Ersetzungen"""
    replacements = {
        '{patient_name}': f'{patient.first_name} {patient.last_name}' if patient else '',
        '{patient_vorname}': patient.first_name if patient else '',
        '{patient_nachname}': patient.last_name if patient else '',
        '{patient_anrede}': getattr(patient, 'salutation', '') or '' if patient else '',
        '{patient_geburtsdatum}': patient.date_of_birth.strftime('%d.%m.%Y') if patient and patient.date_of_birth else '',
        '{praxis_name}': org.name if org else '',
        '{praxis_telefon}': org.phone if org else '',
        '{praxis_email}': org.email if org else '',
        '{praxis_adresse}': getattr(org, 'address', '') or '' if org else '',
        '{praxis_plz}': getattr(org, 'postal_code', '') or '' if org else '',
        '{praxis_ort}': getattr(org, 'city', '') or '' if org else '',
        '{datum}': datetime.now().strftime('%d.%m.%Y'),
    }

    if series_id:
        series = TreatmentSeries.query.get(series_id)
        if series:
            replacements['{serie_name}'] = series.diagnosis or ''

    if invoice_id:
        invoice = Invoice.query.get(invoice_id)
        if invoice:
            replacements['{rechnungs_nummer}'] = invoice.invoice_number or ''
            replacements['{rechnungs_betrag}'] = f'CHF {invoice.total_amount:.2f}' if invoice.total_amount else ''

    # Termin-Platzhalter
    if patient_id:
        next_appt = Appointment.query.filter(
            Appointment.patient_id == patient_id,
            Appointment.start_time >= datetime.now(),
            Appointment.status.in_(['scheduled', 'confirmed'])
        ).order_by(Appointment.start_time).first()
        if next_appt:
            replacements['{termin_datum}'] = next_appt.start_time.strftime('%d.%m.%Y')
            replacements['{termin_zeit}'] = next_appt.start_time.strftime('%H:%M')
            if next_appt.end_time:
                replacements['{termin_ende}'] = next_appt.end_time.strftime('%H:%M')
            else:
                replacements['{termin_ende}'] = ''
        else:
            replacements['{termin_datum}'] = ''
            replacements['{termin_zeit}'] = ''
            replacements['{termin_ende}'] = ''

        # Termin-Liste (alle kommenden Termine)
        upcoming = Appointment.query.filter(
            Appointment.patient_id == patient_id,
            Appointment.start_time >= datetime.now(),
            Appointment.status.in_(['scheduled', 'confirmed'])
        ).order_by(Appointment.start_time).limit(10).all()
        if upcoming:
            termin_liste = '<ul>'
            for a in upcoming:
                termin_liste += f'<li>{a.start_time.strftime("%d.%m.%Y %H:%M")}</li>'
            termin_liste += '</ul>'
            replacements['{termin_liste}'] = termin_liste
        else:
            replacements['{termin_liste}'] = ''

    # Therapeut
    replacements['{therapeut_name}'] = f'{current_user.first_name} {current_user.last_name}'
    replacements['{therapeut_vorname}'] = current_user.first_name or ''
    replacements['{therapeut_nachname}'] = current_user.last_name or ''
    replacements['{therapeut_email}'] = current_user.email or ''
    replacements['{therapeut_telefon}'] = getattr(current_user, 'phone', '') or ''

    return replacements


# ============================================================
# SMS-Verlauf
# ============================================================

@mailing_bp.route('/sms')
@login_required
def sms_index():
    """SMS-Verlauf und -Verwaltung"""
    org_id = current_user.organization_id
    search = request.args.get('search', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 25

    query = SmsLog.query.filter_by(organization_id=org_id)

    if search:
        query = query.filter(
            db.or_(
                SmsLog.phone_number.ilike(f'%{search}%'),
                SmsLog.message.ilike(f'%{search}%')
            )
        )

    query = query.order_by(SmsLog.created_at.desc())
    sms_logs = query.paginate(page=page, per_page=per_page, error_out=False)

    # SMS-Statistik fuer aktuellen Monat
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    monthly_count = SmsLog.query.filter(
        SmsLog.organization_id == org_id,
        SmsLog.created_at >= month_start
    ).count()

    # SMS-Vorlagen laden
    sms_templates = EmailTemplate.query.filter_by(
        organization_id=org_id,
        is_sms=True,
        is_active=True
    ).order_by(EmailTemplate.name).all()

    return render_template('mailing/sms_index.html',
                           sms_logs=sms_logs,
                           monthly_count=monthly_count,
                           sms_templates=sms_templates,
                           search=search)


# ============================================================
# SMS verfassen
# ============================================================

@mailing_bp.route('/sms/compose')
@login_required
@require_right('mailing', 'can_edit')
def sms_compose():
    """SMS verfassen"""
    org_id = current_user.organization_id

    patient_id = request.args.get('patient_id', None, type=int)
    phone = request.args.get('phone', '')
    template_id = request.args.get('template_id', None, type=int)

    patient = Patient.query.get(patient_id) if patient_id else None
    if patient and not phone:
        phone = getattr(patient, 'mobile_phone', '') or getattr(patient, 'phone', '') or ''

    message = ''
    if template_id:
        template = EmailTemplate.query.get(template_id)
        if template and template.organization_id == org_id:
            message = template.body_html or ''
            if patient:
                org = Organization.query.get(org_id)
                replacements = _build_placeholder_replacements(patient, org, patient_id)
                for key, val in replacements.items():
                    message = message.replace(key, val)

    # SMS-Vorlagen
    sms_templates = EmailTemplate.query.filter_by(
        organization_id=org_id,
        is_sms=True,
        is_active=True
    ).order_by(EmailTemplate.name).all()

    # Patienten fuer Autocomplete
    patients = Patient.query.filter_by(
        organization_id=org_id, is_active=True
    ).order_by(Patient.last_name).all()

    return render_template('mailing/sms_compose.html',
                           phone=phone,
                           message=message,
                           patient_id=patient_id,
                           patient=patient,
                           sms_templates=sms_templates,
                           patients=patients)


@mailing_bp.route('/api/sms/send', methods=['POST'])
@login_required
@require_right('mailing', 'can_edit')
def send_sms():
    """SMS senden (Demo-Modus: wird nur protokolliert)"""
    data = request.get_json()
    org_id = current_user.organization_id

    phone = data.get('phone', '').strip()
    message = data.get('message', '').strip()
    patient_id = data.get('patient_id') or None

    if not phone:
        return jsonify({'success': False, 'message': 'Telefonnummer ist erforderlich.'}), 400
    if not message:
        return jsonify({'success': False, 'message': 'Nachricht ist erforderlich.'}), 400

    # SMS-Segmente berechnen (160 Zeichen pro Segment)
    parts = math.ceil(len(message) / 160) if message else 1

    sms = SmsLog(
        organization_id=org_id,
        phone_number=phone,
        message=message,
        patient_id=patient_id,
        parts_count=parts,
        sender_name=f'{current_user.first_name} {current_user.last_name}',
        sent_by_id=getattr(current_user, 'employee_id', None),
        status='sent',
        sent_at=datetime.utcnow()
    )
    db.session.add(sms)
    db.session.commit()

    return jsonify({'success': True, 'message': f'SMS gespeichert (Demo-Modus). {parts} Segment(e).', 'sms_id': sms.id})


# ============================================================
# SMS-Detail
# ============================================================

@mailing_bp.route('/sms/<int:sms_id>')
@login_required
def sms_detail(sms_id):
    """SMS-Detailansicht"""
    sms = SmsLog.query.get_or_404(sms_id)
    if sms.organization_id != current_user.organization_id:
        return jsonify({'success': False}), 403

    patient = Patient.query.get(sms.patient_id) if sms.patient_id else None

    return render_template('mailing/sms_detail.html', sms=sms, patient=patient)


# ============================================================
# Bounce-Ansicht (fehlgeschlagene E-Mails)
# ============================================================

@mailing_bp.route('/bounced')
@login_required
def bounced():
    """Fehlgeschlagene/zurueckgewiesene E-Mails"""
    org_id = current_user.organization_id
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()

    query = EmailLog.query.filter(
        EmailLog.organization_id == org_id,
        EmailLog.status.in_(['bounced', 'failed'])
    )

    if search:
        query = query.filter(
            db.or_(
                EmailLog.to_address.ilike(f'%{search}%'),
                EmailLog.subject.ilike(f'%{search}%'),
                EmailLog.error_message.ilike(f'%{search}%')
            )
        )

    query = query.order_by(EmailLog.created_at.desc())
    bounced_emails = query.paginate(page=page, per_page=25, error_out=False)

    return render_template('mailing/bounced.html',
                           bounced_emails=bounced_emails,
                           search=search)


# ============================================================
# Spam-Verwaltung
# ============================================================

@mailing_bp.route('/spam')
@login_required
def spam_list():
    """Spam-Liste verwalten"""
    org_id = current_user.organization_id

    entries = SpamList.query.filter_by(
        organization_id=org_id
    ).order_by(SpamList.created_at.desc()).all()

    return render_template('mailing/spam.html', entries=entries)


@mailing_bp.route('/api/spam', methods=['POST'])
@login_required
def add_spam():
    """Eintrag zur Spam-Liste hinzufuegen"""
    data = request.get_json()
    org_id = current_user.organization_id

    spam_entry = data.get('spam_entry', '').strip()
    entry_type = data.get('entry_type', 0)

    if not spam_entry:
        return jsonify({'success': False, 'message': 'Eintrag ist erforderlich.'}), 400

    # Pruefen ob bereits vorhanden
    existing = SpamList.query.filter_by(
        organization_id=org_id,
        spam_entry=spam_entry
    ).first()
    if existing:
        return jsonify({'success': False, 'message': 'Eintrag bereits vorhanden.'}), 400

    entry = SpamList(
        organization_id=org_id,
        spam_entry=spam_entry,
        email=spam_entry if entry_type == 0 else None,
        entry_type=entry_type,
        created_by_id=getattr(current_user, 'employee_id', None)
    )
    db.session.add(entry)
    db.session.commit()

    return jsonify({'success': True, 'entry_id': entry.id})


@mailing_bp.route('/api/spam/<int:entry_id>', methods=['PUT'])
@login_required
def update_spam(entry_id):
    """Spam-Eintrag bearbeiten"""
    entry = SpamList.query.get_or_404(entry_id)
    if entry.organization_id != current_user.organization_id:
        return jsonify({'success': False}), 403

    data = request.get_json()
    entry.spam_entry = data.get('spam_entry', entry.spam_entry)
    entry.entry_type = data.get('entry_type', entry.entry_type)
    db.session.commit()

    return jsonify({'success': True})


@mailing_bp.route('/api/spam/<int:entry_id>', methods=['DELETE'])
@login_required
def delete_spam(entry_id):
    """Spam-Eintrag loeschen"""
    entry = SpamList.query.get_or_404(entry_id)
    if entry.organization_id != current_user.organization_id:
        return jsonify({'success': False}), 403

    db.session.delete(entry)
    db.session.commit()

    return jsonify({'success': True})


@mailing_bp.route('/api/spam/from-email', methods=['POST'])
@login_required
def add_spam_from_email():
    """E-Mail(s) als Spam markieren und Absender zur Spam-Liste hinzufuegen"""
    data = request.get_json()
    org_id = current_user.organization_id
    email_ids = data.get('email_ids', [])

    added = 0
    for eid in email_ids:
        email = Email.query.get(eid)
        if email and email.organization_id == org_id and email.from_address:
            # E-Mail in Spam-Ordner verschieben
            email.folder = 'spam'

            # Absender zur Spam-Liste hinzufuegen (falls nicht vorhanden)
            existing = SpamList.query.filter_by(
                organization_id=org_id,
                spam_entry=email.from_address
            ).first()
            if not existing:
                entry = SpamList(
                    organization_id=org_id,
                    spam_entry=email.from_address,
                    email=email.from_address,
                    entry_type=0,
                    created_by_id=getattr(current_user, 'employee_id', None)
                )
                db.session.add(entry)
                added += 1

    db.session.commit()
    return jsonify({'success': True, 'added': added})


# ============================================================
# E-Mail-Konten/Mappings Verwaltung
# ============================================================

@mailing_bp.route('/accounts')
@login_required
def accounts():
    """E-Mail-Konten verwalten (Cenplex: EmailmappingDto)"""
    org_id = current_user.organization_id

    mappings = EmailMapping.query.filter_by(
        organization_id=org_id
    ).all()

    employees = Employee.query.filter_by(
        organization_id=org_id,
        is_active=True
    ).order_by(Employee.last_name).all()

    locations = Location.query.filter_by(
        organization_id=org_id
    ).order_by(Location.name).all()

    return render_template('mailing/accounts.html',
                           mappings=mappings,
                           employees=employees,
                           locations=locations)


@mailing_bp.route('/api/accounts', methods=['POST'])
@login_required
def create_account():
    """Neues E-Mail-Konto anlegen"""
    data = request.get_json()
    org_id = current_user.organization_id

    email_addr = data.get('email', '').strip()
    if not email_addr:
        return jsonify({'success': False, 'message': 'E-Mail-Adresse ist erforderlich.'}), 400

    # Pruefen ob E-Mail bereits existiert
    existing = EmailMapping.query.filter_by(
        organization_id=org_id,
        email=email_addr
    ).first()
    if existing:
        return jsonify({'success': False, 'message': 'E-Mail-Adresse bereits konfiguriert.'}), 400

    mapping = EmailMapping(
        organization_id=org_id,
        email=email_addr,
        employee_id=data.get('employee_id') or None,
        location_id=data.get('location_id') or None,
        sent_email_bcc=data.get('sent_email_bcc', ''),
        received_email_bcc=data.get('received_email_bcc', ''),
        is_default=data.get('is_default', False),
        absence_subject=data.get('absence_subject', ''),
        absence_note=data.get('absence_note', ''),
    )
    db.session.add(mapping)
    db.session.commit()

    return jsonify({'success': True, 'mapping_id': mapping.id})


@mailing_bp.route('/api/accounts/<int:mapping_id>', methods=['PUT'])
@login_required
def update_account(mapping_id):
    """E-Mail-Konto bearbeiten"""
    mapping = EmailMapping.query.get_or_404(mapping_id)
    if mapping.organization_id != current_user.organization_id:
        return jsonify({'success': False}), 403

    data = request.get_json()
    mapping.email = data.get('email', mapping.email)
    mapping.employee_id = data.get('employee_id') or None
    mapping.location_id = data.get('location_id') or None
    mapping.sent_email_bcc = data.get('sent_email_bcc', mapping.sent_email_bcc)
    mapping.received_email_bcc = data.get('received_email_bcc', mapping.received_email_bcc)
    mapping.is_default = data.get('is_default', mapping.is_default)
    mapping.absence_subject = data.get('absence_subject', mapping.absence_subject)
    mapping.absence_note = data.get('absence_note', mapping.absence_note)
    mapping.absence_note_active_from = None
    mapping.absence_note_active_till = None

    # Abwesenheits-Daten parsen
    if data.get('absence_from'):
        try:
            mapping.absence_note_active_from = datetime.strptime(data['absence_from'], '%Y-%m-%d')
        except ValueError:
            pass
    if data.get('absence_till'):
        try:
            mapping.absence_note_active_till = datetime.strptime(data['absence_till'], '%Y-%m-%d')
        except ValueError:
            pass

    db.session.commit()
    return jsonify({'success': True})


@mailing_bp.route('/api/accounts/<int:mapping_id>', methods=['DELETE'])
@login_required
def delete_account(mapping_id):
    """E-Mail-Konto loeschen"""
    mapping = EmailMapping.query.get_or_404(mapping_id)
    if mapping.organization_id != current_user.organization_id:
        return jsonify({'success': False}), 403

    db.session.delete(mapping)
    db.session.commit()
    return jsonify({'success': True})


# ============================================================
# API-Endpunkte: E-Mail senden/verwalten
# ============================================================

@mailing_bp.route('/api/send', methods=['POST'])
@login_required
@require_right('mailing', 'can_edit')
def send_email():
    """E-Mail senden (Demo-Modus: wird nur gespeichert)"""
    data = request.get_json()
    org_id = current_user.organization_id

    # Absender ermitteln
    sender_setting = SystemSetting.query.filter_by(
        organization_id=org_id, key='email_sender_address'
    ).first()
    from_addr = sender_setting.value if sender_setting else current_user.email

    email = Email(
        organization_id=org_id,
        from_address=from_addr,
        to_address=data.get('to', ''),
        cc=data.get('cc', ''),
        bcc=data.get('bcc', ''),
        subject=data.get('subject', ''),
        body_html=data.get('body_html', ''),
        body_text=data.get('body_text', ''),
        status='sent',
        folder='sent',
        linked_patient_id=data.get('patient_id') or None,
        linked_series_id=data.get('series_id') or None,
        linked_invoice_id=data.get('invoice_id') or None,
        sent_at=datetime.utcnow()
    )
    db.session.add(email)

    # Versandprotokoll erstellen
    log = EmailLog(
        organization_id=org_id,
        from_address=from_addr,
        to_address=data.get('to', ''),
        cc=data.get('cc', ''),
        subject=data.get('subject', ''),
        body_html=data.get('body_html', ''),
        patient_id=data.get('patient_id') or None,
        sender_name=f'{current_user.first_name} {current_user.last_name}',
        status='sent',
        sent_at=datetime.utcnow()
    )
    db.session.add(log)

    # Entwurf loeschen falls vorhanden
    draft_id = data.get('draft_id')
    if draft_id:
        draft = Email.query.get(draft_id)
        if draft and draft.folder == 'drafts':
            db.session.delete(draft)

    db.session.commit()

    return jsonify({'success': True, 'message': 'E-Mail wurde gespeichert (Demo-Modus).', 'email_id': email.id})


@mailing_bp.route('/api/draft', methods=['POST'])
@login_required
def save_draft():
    """E-Mail als Entwurf speichern"""
    data = request.get_json()
    org_id = current_user.organization_id

    draft_id = data.get('draft_id')
    if draft_id:
        email = Email.query.get(draft_id)
        if not email:
            return jsonify({'success': False, 'message': 'Entwurf nicht gefunden.'}), 404
        check_org(email)
    else:
        email = Email(organization_id=org_id, folder='drafts', status='draft')
        db.session.add(email)

    email.to_address = data.get('to', '')
    email.cc = data.get('cc', '')
    email.bcc = data.get('bcc', '')
    email.subject = data.get('subject', '')
    email.body_html = data.get('body_html', '')
    email.body_text = data.get('body_text', '')
    email.linked_patient_id = data.get('patient_id') or None
    email.linked_series_id = data.get('series_id') or None
    email.linked_invoice_id = data.get('invoice_id') or None

    db.session.commit()

    return jsonify({'success': True, 'message': 'Entwurf gespeichert.', 'draft_id': email.id})


@mailing_bp.route('/api/delete', methods=['POST'])
@login_required
def delete_email():
    """E-Mail loeschen (in Papierkorb verschieben oder endgueltig loeschen)"""
    data = request.get_json()
    email_ids = data.get('email_ids', [])

    for eid in email_ids:
        email = Email.query.get(eid)
        if email and email.organization_id == current_user.organization_id:
            if email.folder == 'trash':
                db.session.delete(email)
            else:
                email.folder = 'trash'

    db.session.commit()
    return jsonify({'success': True, 'message': 'E-Mails gelöscht.'})


@mailing_bp.route('/api/restore', methods=['POST'])
@login_required
def restore_email():
    """E-Mails aus Papierkorb/Spam wiederherstellen"""
    data = request.get_json()
    email_ids = data.get('email_ids', [])

    for eid in email_ids:
        email = Email.query.get(eid)
        if email and email.organization_id == current_user.organization_id:
            email.folder = 'inbox'

    db.session.commit()
    return jsonify({'success': True, 'message': 'E-Mails wiederhergestellt.'})


@mailing_bp.route('/api/move', methods=['POST'])
@login_required
def move_email():
    """E-Mail in anderen Ordner verschieben"""
    data = request.get_json()
    email_ids = data.get('email_ids', [])
    target_folder = data.get('folder', 'inbox')

    for eid in email_ids:
        email = Email.query.get(eid)
        if email and email.organization_id == current_user.organization_id:
            email.folder = target_folder

    db.session.commit()
    return jsonify({'success': True, 'message': f'E-Mails verschoben.'})


@mailing_bp.route('/api/mark-read', methods=['POST'])
@login_required
def mark_read():
    """E-Mails als gelesen markieren"""
    data = request.get_json()
    email_ids = data.get('email_ids', [])

    for eid in email_ids:
        email = Email.query.get(eid)
        if email and email.organization_id == current_user.organization_id:
            email.read_at = datetime.utcnow()

    db.session.commit()
    return jsonify({'success': True})


@mailing_bp.route('/api/mark-unread', methods=['POST'])
@login_required
def mark_unread():
    """E-Mails als ungelesen markieren"""
    data = request.get_json()
    email_ids = data.get('email_ids', [])

    for eid in email_ids:
        email = Email.query.get(eid)
        if email and email.organization_id == current_user.organization_id:
            email.read_at = None

    db.session.commit()
    return jsonify({'success': True})


@mailing_bp.route('/api/mark-handled', methods=['POST'])
@login_required
def mark_handled():
    """E-Mails als bearbeitet markieren (Cenplex: HandleddateDto)"""
    data = request.get_json()
    email_ids = data.get('email_ids', [])
    handled = data.get('handled', True)

    for eid in email_ids:
        email = Email.query.get(eid)
        if email and email.organization_id == current_user.organization_id:
            if handled:
                email.handled_at = datetime.utcnow()
                email.handled_by_id = getattr(current_user, 'employee_id', None)
            else:
                email.handled_at = None
                email.handled_by_id = None

    db.session.commit()
    return jsonify({'success': True})


@mailing_bp.route('/api/color', methods=['POST'])
@login_required
def set_color():
    """Farbmarkierung fuer E-Mails setzen (Cenplex: ColorcodeDto)"""
    data = request.get_json()
    email_ids = data.get('email_ids', [])
    color = data.get('color', 0)

    for eid in email_ids:
        email = Email.query.get(eid)
        if email and email.organization_id == current_user.organization_id:
            email.color_code = color

    db.session.commit()
    return jsonify({'success': True})


@mailing_bp.route('/api/link-patient', methods=['POST'])
@login_required
def link_patient():
    """E-Mail mit Patient verknuepfen"""
    data = request.get_json()
    email_id = data.get('email_id')
    patient_id = data.get('patient_id')

    email = Email.query.get(email_id)
    if email and email.organization_id == current_user.organization_id:
        email.linked_patient_id = patient_id
        db.session.commit()
        return jsonify({'success': True, 'message': 'Verknüpfung gespeichert.'})

    return jsonify({'success': False, 'message': 'E-Mail nicht gefunden.'}), 404


# ============================================================
# Ordner-Verwaltung
# ============================================================

@mailing_bp.route('/api/folders', methods=['POST'])
@login_required
def create_folder():
    """Neuen Ordner erstellen"""
    data = request.get_json()
    name = data.get('name', '').strip()

    if not name:
        return jsonify({'success': False, 'message': 'Name ist erforderlich.'}), 400

    folder = EmailFolder(
        organization_id=current_user.organization_id,
        name=name
    )
    db.session.add(folder)
    db.session.commit()

    return jsonify({'success': True, 'folder_id': folder.id, 'name': folder.name})


@mailing_bp.route('/api/folders/<int:folder_id>', methods=['PUT'])
@login_required
def rename_folder(folder_id):
    """Ordner umbenennen"""
    folder = EmailFolder.query.get_or_404(folder_id)
    check_org(folder)
    data = request.get_json()
    name = data.get('name', '').strip()

    if not name:
        return jsonify({'success': False, 'message': 'Name ist erforderlich.'}), 400

    folder.name = name
    db.session.commit()

    return jsonify({'success': True, 'name': folder.name})


@mailing_bp.route('/api/folders/<int:folder_id>', methods=['DELETE'])
@login_required
def delete_folder(folder_id):
    """Ordner loeschen (E-Mails in Posteingang verschieben)"""
    folder = EmailFolder.query.get_or_404(folder_id)
    check_org(folder)

    # E-Mails in Posteingang verschieben
    Email.query.filter_by(
        organization_id=current_user.organization_id,
        folder=f'custom_{folder.id}'
    ).update({'folder': 'inbox'})

    db.session.delete(folder)
    db.session.commit()

    return jsonify({'success': True, 'message': 'Ordner gelöscht.'})


@mailing_bp.route('/api/folders/reorder', methods=['POST'])
@login_required
def reorder_folders():
    """Ordner-Reihenfolge aendern (Cenplex: Drag-Drop)"""
    data = request.get_json()
    folder_ids = data.get('folder_ids', [])

    for i, fid in enumerate(folder_ids):
        folder = EmailFolder.query.get(fid)
        if folder and folder.organization_id == current_user.organization_id:
            folder.sort_order = i

    db.session.commit()
    return jsonify({'success': True})


# ============================================================
# Vorlagen-API (fuer Compose-Formular)
# ============================================================

@mailing_bp.route('/api/templates/<int:template_id>')
@login_required
def get_template(template_id):
    """Vorlage laden und Platzhalter ersetzen"""
    template = EmailTemplate.query.get_or_404(template_id)
    check_org(template)
    patient_id = request.args.get('patient_id', None, type=int)

    subject = template.subject or ''
    body = template.body_html or ''

    if patient_id:
        patient = Patient.query.get(patient_id)
        org = Organization.query.get(current_user.organization_id)
        if patient:
            replacements = _build_placeholder_replacements(patient, org, patient_id)
            for key, val in replacements.items():
                subject = subject.replace(key, val)
                body = body.replace(key, val)

    return jsonify({
        'subject': subject,
        'body_html': body,
        'template_type': template.template_type
    })


# ============================================================
# Ungelesene E-Mails API (fuer Badge in Navigation)
# ============================================================

@mailing_bp.route('/api/unread-count')
@login_required
def unread_count():
    """Anzahl ungelesener E-Mails im Posteingang"""
    count = Email.query.filter_by(
        organization_id=current_user.organization_id,
        folder='inbox'
    ).filter(Email.read_at.is_(None)).count()

    return jsonify({'count': count})


# ============================================================
# E-Mail Versandprotokoll (Sent-Log)
# ============================================================

@mailing_bp.route('/sent-log')
@login_required
def sent_log():
    """Detailliertes Versandprotokoll (Cenplex: EmaillogDto)"""
    org_id = current_user.organization_id
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    status_filter = request.args.get('status', '')

    query = EmailLog.query.filter_by(organization_id=org_id)

    if status_filter:
        query = query.filter_by(status=status_filter)

    if search:
        query = query.filter(
            db.or_(
                EmailLog.to_address.ilike(f'%{search}%'),
                EmailLog.subject.ilike(f'%{search}%')
            )
        )

    query = query.order_by(EmailLog.created_at.desc())
    logs = query.paginate(page=page, per_page=25, error_out=False)

    return render_template('mailing/sent_log.html',
                           logs=logs,
                           search=search,
                           status_filter=status_filter)
