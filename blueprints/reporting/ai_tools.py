"""KI-Tools fuer das Auswertungs- und Kennzahlen-Modul"""
import json
from datetime import date, datetime, timedelta
from flask_login import current_user
from services.reporting_service import (
    run_report, calculate_kpis, calculate_therapist_scorecard,
    get_report_categories, get_revenue_chart_data
)
from models import db, Employee, Patient, Appointment, Invoice, TreatmentSeries
from sqlalchemy import func


REPORTING_TOOLS = [
    {
        'name': 'auswertung_erstellen',
        'description': 'Erstellt eine Auswertung (Report) fuer eine bestimmte Kategorie mit Filtern und Spalten. Kategorien: patients, appointments, series, invoices, employees, products.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'kategorie': {
                    'type': 'string',
                    'description': 'Kategorie der Auswertung',
                    'enum': ['patients', 'appointments', 'series', 'invoices', 'employees', 'products']
                },
                'filter': {
                    'type': 'object',
                    'description': 'Filter als Key-Value-Paare (z.B. date_from, date_to, status, employee_id, insurance_type, search)',
                },
                'spalten': {
                    'type': 'array',
                    'items': {'type': 'string'},
                    'description': 'Liste der gewuenschten Spalten-Keys (leer = alle Spalten)'
                }
            },
            'required': ['kategorie']
        }
    },
    {
        'name': 'kpi_abfragen',
        'description': 'Fragt einen oder mehrere KPIs fuer einen bestimmten Zeitraum ab. Verfuegbare KPIs: umsatz, offene_posten, neupatienten, behandlungen, auslastung, no_show_rate, absagequote, avg_seriendauer, umsatz_pro_therapeut, patienten_pro_therapeut, mahnquote, avg_zahlungsfrist.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'kpi_name': {
                    'type': 'string',
                    'description': 'Name des KPI (oder "alle" fuer alle KPIs)'
                },
                'zeitraum': {
                    'type': 'string',
                    'description': 'Zeitraum: "monat", "quartal", "jahr" oder "YYYY-MM-DD bis YYYY-MM-DD"'
                }
            },
            'required': ['kpi_name']
        }
    },
    {
        'name': 'umsatz_zeitraum',
        'description': 'Berechnet den Umsatz in einem bestimmten Zeitraum.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'von': {'type': 'string', 'description': 'Startdatum (YYYY-MM-DD)'},
                'bis': {'type': 'string', 'description': 'Enddatum (YYYY-MM-DD)'}
            },
            'required': ['von', 'bis']
        }
    },
    {
        'name': 'auslastung_therapeut',
        'description': 'Berechnet die Auslastung eines bestimmten Therapeuten.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'employee_id': {'type': 'integer', 'description': 'ID des Mitarbeiters'},
                'monat': {'type': 'integer', 'description': 'Monat (1-12)'},
                'jahr': {'type': 'integer', 'description': 'Jahr'}
            },
            'required': ['employee_id']
        }
    },
    {
        'name': 'neupatienten_monat',
        'description': 'Gibt die Anzahl der Neupatienten in einem bestimmten Monat zurueck.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'monat': {'type': 'integer', 'description': 'Monat (1-12)'},
                'jahr': {'type': 'integer', 'description': 'Jahr'}
            },
            'required': ['monat', 'jahr']
        }
    },
    {
        'name': 'top_diagnosen',
        'description': 'Gibt die haeufigsten Diagnosen in einem Zeitraum zurueck.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'zeitraum': {'type': 'string', 'description': 'Zeitraum: "monat", "quartal", "jahr"'},
                'limit': {'type': 'integer', 'description': 'Maximale Anzahl Ergebnisse (Standard: 10)'}
            }
        }
    },
    {
        'name': 'vergleich_vorjahr',
        'description': 'Vergleicht einen KPI mit dem Vorjahr.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'kpi_name': {'type': 'string', 'description': 'Name des KPI'},
                'monat': {'type': 'integer', 'description': 'Monat (1-12)'},
                'jahr': {'type': 'integer', 'description': 'Jahr (leer = aktuelles Jahr)'}
            },
            'required': ['kpi_name']
        }
    }
]


def _parse_zeitraum(zeitraum):
    """Hilfsfunktion: Zeitraum-String zu date_from, date_to"""
    today = date.today()

    if not zeitraum or zeitraum == 'monat':
        d_from = today.replace(day=1)
        if today.month == 12:
            d_to = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            d_to = today.replace(month=today.month + 1, day=1) - timedelta(days=1)
        return d_from, d_to

    if zeitraum == 'quartal':
        q = ((today.month - 1) // 3) * 3 + 1
        d_from = today.replace(month=q, day=1)
        end_m = q + 2
        if end_m > 12:
            d_to = today.replace(year=today.year + 1, month=end_m - 12 + 1, day=1) - timedelta(days=1)
        else:
            d_to = today.replace(month=end_m + 1, day=1) - timedelta(days=1)
        return d_from, d_to

    if zeitraum == 'jahr':
        return today.replace(month=1, day=1), today.replace(month=12, day=31)

    # Benutzerdefiniert: "YYYY-MM-DD bis YYYY-MM-DD"
    if ' bis ' in zeitraum:
        parts = zeitraum.split(' bis ')
        try:
            d_from = datetime.strptime(parts[0].strip(), '%Y-%m-%d').date()
            d_to = datetime.strptime(parts[1].strip(), '%Y-%m-%d').date()
            return d_from, d_to
        except (ValueError, IndexError):
            pass

    return today.replace(day=1), today


def reporting_tool_executor(tool_name, tool_input):
    """Fuehrt Reporting-Tools aus"""
    org_id = current_user.organization_id if current_user and hasattr(current_user, 'organization_id') else 1

    if tool_name == 'auswertung_erstellen':
        kategorie = tool_input.get('kategorie', 'patients')
        filter_dict = tool_input.get('filter', {})
        spalten = tool_input.get('spalten', [])

        result = run_report(kategorie, filter_dict, spalten, org_id, page=1, per_page=20)
        cat_labels = get_report_categories()
        return {
            'kategorie': cat_labels.get(kategorie, kategorie),
            'anzahl_ergebnisse': result['total_count'],
            'spalten': result['headers'],
            'daten': result['rows'][:20],
            'summen': result.get('totals', {}),
            'hinweis': f"Es wurden {result['total_count']} Ergebnisse gefunden. Hier die ersten {min(20, len(result['rows']))} Eintraege."
        }

    elif tool_name == 'kpi_abfragen':
        kpi_name = tool_input.get('kpi_name', 'alle')
        zeitraum = tool_input.get('zeitraum', 'monat')
        d_from, d_to = _parse_zeitraum(zeitraum)

        kpis = calculate_kpis(d_from, d_to, org_id)

        if kpi_name == 'alle':
            kpi_labels = {
                'umsatz': 'Umsatz (CHF)', 'offene_posten': 'Offene Posten (CHF)',
                'neupatienten': 'Neupatienten', 'behandlungen': 'Behandlungen',
                'auslastung': 'Auslastung (%)', 'no_show_rate': 'No-Show-Rate (%)',
                'absagequote': 'Absagequote (%)', 'avg_seriendauer': 'Ø Seriendauer (Tage)',
                'umsatz_pro_therapeut': 'Umsatz pro Therapeut (CHF)',
                'patienten_pro_therapeut': 'Patienten pro Therapeut',
                'mahnquote': 'Mahnquote (%)', 'avg_zahlungsfrist': 'Ø Zahlungsfrist (Tage)'
            }
            return {
                'zeitraum': f"{d_from.strftime('%d.%m.%Y')} bis {d_to.strftime('%d.%m.%Y')}",
                'kpis': {kpi_labels.get(k, k): v for k, v in kpis.items() if k in kpi_labels}
            }
        else:
            val = kpis.get(kpi_name)
            return {
                'kpi': kpi_name,
                'wert': val,
                'zeitraum': f"{d_from.strftime('%d.%m.%Y')} bis {d_to.strftime('%d.%m.%Y')}"
            }

    elif tool_name == 'umsatz_zeitraum':
        von = tool_input.get('von')
        bis = tool_input.get('bis')
        kpis = calculate_kpis(von, bis, org_id)
        return {
            'zeitraum': f"{von} bis {bis}",
            'umsatz': kpis['umsatz'],
            'offene_posten': kpis['offene_posten'],
            'behandlungen': kpis['behandlungen']
        }

    elif tool_name == 'auslastung_therapeut':
        emp_id = tool_input.get('employee_id')
        monat = tool_input.get('monat', date.today().month)
        jahr = tool_input.get('jahr', date.today().year)

        d_from = date(jahr, monat, 1)
        if monat == 12:
            d_to = date(jahr + 1, 1, 1) - timedelta(days=1)
        else:
            d_to = date(jahr, monat + 1, 1) - timedelta(days=1)

        kpis = calculate_kpis(d_from, d_to, org_id, employee_id=emp_id)
        emp = Employee.query.get(emp_id)
        name = f"{emp.user.first_name} {emp.user.last_name}" if emp and emp.user else f"ID {emp_id}"
        return {
            'therapeut': name,
            'zeitraum': f"{monat:02d}/{jahr}",
            'auslastung': kpis['auslastung'],
            'behandlungen': kpis['behandlungen'],
            'behandlungsminuten': kpis['behandlungsminuten'],
            'arbeitsminuten': kpis['arbeitsminuten']
        }

    elif tool_name == 'neupatienten_monat':
        monat = tool_input.get('monat')
        jahr = tool_input.get('jahr')
        d_from = date(jahr, monat, 1)
        if monat == 12:
            d_to = date(jahr + 1, 1, 1) - timedelta(days=1)
        else:
            d_to = date(jahr, monat + 1, 1) - timedelta(days=1)

        count = Patient.query.filter(
            Patient.organization_id == org_id,
            Patient.created_at >= datetime.combine(d_from, datetime.min.time()),
            Patient.created_at <= datetime.combine(d_to, datetime.max.time())
        ).count()
        return {'monat': f"{monat:02d}/{jahr}", 'neupatienten': count}

    elif tool_name == 'top_diagnosen':
        zeitraum = tool_input.get('zeitraum', 'monat')
        limit = tool_input.get('limit', 10)
        d_from, d_to = _parse_zeitraum(zeitraum)

        results = db.session.query(
            TreatmentSeries.diagnosis_text,
            func.count(TreatmentSeries.id).label('count')
        ).join(Patient).filter(
            Patient.organization_id == org_id,
            TreatmentSeries.created_at >= datetime.combine(d_from, datetime.min.time()),
            TreatmentSeries.created_at <= datetime.combine(d_to, datetime.max.time()),
            TreatmentSeries.diagnosis_text.isnot(None),
            TreatmentSeries.diagnosis_text != ''
        ).group_by(TreatmentSeries.diagnosis_text).order_by(func.count(TreatmentSeries.id).desc()).limit(limit).all()

        return {
            'zeitraum': f"{d_from.strftime('%d.%m.%Y')} bis {d_to.strftime('%d.%m.%Y')}",
            'diagnosen': [{'diagnose': r[0], 'anzahl': r[1]} for r in results]
        }

    elif tool_name == 'vergleich_vorjahr':
        kpi_name = tool_input.get('kpi_name')
        monat = tool_input.get('monat', date.today().month)
        jahr = tool_input.get('jahr', date.today().year)

        d_from = date(jahr, monat, 1)
        if monat == 12:
            d_to = date(jahr + 1, 1, 1) - timedelta(days=1)
        else:
            d_to = date(jahr, monat + 1, 1) - timedelta(days=1)

        kpis_aktuell = calculate_kpis(d_from, d_to, org_id)
        d_from_prev = d_from.replace(year=d_from.year - 1)
        try:
            d_to_prev = d_to.replace(year=d_to.year - 1)
        except ValueError:
            d_to_prev = d_to.replace(year=d_to.year - 1, day=28)
        kpis_prev = calculate_kpis(d_from_prev, d_to_prev, org_id)

        curr = kpis_aktuell.get(kpi_name, 0)
        prev = kpis_prev.get(kpi_name, 0)
        if prev != 0:
            change = round((curr - prev) / prev * 100, 1)
        elif curr > 0:
            change = 100.0
        else:
            change = 0.0

        return {
            'kpi': kpi_name,
            'aktuell': curr,
            'vorjahr': prev,
            'veraenderung_prozent': change,
            'trend': 'gestiegen' if change > 0 else ('gesunken' if change < 0 else 'gleich'),
            'zeitraum_aktuell': f"{d_from.strftime('%d.%m.%Y')} bis {d_to.strftime('%d.%m.%Y')}",
            'zeitraum_vorjahr': f"{d_from_prev.strftime('%d.%m.%Y')} bis {d_to_prev.strftime('%d.%m.%Y')}"
        }

    return {'error': f'Unbekanntes Tool: {tool_name}'}
