Du bist ein Compliance Engineer. Dein Auftrag: Das Audit-System in /Users/thomasbalke/praxis-app vollstaendig ausbauen.

WICHTIG: Lies IMMER zuerst die betroffenen Dateien KOMPLETT.

## Aufgabe 1: Audit-Service erweitern
Datei: /Users/thomasbalke/praxis-app/services/audit_service.py

Lies die Datei zuerst. Erweitere sie um:

```python
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
from datetime import datetime
from flask import request
from flask_login import current_user
from models import db, AuditLog


# HMAC-Key fuer Log-Integritaet
_AUDIT_HMAC_KEY = os.environ.get('AUDIT_HMAC_KEY', 'default-audit-key').encode()


def _compute_hmac(data_str):
    """Berechnet HMAC-SHA256 fuer Log-Integritaetspruefung."""
    return hmac.new(_AUDIT_HMAC_KEY, data_str.encode(), hashlib.sha256).hexdigest()


def log_action(action, entity_type, entity_id, changes=None, details=None):
    """
    Erstellt einen Audit-Log-Eintrag.

    Args:
        action: 'create', 'read', 'update', 'delete', 'export', 'login', 'login_failed', etc.
        entity_type: 'patient', 'invoice', 'appointment', 'user', etc.
        entity_id: ID der betroffenen Entitaet
        changes: Dict mit {field: {'old': ..., 'new': ...}} fuer Updates
        details: Zusaetzliche Details als String
    """
    try:
        user_id = current_user.id if current_user and current_user.is_authenticated else None
        user_role = getattr(current_user, 'role', None) if current_user and current_user.is_authenticated else None
        ip_address = request.remote_addr if request else None
        user_agent = request.headers.get('User-Agent', '')[:200] if request else None

        changes_json = None
        if changes:
            # Sensible Felder in Aenderungen maskieren
            safe_changes = _sanitize_changes(changes)
            changes_json = json.dumps(safe_changes, ensure_ascii=False, default=str)

        # Integritaets-Hash
        integrity_data = f'{user_id}:{action}:{entity_type}:{entity_id}:{datetime.utcnow().isoformat()}'
        integrity_hash = _compute_hmac(integrity_data)

        log = AuditLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            changes_json=changes_json,
            ip_address=ip_address,
            integrity_hash=integrity_hash,
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        # Audit-Logging darf Hauptfunktion nicht blockieren
        # Aber: Fehler loggen (nicht still verschlucken!)
        import logging
        logging.getLogger('audit').error(f'Audit-Log fehlgeschlagen: {e}')
        db.session.rollback()


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
```

## Aufgabe 2: AuditLog Model erweitern
Datei: /Users/thomasbalke/praxis-app/models.py

Finde das AuditLog Model und fuege fehlende Felder hinzu:
```python
# Zusaetzliche Felder:
integrity_hash = db.Column(db.String(64), nullable=True)  # HMAC-SHA256
```

Falls das Feld `user_role` fehlt, ebenfalls hinzufuegen.

## Aufgabe 3: Audit-Logging in Billing einbauen
Datei: /Users/thomasbalke/praxis-app/blueprints/billing/routes.py

Fuege log_action() Aufrufe hinzu bei:
- Rechnung erstellen: `log_action('create', 'invoice', invoice.id)`
- Rechnung senden: `log_action('update', 'invoice', invoice.id, changes={'status': {'old': old_status, 'new': 'sent'}})`
- Zahlung erfassen: `log_action('create', 'payment', payment.id, changes={'amount': {'new': amount}, 'invoice_id': {'new': invoice.id}})`
- Rechnung stornieren: `log_action('update', 'invoice', invoice.id, changes={'status': {'old': old_status, 'new': 'cancelled'}})`
- Mahnlauf: `log_action('create', 'dunning', invoice.id, changes={'level': {'new': next_level}})`

## Aufgabe 4: Audit-Logging in Treatment einbauen
Datei: /Users/thomasbalke/praxis-app/blueprints/treatment/routes.py

- SOAP-Noten speichern: `log_action('update', 'appointment_soap', appointment.id, changes=soap_changes)`
  Dabei soap_changes = Dict der geaenderten Felder mit alten/neuen Werten
- Serie abschliessen: `log_action('update', 'treatment_series', series.id, changes={'status': {'old': old_status, 'new': new_status}})`

## Aufgabe 5: Audit-Logging in Reporting einbauen
Datei: /Users/thomasbalke/praxis-app/blueprints/reporting/routes.py

Finde die Export-Route und fuege hinzu:
```python
from services.audit_service import log_data_export
# Nach dem Export:
log_data_export('csv_export', len(result.get('rows', [])), columns=columns, filters=filters)
```

## Aufgabe 6: Audit-Logging fuer Patienten-Merge
Datei: /Users/thomasbalke/praxis-app/blueprints/patients/routes.py

Finde die Merge-Route und fuege detailliertes Logging hinzu:
```python
log_action('merge', 'patient', target.id, changes={
    'source_patient_id': {'old': source.id, 'new': None},
    'target_patient_id': {'new': target.id},
    'merged_records': {'new': 'treatment_series, appointments, documents, emails'}
})
```

## Reihenfolge:
1. Lies audit_service.py, models.py (AuditLog), und alle betroffenen routes.py
2. Erweitere audit_service.py
3. Erweitere AuditLog Model
4. Fuege Audit-Logging in billing, treatment, reporting, patients ein
5. Syntax-Checks fuer alle geaenderten Dateien
