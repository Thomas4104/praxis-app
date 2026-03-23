"""KI-Tools fuer den Einstellungen-Bereich"""
import json
from models import db, AISettings, SystemSetting, EmailTemplate, PrintTemplate
from services.settings_service import get_setting, set_setting, get_settings_by_category


SETTINGS_TOOLS = [
    {
        'name': 'einstellung_anzeigen',
        'description': 'Zeigt die aktuellen Einstellungen einer bestimmten Kategorie an.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'kategorie': {
                    'type': 'string',
                    'description': 'Kategorie der Einstellungen',
                    'enum': ['general', 'calendar', 'email', 'billing', 'ai']
                }
            },
            'required': ['kategorie']
        }
    },
    {
        'name': 'einstellung_aendern',
        'description': 'Aendert eine einzelne Einstellung. Nur fuer Administratoren.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'key': {
                    'type': 'string',
                    'description': 'Der Schluessel der Einstellung (z.B. "calendar_time_grid", "billing_payment_term")'
                },
                'value': {
                    'type': 'string',
                    'description': 'Der neue Wert der Einstellung'
                }
            },
            'required': ['key', 'value']
        }
    },
    {
        'name': 'ki_intensitaet_setzen',
        'description': 'Aendert die KI-Intensitaetsstufe (low=dezent, normal, high=proaktiv).',
        'input_schema': {
            'type': 'object',
            'properties': {
                'level': {
                    'type': 'string',
                    'description': 'Intensitaetsstufe',
                    'enum': ['low', 'normal', 'high']
                }
            },
            'required': ['level']
        }
    },
    {
        'name': 'email_vorlage_anzeigen',
        'description': 'Zeigt eine E-Mail-Vorlage anhand des Typs an.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'typ': {
                    'type': 'string',
                    'description': 'Typ der Vorlage',
                    'enum': ['reminder', 'confirmation', 'cancellation', 'recall', 'welcome']
                }
            },
            'required': ['typ']
        }
    }
]


# Kategorie-Labels fuer deutsche Ausgabe
KATEGORIE_LABELS = {
    'general': 'Allgemein',
    'calendar': 'Kalender',
    'email': 'E-Mail',
    'billing': 'Abrechnung',
    'ai': 'KI'
}

# Setting-Key Labels fuer deutsche Ausgabe
SETTING_LABELS = {
    'app_language': 'App-Sprache',
    'timezone': 'Zeitzone',
    'date_format': 'Datumsformat',
    'currency': 'Waehrung',
    'calendar_time_grid': 'Zeitraster (Minuten)',
    'calendar_day_start': 'Tagesbeginn',
    'calendar_day_end': 'Tagesende',
    'calendar_default_duration': 'Standard-Termindauer (Minuten)',
    'email_sender_address': 'Absender-E-Mail',
    'email_sender_name': 'Absender-Name',
    'email_auto_reminder': 'Automatische Erinnerung',
    'email_reminder_hours': 'Erinnerung (Stunden vorher)',
    'billing_default_model': 'Abrechnungsmodell',
    'billing_payment_term': 'Zahlungsziel (Tage)',
    'billing_invoice_format': 'Rechnungsnummern-Format',
    'billing_next_invoice_number': 'Naechste Rechnungsnummer',
    'dunning_1_days': '1. Mahnung nach (Tagen)',
    'dunning_2_days': '2. Mahnung nach (Tagen)',
    'dunning_3_days': '3. Mahnung nach (Tagen)',
    'dunning_1_fee': '1. Mahngebuehr (CHF)',
    'dunning_2_fee': '2. Mahngebuehr (CHF)',
    'dunning_3_fee': '3. Mahngebuehr (CHF)',
}

INTENSITY_LABELS = {
    'low': 'Dezent',
    'normal': 'Normal',
    'high': 'Proaktiv'
}

TEMPLATE_TYPE_LABELS = {
    'reminder': 'Terminerinnerung',
    'confirmation': 'Terminbestaetigung',
    'cancellation': 'Terminabsage',
    'recall': 'Recall',
    'welcome': 'Willkommen'
}


def settings_tool_executor(tool_name, tool_input):
    """Fuehrt die Einstellungen-Tools aus"""
    from flask_login import current_user

    if tool_name == 'einstellung_anzeigen':
        kategorie = tool_input['kategorie']
        org_id = current_user.organization_id

        if kategorie == 'ai':
            ai_settings = AISettings.query.filter_by(organization_id=org_id).first()
            if not ai_settings:
                return {'ergebnis': 'Keine KI-Einstellungen konfiguriert.'}

            features = {}
            if ai_settings.features_enabled_json:
                try:
                    features = json.loads(ai_settings.features_enabled_json)
                except (json.JSONDecodeError, TypeError):
                    pass

            return {
                'ergebnis': {
                    'intensitaet': INTENSITY_LABELS.get(ai_settings.intensity_level, ai_settings.intensity_level),
                    'monatliches_budget_chf': f'{ai_settings.budget_monthly:.2f}',
                    'verbraucht_chf': f'{ai_settings.budget_used:.2f}',
                    'chat_assistent': 'Aktiv' if features.get('chat_assistant') else 'Inaktiv',
                    'terminvorschlaege': 'Aktiv' if features.get('auto_appointment_suggestions') else 'Inaktiv',
                    'proaktive_hinweise': 'Aktiv' if features.get('proactive_hints') else 'Inaktiv',
                    'dokumentationsvorschlaege': 'Aktiv' if features.get('documentation_suggestions') else 'Inaktiv'
                }
            }

        settings = get_settings_by_category(org_id, kategorie)
        if not settings:
            return {'ergebnis': f'Keine Einstellungen fuer Kategorie "{KATEGORIE_LABELS.get(kategorie, kategorie)}" gefunden. Standardwerte werden verwendet.'}

        ergebnis = {}
        for key, value in settings.items():
            label = SETTING_LABELS.get(key, key)
            ergebnis[label] = value

        return {'ergebnis': ergebnis, 'kategorie': KATEGORIE_LABELS.get(kategorie, kategorie)}

    elif tool_name == 'einstellung_aendern':
        if current_user.role != 'admin':
            return {'error': 'Nur Administratoren duerfen Einstellungen aendern.'}

        key = tool_input['key']
        value = tool_input['value']
        org_id = current_user.organization_id

        # Kategorie anhand des Keys ermitteln
        if key.startswith('calendar_') or key.startswith('appointment_'):
            category = 'calendar'
        elif key.startswith('email_'):
            category = 'email'
        elif key.startswith('billing_') or key.startswith('dunning_'):
            category = 'billing'
        else:
            category = 'general'

        # Typ ermitteln
        value_type = 'string'
        if key.endswith('_days') or key.endswith('_hours') or key.endswith('_number') or key == 'calendar_time_grid' or key == 'calendar_default_duration':
            value_type = 'integer'
        elif key.endswith('_fee'):
            value_type = 'float'
        elif key.endswith('_reminder'):
            value_type = 'boolean'

        set_setting(org_id, key, value, value_type, category)
        label = SETTING_LABELS.get(key, key)

        return {'ergebnis': f'Einstellung "{label}" wurde auf "{value}" geaendert.'}

    elif tool_name == 'ki_intensitaet_setzen':
        if current_user.role != 'admin':
            return {'error': 'Nur Administratoren duerfen die KI-Intensitaet aendern.'}

        level = tool_input['level']
        org_id = current_user.organization_id

        ai_settings = AISettings.query.filter_by(organization_id=org_id).first()
        if not ai_settings:
            ai_settings = AISettings(organization_id=org_id)
            db.session.add(ai_settings)

        ai_settings.intensity_level = level
        db.session.commit()

        return {'ergebnis': f'KI-Intensitaet wurde auf "{INTENSITY_LABELS.get(level, level)}" gesetzt.'}

    elif tool_name == 'email_vorlage_anzeigen':
        typ = tool_input['typ']
        org_id = current_user.organization_id

        vorlagen = EmailTemplate.query.filter_by(
            organization_id=org_id, template_type=typ
        ).all()

        if not vorlagen:
            return {'ergebnis': f'Keine E-Mail-Vorlagen vom Typ "{TEMPLATE_TYPE_LABELS.get(typ, typ)}" gefunden.'}

        ergebnisse = []
        for v in vorlagen:
            ergebnisse.append({
                'name': v.name,
                'typ': TEMPLATE_TYPE_LABELS.get(v.template_type, v.template_type),
                'betreff': v.subject or '-',
                'aktiv': 'Ja' if v.is_active else 'Nein'
            })

        return {'ergebnis': ergebnisse, 'anzahl': len(ergebnisse)}

    return {'error': f'Unbekanntes Tool: {tool_name}'}
