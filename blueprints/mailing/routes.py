"""Mailing-Blueprint: E-Mail-Verwaltung und Kommunikation"""
import json
from datetime import datetime
from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from blueprints.mailing import mailing_bp
from models import (db, Email, EmailAttachment, EmailFolder, EmailTemplate,
                     Patient, TreatmentSeries, Invoice, Organization,
                     CostApproval, Appointment, SystemSetting)


# ============================================================
# E-Mail-Uebersicht
# ============================================================

@mailing_bp.route('/')
@login_required
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

    # Ordner-Zaehler
    folder_counts = {}
    for f in ['inbox', 'drafts', 'sent', 'archive', 'trash']:
        folder_counts[f] = Email.query.filter_by(
            organization_id=org_id, folder=f
        ).count()

    # Ungelesene im Posteingang
    unread_count = Email.query.filter_by(
        organization_id=org_id, folder='inbox'
    ).filter(Email.read_at.is_(None)).count()

    # Eigene Ordner
    custom_folders = EmailFolder.query.filter_by(
        organization_id=org_id
    ).order_by(EmailFolder.sort_order, EmailFolder.name).all()

    for cf in custom_folders:
        folder_counts[f'custom_{cf.id}'] = Email.query.filter_by(
            organization_id=org_id, folder=f'custom_{cf.id}'
        ).count()

    return render_template('mailing/index.html',
                           emails=emails,
                           current_folder=folder,
                           folder_counts=folder_counts,
                           unread_count=unread_count,
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

    return render_template('mailing/detail.html',
                           email=email,
                           patient=patient,
                           series=series,
                           invoice=invoice,
                           attachments=attachments,
                           custom_folders=custom_folders,
                           patients=patients)


# ============================================================
# E-Mail verfassen
# ============================================================

@mailing_bp.route('/compose')
@login_required
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
            to_address = original.from_address or ''
            subject = f'Re: {original.subject}' if not (original.subject or '').startswith('Re:') else original.subject
            body = f'<br><br><hr><p><strong>Von:</strong> {original.from_address}<br><strong>Datum:</strong> {original.created_at.strftime("%d.%m.%Y %H:%M")}<br><strong>Betreff:</strong> {original.subject}</p>{original.body_html or original.body_text or ""}'

    # Weiterleiten
    if forward_id:
        original = Email.query.get(forward_id)
        if original:
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

    # E-Mail-Vorlagen laden
    templates = EmailTemplate.query.filter_by(
        organization_id=org_id,
        is_active=True
    ).order_by(EmailTemplate.name).all()

    # Absender-Konfiguration aus Einstellungen
    sender_setting = SystemSetting.query.filter_by(
        organization_id=org_id, key='email_sender_address'
    ).first()
    sender_address = sender_setting.value if sender_setting else ''

    sender_name_setting = SystemSetting.query.filter_by(
        organization_id=org_id, key='email_sender_name'
    ).first()
    sender_name = sender_name_setting.value if sender_name_setting else ''

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
                           patients=patients)


def _build_placeholder_replacements(patient, org, patient_id=None, series_id=None, invoice_id=None):
    """Erstellt ein Dictionary mit Platzhalter-Ersetzungen"""
    replacements = {
        '{patient_name}': f'{patient.first_name} {patient.last_name}' if patient else '',
        '{patient_vorname}': patient.first_name if patient else '',
        '{patient_nachname}': patient.last_name if patient else '',
        '{praxis_name}': org.name if org else '',
        '{praxis_telefon}': org.phone if org else '',
        '{praxis_email}': org.email if org else '',
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
        else:
            replacements['{termin_datum}'] = ''
            replacements['{termin_zeit}'] = ''

    # Therapeut
    replacements['{therapeut_name}'] = f'{current_user.first_name} {current_user.last_name}'

    return replacements


# ============================================================
# API-Endpunkte
# ============================================================

@mailing_bp.route('/api/send', methods=['POST'])
@login_required
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

    # E-Mails in Posteingang verschieben
    Email.query.filter_by(
        organization_id=current_user.organization_id,
        folder=f'custom_{folder.id}'
    ).update({'folder': 'inbox'})

    db.session.delete(folder)
    db.session.commit()

    return jsonify({'success': True, 'message': 'Ordner gelöscht.'})


# ============================================================
# Vorlagen-API (fuer Compose-Formular)
# ============================================================

@mailing_bp.route('/api/templates/<int:template_id>')
@login_required
def get_template(template_id):
    """Vorlage laden und Platzhalter ersetzen"""
    template = EmailTemplate.query.get_or_404(template_id)
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
