"""Integration Tests fuer KI-System Sicherheit.

Stellt sicher, dass PII korrekt gefiltert wird und
Tool-Permissions korrekt durchgesetzt werden.
"""
import pytest
from unittest.mock import MagicMock


class TestPIIFilter:
    """PII-Filter entfernt sensible Daten aus Text und Dictionaries."""

    def test_ahv_number_redacted(self):
        """AHV-Nummer (756.XXXX.XXXX.XX) wird maskiert."""
        from ai.pii_filter import redact_pii
        text = 'Patient hat AHV 756.1234.5678.90'
        result = redact_pii(text)
        assert '756.1234.5678.90' not in result
        assert 'REDACTED' in result

    def test_ahv_number_variant_redacted(self):
        """AHV-Nummer ohne Punkte wird ebenfalls maskiert."""
        from ai.pii_filter import redact_pii
        text = 'AHV: 7561234567890'
        result = redact_pii(text)
        assert '7561234567890' not in result

    def test_iban_redacted(self):
        """Schweizer IBAN wird maskiert."""
        from ai.pii_filter import redact_pii
        text = 'IBAN: CH93 0076 2011 6238 5295 7'
        result = redact_pii(text)
        assert 'CH93' not in result

    def test_iban_compact_redacted(self):
        """IBAN ohne Leerzeichen wird maskiert."""
        from ai.pii_filter import redact_pii
        text = 'Konto: CH9300762011623852957'
        result = redact_pii(text)
        assert 'CH9300762011623852957' not in result

    def test_phone_redacted(self):
        """Schweizer Telefonnummer wird maskiert."""
        from ai.pii_filter import redact_pii
        text = 'Telefon: +41 79 123 45 67'
        result = redact_pii(text)
        assert '+41 79' not in result

    def test_phone_with_country_code_variant(self):
        """Telefonnummer mit 0041 Praefix wird maskiert."""
        from ai.pii_filter import redact_pii
        text = 'Tel: 0041791234567'
        result = redact_pii(text)
        assert '0041791234567' not in result

    def test_email_redacted(self):
        """E-Mail-Adresse wird maskiert."""
        from ai.pii_filter import redact_pii
        text = 'Email: patient@example.com'
        result = redact_pii(text)
        assert 'patient@example.com' not in result

    def test_insurance_number_redacted(self):
        """Versicherungsnummer wird maskiert."""
        from ai.pii_filter import redact_pii
        text = 'Versicherung: 123456-789'
        result = redact_pii(text)
        assert '123456-789' not in result

    def test_non_pii_text_unchanged(self):
        """Normaler Text ohne PII bleibt unveraendert."""
        from ai.pii_filter import redact_pii
        text = 'Der Patient hat Rueckenschmerzen seit 3 Wochen.'
        result = redact_pii(text)
        assert result == text

    def test_filter_dict_removes_sensitive_fields(self):
        """filter_dict ersetzt sensible Felder mit [REDACTED]."""
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
        assert filtered['name'] == 'Max Muster'  # Name bleibt erhalten

    def test_filter_dict_handles_nested(self):
        """filter_dict behandelt verschachtelte Dicts korrekt."""
        from ai.pii_filter import filter_dict
        data = {
            'patient': {
                'name': 'Test',
                'ahv_number': '756.9999.8888.77',
                'email': 'test@example.com',
            }
        }
        filtered = filter_dict(data)
        assert filtered['patient']['ahv_number'] == '[REDACTED]'
        assert filtered['patient']['name'] == 'Test'

    def test_sanitize_context_applies_redaction(self):
        """sanitize_context wendet redact_pii auf Kontext-Strings an."""
        from ai.pii_filter import sanitize_context
        context = 'Patient AHV 756.1111.2222.33, Tel +41 79 999 88 77'
        result = sanitize_context(context)
        assert '756.1111.2222.33' not in result
        assert '+41 79' not in result

    def test_sanitize_tool_result_patient_data(self):
        """sanitize_tool_result filtert Patientendaten auf erlaubte Felder."""
        from ai.pii_filter import sanitize_tool_result
        result = {
            'id': 1,
            'patient_number': 'P00001',
            'first_name': 'Anna',
            'last_name': 'Mueller',
            'ahv_number': '756.1234.5678.90',
            'phone': '+41 79 123 45 67',
            'address': 'Teststrasse 1',
            'is_active': True,
        }
        sanitized = sanitize_tool_result('patient_details', result)
        # Erlaubte Felder muessen vorhanden sein
        assert sanitized.get('id') == 1
        assert sanitized.get('first_name') == 'Anna' or sanitized.get('vorname') is not None
        # Sensible Felder muessen gefiltert sein
        assert 'ahv_number' not in sanitized or sanitized.get('ahv_number') == '[REDACTED]'
        assert 'phone' not in sanitized or sanitized.get('phone') == '[REDACTED]'


class TestToolPermissions:
    """Tool-Permissions blockieren unerlaubte Tools je nach Rolle."""

    def test_reception_cannot_delete_patient(self):
        """Empfangs-User darf patient_deaktivieren nicht nutzen."""
        from ai.tool_permissions import can_use_tool
        user = MagicMock()
        user.role = 'reception'
        assert not can_use_tool('patient_deaktivieren', user)

    def test_admin_can_delete_patient(self):
        """Admin darf patient_deaktivieren nutzen."""
        from ai.tool_permissions import can_use_tool
        user = MagicMock()
        user.role = 'admin'
        assert can_use_tool('patient_deaktivieren', user)

    def test_therapist_can_use_read_tools(self):
        """Therapeut kann Lese-Tools nutzen."""
        from ai.tool_permissions import can_use_tool
        user = MagicMock()
        user.role = 'therapist'
        assert can_use_tool('patient_suchen', user)

    def test_reception_cannot_use_therapist_tools(self):
        """Empfangs-User kann keine Therapeuten-Tools nutzen."""
        from ai.tool_permissions import can_use_tool, TOOL_PERMISSIONS
        user = MagicMock()
        user.role = 'reception'
        # Alle Therapeuten-spezifischen Tools pruefen
        for tool in TOOL_PERMISSIONS.get('therapist', set()):
            if tool not in TOOL_PERMISSIONS.get('reception', set()) and \
               tool not in TOOL_PERMISSIONS.get('read', set()):
                assert not can_use_tool(tool, user), f'reception sollte {tool} nicht nutzen koennen'

    def test_get_allowed_tools_returns_set(self):
        """get_allowed_tools gibt ein Set zurueck."""
        from ai.tool_permissions import get_allowed_tools
        user = MagicMock()
        user.role = 'admin'
        tools = get_allowed_tools(user)
        assert isinstance(tools, set)
        assert len(tools) > 0


class TestDestructiveToolConfirmation:
    """Destruktive Tools erfordern Bestaetigung."""

    def test_destructive_tools_require_confirmation(self):
        """Bekannte destruktive Tools erfordern Bestaetigung."""
        from ai.tool_permissions import requires_confirmation
        assert requires_confirmation('patient_deaktivieren')
        assert requires_confirmation('zahlung_verbuchen')
        assert requires_confirmation('mahnlauf_starten')

    def test_read_tools_no_confirmation(self):
        """Lese-Tools erfordern keine Bestaetigung."""
        from ai.tool_permissions import requires_confirmation
        assert not requires_confirmation('patient_suchen')

    def test_rechnung_stornieren_requires_confirmation(self):
        """Rechnung stornieren erfordert Bestaetigung."""
        from ai.tool_permissions import requires_confirmation
        assert requires_confirmation('rechnung_stornieren')

    def test_serie_abschliessen_requires_confirmation(self):
        """Serie abschliessen erfordert Bestaetigung."""
        from ai.tool_permissions import requires_confirmation
        assert requires_confirmation('serie_abschliessen')
