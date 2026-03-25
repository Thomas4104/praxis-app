"""
PII-Filter (Personally Identifiable Information) fuer KI-Kontext.
Minimiert sensible Daten die an externe APIs gesendet werden.

Schweizer DSG / DSGVO: Medizinische Daten duerfen nicht ohne Notwendigkeit
an Dritte (auch Cloud-APIs) uebermittelt werden.
"""
import re


# Muster fuer sensible Daten
PII_PATTERNS = {
    'ahv_number': re.compile(r'\b756[.\s]?\d{4}[.\s]?\d{4}[.\s]?\d{2}\b'),
    'iban': re.compile(r'\b[A-Z]{2}\d{2}[\s]?\d{4}[\s]?\d{4}[\s]?\d{4}[\s]?\d{4}[\s]?\d{0,2}\b'),
    'phone_swiss': re.compile(r'(\+41|0041|0)\s?\d{2}\s?\d{3}\s?\d{2}\s?\d{2}'),
    'email': re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
    'insurance_number': re.compile(r'\b\d{6,10}[-/]\d{1,6}\b'),
}

# Felder die NICHT an die API gesendet werden duerfen
REDACTED_FIELDS = {
    'ahv_number', 'ahv_nummer',
    'insurance_number', 'versicherungsnummer',
    'iban', 'qr_iban',
    'phone', 'mobile', 'telefon',
    'email', 'e_mail',
    'address', 'street', 'adresse', 'strasse',
    'plz', 'zip_code',
    'date_of_birth', 'geburtsdatum',
}


def redact_pii(text):
    """Ersetzt PII-Muster in einem Text durch Platzhalter."""
    if not text or not isinstance(text, str):
        return text

    result = text
    for name, pattern in PII_PATTERNS.items():
        result = pattern.sub(f'[{name.upper()}_REDACTED]', result)
    return result


def filter_dict(data, allowed_fields=None):
    """Filtert sensible Felder aus einem Dictionary.

    Args:
        data: Dictionary mit potenziell sensiblen Daten
        allowed_fields: Optional - nur diese Felder durchlassen
    """
    if not isinstance(data, dict):
        return data

    filtered = {}
    for key, value in data.items():
        key_lower = key.lower()
        # Feld komplett entfernen wenn in REDACTED_FIELDS
        if key_lower in REDACTED_FIELDS:
            filtered[key] = '[REDACTED]'
            continue
        # Verschachtelte Dicts rekursiv filtern
        if isinstance(value, dict):
            filtered[key] = filter_dict(value, allowed_fields)
        elif isinstance(value, list):
            filtered[key] = [
                filter_dict(item, allowed_fields) if isinstance(item, dict)
                else redact_pii(str(item)) if isinstance(item, str)
                else item
                for item in value
            ]
        elif isinstance(value, str):
            filtered[key] = redact_pii(value)
        else:
            filtered[key] = value

    return filtered


def sanitize_tool_result(tool_name, result):
    """Sanitisiert Tool-Ergebnisse bevor sie an die API zurueckgehen.

    Bestimmte Tools geben Patientendaten zurueck. Diese muessen
    gefiltert werden bevor sie im naechsten API-Call mitgesendet werden.
    """
    if not isinstance(result, dict):
        return result

    # Fuer Patient-Details: Nur notwendige Felder durchlassen
    if tool_name in ('patient_details', 'patient_suchen'):
        safe_fields = {
            'id', 'patient_number', 'vorname', 'nachname', 'first_name', 'last_name',
            'is_active', 'insurance_type', 'created_at',
            'total_appointments', 'next_appointment',
        }
        return {k: v for k, v in result.items()
                if k in safe_fields or k == 'error'}

    return filter_dict(result)


def sanitize_context(context_text):
    """Sanitisiert den Kontext-Text bevor er an die API geht."""
    return redact_pii(context_text)
