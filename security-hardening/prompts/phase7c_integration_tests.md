Du bist ein Integration Test Engineer. Dein Auftrag: Integration-Tests fuer kritische Workflows in /Users/thomasbalke/praxis-app schreiben.

WICHTIG: Lies zuerst die relevanten Routes und Models. Voraussetzung: tests/conftest.py existiert bereits.

## Aufgabe 1: Multi-Tenancy Integration Tests
Erstelle: /Users/thomasbalke/praxis-app/tests/test_multi_tenancy.py

Teste end-to-end:
1. User in Org A kann KEINE Patienten von Org B sehen
2. User in Org A kann KEINE Termine von Org B sehen
3. User in Org A kann KEINE Rechnungen von Org B sehen
4. Suche gibt nur Ergebnisse der eigenen Org zurueck
5. API-Endpoints filtern korrekt nach Organization

## Aufgabe 2: Portal-Security Integration Tests
Erstelle: /Users/thomasbalke/praxis-app/tests/test_portal_security.py

Teste:
1. Portal-Login mit falschen Credentials wird abgelehnt
2. Portal-User kann nur eigene Termine sehen
3. Portal-User kann nur eigene Rechnungen sehen
4. Portal-User kann keine anderen Patienten-Daten abrufen
5. Online-Booking-Validierung (kein Datum in der Vergangenheit)

## Aufgabe 3: KI-Tool-Security Integration Tests
Erstelle: /Users/thomasbalke/praxis-app/tests/test_ai_security.py

Teste:
1. PII-Filter entfernt AHV-Nummern aus Kontext
2. PII-Filter entfernt Telefonnummern
3. PII-Filter entfernt IBAN
4. Tool-Permissions blockieren unerlaubte Tools
5. Destruktive Tools erfordern Bestaetigung

```python
"""Tests fuer KI-System Sicherheit."""
import pytest


class TestPIIFilter:
    def test_ahv_number_redacted(self):
        from ai.pii_filter import redact_pii
        text = 'Patient hat AHV 756.1234.5678.90'
        result = redact_pii(text)
        assert '756.1234.5678.90' not in result
        assert 'REDACTED' in result

    def test_iban_redacted(self):
        from ai.pii_filter import redact_pii
        text = 'IBAN: CH93 0076 2011 6238 5295 7'
        result = redact_pii(text)
        assert 'CH93' not in result

    def test_phone_redacted(self):
        from ai.pii_filter import redact_pii
        text = 'Telefon: +41 79 123 45 67'
        result = redact_pii(text)
        assert '+41 79' not in result

    def test_email_redacted(self):
        from ai.pii_filter import redact_pii
        text = 'Email: patient@example.com'
        result = redact_pii(text)
        assert 'patient@example.com' not in result

    def test_filter_dict_removes_sensitive_fields(self):
        from ai.pii_filter import filter_dict
        data = {
            'name': 'Max Muster',
            'ahv_number': '756.1234.5678.90',
            'insurance_number': '123456-789',
            'phone': '+41 79 123 45 67',
        }
        filtered = filter_dict(data)
        assert filtered['ahv_number'] == '[REDACTED]'
        assert filtered['insurance_number'] == '[REDACTED]'
        assert filtered['phone'] == '[REDACTED]'
        assert filtered['name'] == 'Max Muster'  # Name bleibt


class TestToolPermissions:
    def test_reception_cannot_delete_patient(self):
        from ai.tool_permissions import can_use_tool
        from unittest.mock import MagicMock
        user = MagicMock()
        user.role = 'reception'
        assert not can_use_tool('patient_deaktivieren', user)

    def test_admin_can_delete_patient(self):
        from ai.tool_permissions import can_use_tool
        from unittest.mock import MagicMock
        user = MagicMock()
        user.role = 'admin'
        assert can_use_tool('patient_deaktivieren', user)

    def test_destructive_tools_require_confirmation(self):
        from ai.tool_permissions import requires_confirmation
        assert requires_confirmation('patient_deaktivieren')
        assert requires_confirmation('zahlung_verbuchen')
        assert requires_confirmation('mahnlauf_starten')
        assert not requires_confirmation('patient_suchen')
```

## Aufgabe 4: Health-Check Tests
Erstelle: /Users/thomasbalke/praxis-app/tests/test_health.py

```python
"""Tests fuer Health-Endpoint Sicherheit."""
import pytest


class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        response = client.get('/health')
        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'healthy'

    def test_health_does_not_expose_details_on_error(self, client):
        """Bei Fehler duerfen keine internen Details exponiert werden."""
        # Dieser Test ist schwer zu triggern ohne DB-Mock
        # Aber: pruefen dass das Format korrekt ist
        response = client.get('/health')
        data = response.get_json()
        if 'error' in data:
            # Fehler-Nachricht darf keine Stack-Traces oder DB-Details enthalten
            assert 'traceback' not in data['error'].lower()
            assert 'password' not in data['error'].lower()
            assert 'postgresql' not in data['error'].lower()
```

## Reihenfolge:
1. Lies conftest.py, relevante routes.py und models.py
2. Passe alle Tests an tatsaechliche Implementierung an
3. Erstelle Test-Dateien
4. Syntax-Checks: python3 -c "import ast; ast.parse(open('tests/test_ai_security.py').read())"
