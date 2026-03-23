"""KI-Tools fuer den Praxis-Bereich"""
import json
from datetime import datetime, date
from models import db, Organization, Location, BankAccount, Holiday, TreatmentSeriesTemplate, TaxPointValue


PRACTICE_TOOLS = [
    {
        'name': 'praxis_info',
        'description': 'Zeigt alle Praxisdaten der Organisation (Name, Adresse, Registrierungsnummern, etc.).',
        'input_schema': {
            'type': 'object',
            'properties': {},
            'required': []
        }
    },
    {
        'name': 'standorte_auflisten',
        'description': 'Listet alle Standorte der Praxis auf mit Adresse, Telefon und Status.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'nur_aktive': {
                    'type': 'boolean',
                    'description': 'Nur aktive Standorte anzeigen (Standard: true)'
                }
            },
            'required': []
        }
    },
    {
        'name': 'oeffnungszeiten_anzeigen',
        'description': 'Zeigt die Oeffnungszeiten eines Standorts oder der gesamten Organisation.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'standort_id': {
                    'type': 'integer',
                    'description': 'ID des Standorts (leer = Organisations-Standard)'
                }
            },
            'required': []
        }
    },
    {
        'name': 'feiertage_anzeigen',
        'description': 'Zeigt die Feiertage fuer ein bestimmtes Jahr.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'jahr': {
                    'type': 'integer',
                    'description': 'Jahr (Standard: aktuelles Jahr)'
                }
            },
            'required': []
        }
    },
    {
        'name': 'serienvorlagen_auflisten',
        'description': 'Listet alle Behandlungsserien-Vorlagen auf.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'nur_aktive': {
                    'type': 'boolean',
                    'description': 'Nur aktive Vorlagen anzeigen (Standard: true)'
                }
            },
            'required': []
        }
    },
    {
        'name': 'taxpunktwert_abfragen',
        'description': 'Zeigt den aktuellen Taxpunktwert fuer einen bestimmten Tarif-Typ.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'tarif_typ': {
                    'type': 'string',
                    'description': 'Tarif-Typ (z.B. "Tarif 312", "Tarif 311", "Tarif 590")'
                }
            },
            'required': ['tarif_typ']
        }
    }
]


def practice_tool_executor(tool_name, tool_input):
    """Fuehrt die Praxis-Tools aus"""

    if tool_name == 'praxis_info':
        org = Organization.query.first()
        if not org:
            return {'error': 'Keine Organisation gefunden.'}

        return {
            'ergebnis': {
                'name': org.name,
                'adresse': f'{org.address}, {org.zip_code} {org.city}' if org.address else '-',
                'telefon': org.phone or '-',
                'email': org.email or '-',
                'zsr_nummer': org.zsr_number or '-',
                'gln_nummer': org.gln_number or '-',
                'nif_nummer': org.nif_number or '-',
                'uid_nummer': org.uid_number or '-',
                'kontaktperson': org.contact_person or '-',
                'standardsprache': org.default_language or 'de',
                'anzahl_standorte': org.locations.filter_by(is_active=True).count()
            }
        }

    elif tool_name == 'standorte_auflisten':
        nur_aktive = tool_input.get('nur_aktive', True)
        query = Location.query
        if nur_aktive:
            query = query.filter_by(is_active=True)
        standorte = query.order_by(Location.name).all()

        if not standorte:
            return {'ergebnis': 'Keine Standorte gefunden.', 'anzahl': 0}

        ergebnisse = []
        for s in standorte:
            ergebnisse.append({
                'id': s.id,
                'name': s.name,
                'adresse': f'{s.address}, {s.zip_code} {s.city}' if s.address else '-',
                'telefon': s.phone or '-',
                'email': s.email or '-',
                'aktiv': s.is_active
            })

        return {'ergebnis': ergebnisse, 'anzahl': len(ergebnisse)}

    elif tool_name == 'oeffnungszeiten_anzeigen':
        standort_id = tool_input.get('standort_id')
        if standort_id:
            standort = Location.query.get(standort_id)
            if not standort:
                return {'error': 'Standort nicht gefunden.'}
            oh_json = standort.opening_hours_json
            quelle = f'Standort: {standort.name}'
        else:
            org = Organization.query.first()
            if not org:
                return {'error': 'Keine Organisation gefunden.'}
            oh_json = org.opening_hours_json
            quelle = 'Organisation (Standard)'

        if not oh_json:
            return {'ergebnis': f'Keine Oeffnungszeiten definiert fuer {quelle}.'}

        try:
            oh = json.loads(oh_json)
        except (json.JSONDecodeError, TypeError):
            return {'ergebnis': 'Oeffnungszeiten konnten nicht geladen werden.'}

        tage_namen = {
            'montag': 'Montag', 'dienstag': 'Dienstag', 'mittwoch': 'Mittwoch',
            'donnerstag': 'Donnerstag', 'freitag': 'Freitag',
            'samstag': 'Samstag', 'sonntag': 'Sonntag'
        }

        zeiten = []
        for key, label in tage_namen.items():
            tag = oh.get(key)
            if tag and tag.get('von'):
                zeiten.append(f'{label}: {tag["von"]} - {tag["bis"]}')
            else:
                zeiten.append(f'{label}: Geschlossen')

        return {
            'ergebnis': {
                'quelle': quelle,
                'zeiten': zeiten
            }
        }

    elif tool_name == 'feiertage_anzeigen':
        jahr = tool_input.get('jahr', date.today().year)
        feiertage = Holiday.query.filter(
            db.extract('year', Holiday.date) == jahr
        ).order_by(Holiday.date).all()

        if not feiertage:
            return {'ergebnis': f'Keine Feiertage fuer {jahr} definiert.', 'anzahl': 0}

        ergebnisse = []
        for f in feiertage:
            ergebnisse.append({
                'datum': f.date.strftime('%d.%m.%Y'),
                'name': f.name,
                'kanton': f.canton or '-',
                'standort': f.location.name if f.location else 'Alle Standorte'
            })

        return {'ergebnis': ergebnisse, 'anzahl': len(ergebnisse)}

    elif tool_name == 'serienvorlagen_auflisten':
        nur_aktive = tool_input.get('nur_aktive', True)
        query = TreatmentSeriesTemplate.query
        if nur_aktive:
            query = query.filter_by(is_active=True)
        vorlagen = query.order_by(TreatmentSeriesTemplate.name).all()

        if not vorlagen:
            return {'ergebnis': 'Keine Serienvorlagen gefunden.', 'anzahl': 0}

        ergebnisse = []
        for v in vorlagen:
            ergebnisse.append({
                'id': v.id,
                'name': v.name,
                'kurzname': v.short_name or '-',
                'tarif_typ': v.tariff_type or '-',
                'anzahl_termine': v.num_appointments,
                'dauer_minuten': v.duration_minutes,
                'gruppentherapie': v.group_therapy,
                'standort': v.default_location.name if v.default_location else '-',
                'aktiv': v.is_active
            })

        return {'ergebnis': ergebnisse, 'anzahl': len(ergebnisse)}

    elif tool_name == 'taxpunktwert_abfragen':
        tarif_typ = tool_input['tarif_typ']
        heute = date.today()

        # Aktuellen Wert suchen (gueltig heute, kein Ablaufdatum oder noch gueltig)
        tp = TaxPointValue.query.filter(
            TaxPointValue.tariff_type.ilike(f'%{tarif_typ}%'),
            TaxPointValue.valid_from <= heute,
            db.or_(TaxPointValue.valid_to == None, TaxPointValue.valid_to >= heute)
        ).order_by(TaxPointValue.valid_from.desc()).first()

        if not tp:
            return {'ergebnis': f'Kein aktueller Taxpunktwert fuer "{tarif_typ}" gefunden.'}

        return {
            'ergebnis': {
                'tarif_typ': tp.tariff_type,
                'wert_chf': f'{tp.value:.2f}',
                'gueltig_ab': tp.valid_from.strftime('%d.%m.%Y'),
                'gueltig_bis': tp.valid_to.strftime('%d.%m.%Y') if tp.valid_to else 'Unbefristet',
                'kanton': tp.canton or 'Alle',
                'versicherer': tp.insurer.name if tp.insurer else 'Alle'
            }
        }

    return {'error': f'Unbekanntes Tool: {tool_name}'}
