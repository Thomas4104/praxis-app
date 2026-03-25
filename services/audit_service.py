"""
Erweitertes Audit-Logging fuer medizinische Compliance (DSG/DSGVO).
Protokolliert ALLE Zugriffe auf sensible Daten mit:
- Wer (User-ID, Rolle, IP)
- Was (Aktion, Entitaet, Entitaets-ID)
- Wann (Zeitstempel)
- Aenderungen (Vorher/Nachher fuer Mutationen)
"""
import json
import hashlib
import hmac
import os
import logging
from datetime import datetime
from flask import request
from flask_login import current_user


# HMAC-Key fuer Log-Integritaet
_AUDIT_HMAC_KEY = os.environ.get('AUDIT_HMAC_KEY', 'default-audit-key').encode()


def _compute_hmac(data_str):
    """Berechnet HMAC-SHA256 fuer Log-Integritaetspruefung."""
    return hmac.new(_AUDIT_HMAC_KEY, data_str.encode(), hashlib.sha256).hexdigest()


def _sanitize_changes(changes):
    """Maskiert sensible Werte in Aenderungs-Logs."""
    SENSITIVE_FIELDS = {
        'ahv_number', 'insurance_number', 'iban', 'qr_iban',
        'password', 'password_hash', 'totp_secret', 'totp_backup_codes',
    }
    sanitized = {}
    for field, change in changes.items():
        if field.lower() in SENSITIVE_FIELDS:
            sanitized[field] = {'old': '[REDACTED]', 'new': '[CHANGED]'}
        else:
            sanitized[field] = change
    return sanitized


def log_action(action, entity_type, entity_id, changes=None, details=None):
    """
    Erstellt einen Audit-Log-Eintrag.

    Args:
        action: 'create', 'read', 'update', 'delete', 'export', 'login', 'login_failed', 'merge', etc.
        entity_type: 'patient', 'invoice', 'appointment', 'user', etc.
        entity_id: ID der betroffenen Entitaet
        changes: Dict mit {field: {'old': ..., 'new': ...}} fuer Updates
        details: Zusaetzliche Details als String
    """
    try:
        from models import db, AuditLog

        user_id = current_user.id if current_user and current_user.is_authenticated else None
        user_role = getattr(current_user, 'role', None) if current_user and current_user.is_authenticated else None
        org_id = current_user.organization_id if current_user and current_user.is_authenticated else None
        ip_address = request.remote_addr if request else None

        changes_json = None
        if changes:
            # Sensible Felder in Aenderungen maskieren
            safe_changes = _sanitize_changes(changes)
            changes_json = json.dumps(safe_changes, ensure_ascii=False, default=str)

        # Integritaets-Hash
        integrity_data = f'{user_id}:{action}:{entity_type}:{entity_id}:{datetime.utcnow().isoformat()}'
        integrity_hash = _compute_hmac(integrity_data)

        log = AuditLog(
            organization_id=org_id,
            user_id=user_id,
            user_role=user_role,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            changes_json=changes_json,
            ip_address=ip_address,
            integrity_hash=integrity_hash,
            created_at=datetime.utcnow()
        )
        db.session.add(log)
        # Kein eigener Commit - wird mit dem naechsten Commit gespeichert
    except Exception as e:
        # Audit-Logging darf Hauptfunktion nicht blockieren
        # Aber: Fehler loggen (nicht still verschlucken!)
        logging.getLogger('audit').error(f'Audit-Log fehlgeschlagen: {e}')
        try:
            from models import db
            db.session.rollback()
        except Exception:
            pass


def log_data_export(export_type, row_count, columns=None, filters=None):
    """Spezielles Logging fuer Datenexporte."""
    log_action(
        'export',
        export_type,
        0,
        details=json.dumps({
            'row_count': row_count,
            'columns': columns or [],
            'filters': filters or {},
        }, ensure_ascii=False)
    )


def log_patient_access(patient_id, access_type='view'):
    """Convenience-Funktion fuer Patientendaten-Zugriff."""
    log_action(access_type, 'patient', patient_id)
