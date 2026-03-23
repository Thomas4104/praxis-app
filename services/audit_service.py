"""Audit-Logging fuer DSG/GDPR Compliance"""
from datetime import datetime
from flask import request
from flask_login import current_user


def log_action(action, entity_type, entity_id, changes=None):
    """Protokolliert eine Aktion im Audit-Log.

    action: 'create', 'read', 'update', 'delete', 'login', 'logout', 'download', 'print'
    entity_type: 'patient', 'appointment', 'invoice', 'document', etc.
    entity_id: ID des betroffenen Datensatzes
    changes: Optional dict mit Aenderungen
    """
    try:
        from models import db, AuditLog
        import json
        log = AuditLog(
            organization_id=current_user.organization_id if current_user and current_user.is_authenticated else None,
            user_id=current_user.id if current_user and current_user.is_authenticated else None,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            changes_json=json.dumps(changes, default=str, ensure_ascii=False) if changes else None,
            ip_address=request.remote_addr if request else None,
            created_at=datetime.utcnow()
        )
        db.session.add(log)
        # Kein eigener Commit - wird mit dem naechsten Commit gespeichert
    except Exception:
        pass  # Audit-Logging darf Hauptfunktion nicht blockieren
