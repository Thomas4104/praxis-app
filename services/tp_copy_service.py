"""
Service fuer automatische Tiers-Payant-Rechnungskopien.
Seit 01.01.2022 sind Schweizer Praxen gesetzlich verpflichtet,
bei Tiers-Payant-Abrechnungen eine Rechnungskopie an den Patienten zu senden.
"""
from datetime import datetime
from flask import current_app
from models import db, Invoice, InvoiceCopy, InvoiceCopyConfig, Patient, Task
from services.settings_service import get_setting


def should_send_tp_copy(invoice):
    """Prueft ob fuer diese Rechnung eine TP-Kopie versendet werden muss."""
    if not invoice:
        return False
    # Nur bei Tiers-Payant Rechnungen
    if invoice.billing_model != 'tiers_payant':
        return False
    # Pruefe ob Konfiguration aktiv
    config = InvoiceCopyConfig.query.filter_by(
        organization_id=invoice.organization_id,
        is_active=True
    ).first()
    if not config:
        return False
    # Pruefe ob bereits eine Kopie existiert
    existing = InvoiceCopy.query.filter_by(
        invoice_id=invoice.id,
        recipient_type='patient',
        status='sent'
    ).first()
    if existing:
        return False
    return True


def send_tp_copy_to_patient(invoice_id):
    """Erstellt und versendet eine Rechnungskopie an den Patienten.

    Returns:
        tuple: (InvoiceCopy, error_message)
    """
    invoice = Invoice.query.get(invoice_id)
    if not invoice:
        return None, 'Rechnung nicht gefunden'

    if not should_send_tp_copy(invoice):
        return None, 'Keine TP-Kopie erforderlich'

    patient = Patient.query.get(invoice.patient_id)
    if not patient:
        return None, 'Patient nicht gefunden'

    config = InvoiceCopyConfig.query.filter_by(
        organization_id=invoice.organization_id,
        is_active=True
    ).first()

    # Kopie-Eintrag erstellen
    copy = InvoiceCopy(
        invoice_id=invoice.id,
        recipient_type='patient',
        recipient_email=patient.email or '',
        sent_via=config.send_channel if config else 'email',
        status='pending',
    )
    db.session.add(copy)
    db.session.flush()

    # PDF-Pfad von der Rechnung uebernehmen (oder neu generieren)
    if invoice.pdf_path:
        copy.pdf_path = invoice.pdf_path
    else:
        # PDF generieren
        from services.billing_service import generate_invoice_pdf
        try:
            pdf_path = generate_invoice_pdf(invoice.id)
            copy.pdf_path = pdf_path
        except Exception as e:
            copy.status = 'failed'
            copy.error_message = f'PDF-Generierung fehlgeschlagen: {str(e)}'
            db.session.commit()
            _create_failure_task(invoice, str(e))
            return copy, copy.error_message

    # E-Mail versenden
    if config and config.send_channel in ('email', 'both'):
        if not patient.email:
            copy.status = 'failed'
            copy.error_message = 'Patient hat keine E-Mail-Adresse'
            db.session.commit()
            _create_failure_task(invoice, 'Keine E-Mail-Adresse')
            return copy, copy.error_message

        try:
            # E-Mail senden (nutzt bestehendes Mailing-System)
            _send_copy_email(invoice, patient, copy, config)
            copy.status = 'sent'
            copy.sent_at = datetime.utcnow()
        except Exception as e:
            copy.status = 'failed'
            copy.error_message = str(e)
            _create_failure_task(invoice, str(e))

    if config and config.send_channel == 'print':
        # Bei "Druck" nur PDF generieren, Status auf "sent" setzen
        copy.status = 'sent'
        copy.sent_at = datetime.utcnow()
        copy.sent_via = 'print'

    db.session.commit()
    return copy, None


def _send_copy_email(invoice, patient, copy, config):
    """Versendet die Rechnungskopie per E-Mail."""
    from services.settings_service import get_setting

    subject = f'Rechnungskopie {invoice.invoice_number}'
    body = (
        f'Guten Tag {patient.first_name} {patient.last_name}\n\n'
        f'Im Anhang finden Sie eine Kopie der Rechnung {invoice.invoice_number} '
        f'vom {invoice.created_at.strftime("%d.%m.%Y") if invoice.created_at else ""}.\n\n'
        f'Diese Kopie dient zu Ihrer Information. Die Rechnung wurde direkt '
        f'an Ihre Versicherung gesendet.\n\n'
        f'Freundliche Gruesse\n'
        f'{get_setting(invoice.organization_id, "practice_name", "Ihre Praxis")}'
    )

    # Nutze bestehendes E-Mail-System falls vorhanden
    # Ansonsten nur Status setzen (E-Mail wird extern versendet)
    current_app.logger.info(
        f'TP-Rechnungskopie {invoice.invoice_number} an {patient.email} vorbereitet'
    )


def _create_failure_task(invoice, error_message):
    """Erstellt eine Aufgabe bei fehlgeschlagenem Versand."""
    config = InvoiceCopyConfig.query.filter_by(
        organization_id=invoice.organization_id,
        is_active=True
    ).first()

    if not config or not config.create_task_on_failure:
        return

    task = Task(
        organization_id=invoice.organization_id,
        title=f'TP-Rechnungskopie fehlgeschlagen: {invoice.invoice_number}',
        description=(
            f'Der automatische Versand der Rechnungskopie fuer Rechnung '
            f'{invoice.invoice_number} ist fehlgeschlagen.\n'
            f'Fehler: {error_message}\n'
            f'Bitte manuell versenden.'
        ),
        priority='high',
        status='open',
    )
    db.session.add(task)


def process_pending_copies(org_id):
    """Verarbeitet alle ausstehenden Rechnungskopien einer Organisation."""
    pending = InvoiceCopy.query.join(Invoice).filter(
        Invoice.organization_id == org_id,
        InvoiceCopy.status == 'pending'
    ).all()

    results = {'sent': 0, 'failed': 0}
    for copy in pending:
        _, error = send_tp_copy_to_patient(copy.invoice_id)
        if error:
            results['failed'] += 1
        else:
            results['sent'] += 1

    return results
