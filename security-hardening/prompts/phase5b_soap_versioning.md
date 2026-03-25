Du bist ein Healthcare IT Compliance Spezialist. Dein Auftrag: SOAP-Noten-Versionierung in /Users/thomasbalke/praxis-app implementieren.

WICHTIG: Lies IMMER zuerst die betroffenen Dateien KOMPLETT.

## Aufgabe 1: SOAP-History Model erstellen
Datei: /Users/thomasbalke/praxis-app/models.py

Fuege ein neues Model hinzu (am Ende, vor den Portal-Models):

```python
class SoapNoteHistory(db.Model):
    """Versionierung von SOAP-Noten fuer medizinische Compliance.
    Jede Aenderung an SOAP-Noten wird hier archiviert.
    Schweizer Medizinrecht verlangt unveraenderbare klinische Dokumentation."""
    __tablename__ = 'soap_note_history'

    id = db.Column(db.Integer, primary_key=True)
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointments.id'), nullable=False)
    version = db.Column(db.Integer, nullable=False, default=1)

    # Snapshot der SOAP-Felder zum Zeitpunkt der Aenderung
    soap_subjective = db.Column(db.Text, nullable=True)
    soap_objective = db.Column(db.Text, nullable=True)
    soap_assessment = db.Column(db.Text, nullable=True)
    soap_plan = db.Column(db.Text, nullable=True)

    # Metadaten
    changed_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    changed_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    change_reason = db.Column(db.String(500), nullable=True)  # Aenderungsgrund (Pflicht bei Korrektur)

    # Integritaet
    content_hash = db.Column(db.String(64), nullable=False)  # SHA-256 des Inhalts

    # Relationships
    appointment = db.relationship('Appointment', backref=db.backref('soap_history', lazy='dynamic', order_by='SoapNoteHistory.version'))
    changed_by = db.relationship('User')

    # Indexes
    __table_args__ = (
        db.Index('ix_soap_history_appointment', 'appointment_id', 'version'),
    )

    def compute_hash(self):
        import hashlib
        content = f'{self.soap_subjective or ""}|{self.soap_objective or ""}|{self.soap_assessment or ""}|{self.soap_plan or ""}'
        self.content_hash = hashlib.sha256(content.encode()).hexdigest()
        return self.content_hash
```

## Aufgabe 2: SOAP-Speichern Route anpassen
Datei: /Users/thomasbalke/praxis-app/blueprints/treatment/routes.py

Finde die Route die SOAP-Noten speichert (vermutlich api_soap_speichern oder aehnlich).

VORHER wird direkt ueberschrieben. NACHHER wird eine History erstellt:

```python
from models import SoapNoteHistory
from services.audit_service import log_action

# In der SOAP-Speichern Route:
# 1. Alten Zustand sichern
old_values = {
    'soap_subjective': appointment.soap_subjective,
    'soap_objective': appointment.soap_objective,
    'soap_assessment': appointment.soap_assessment,
    'soap_plan': appointment.soap_plan,
}

# 2. Pruefen ob sich etwas geaendert hat
new_values = {
    'soap_subjective': data.get('soap_subjective', appointment.soap_subjective),
    'soap_objective': data.get('soap_objective', appointment.soap_objective),
    'soap_assessment': data.get('soap_assessment', appointment.soap_assessment),
    'soap_plan': data.get('soap_plan', appointment.soap_plan),
}

has_changes = any(old_values[k] != new_values[k] for k in old_values)

if has_changes:
    # 3. Aktuelle Version in History speichern (VOR der Aenderung)
    current_version = appointment.soap_history.count() + 1
    history = SoapNoteHistory(
        appointment_id=appointment.id,
        version=current_version,
        soap_subjective=old_values['soap_subjective'],
        soap_objective=old_values['soap_objective'],
        soap_assessment=old_values['soap_assessment'],
        soap_plan=old_values['soap_plan'],
        changed_by_id=current_user.id,
        change_reason=data.get('change_reason', ''),
    )
    history.compute_hash()
    db.session.add(history)

    # 4. Neue Werte setzen
    for key, value in new_values.items():
        setattr(appointment, key, value)

    # 5. Audit-Log
    changes = {}
    for key in old_values:
        if old_values[key] != new_values[key]:
            changes[key] = {
                'old': (old_values[key] or '')[:100] + '...' if old_values[key] and len(old_values[key] or '') > 100 else old_values[key],
                'new': (new_values[key] or '')[:100] + '...' if new_values[key] and len(new_values[key] or '') > 100 else new_values[key],
            }
    log_action('update', 'soap_notes', appointment.id, changes=changes)

db.session.commit()
```

## Aufgabe 3: SOAP-History API Route erstellen
Datei: /Users/thomasbalke/praxis-app/blueprints/treatment/routes.py

Fuege eine neue Route hinzu zum Anzeigen der History:

```python
@treatment_bp.route('/api/termin/<int:termin_id>/soap/history')
@login_required
def api_soap_history(termin_id):
    """Gibt die SOAP-Noten-History fuer einen Termin zurueck."""
    appointment = Appointment.query.get_or_404(termin_id)
    check_org(appointment)

    history = SoapNoteHistory.query.filter_by(
        appointment_id=termin_id
    ).order_by(SoapNoteHistory.version.desc()).all()

    return jsonify([{
        'version': h.version,
        'soap_subjective': h.soap_subjective,
        'soap_objective': h.soap_objective,
        'soap_assessment': h.soap_assessment,
        'soap_plan': h.soap_plan,
        'changed_by': f'{h.changed_by.first_name} {h.changed_by.last_name}' if h.changed_by else 'Unbekannt',
        'changed_at': h.changed_at.strftime('%d.%m.%Y %H:%M'),
        'change_reason': h.change_reason,
        'content_hash': h.content_hash,
    } for h in history])
```

## Aufgabe 4: Appointment Model um Timestamp erweitern
Datei: /Users/thomasbalke/praxis-app/models.py

Finde das Appointment Model und fuege hinzu (falls nicht vorhanden):
```python
soap_updated_at = db.Column(db.DateTime, nullable=True)
soap_updated_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
```

Aktualisiere in der SOAP-Speichern Route:
```python
appointment.soap_updated_at = datetime.utcnow()
appointment.soap_updated_by_id = current_user.id
```

## Reihenfolge:
1. Lies models.py (Appointment Model) und treatment/routes.py KOMPLETT
2. Fuege SoapNoteHistory Model hinzu
3. Erweitere Appointment Model
4. Aendere SOAP-Speichern Route
5. Fuege History-API hinzu
6. Syntax-Checks
