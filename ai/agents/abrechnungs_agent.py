# Abrechnungs-Agent: Spezialist für Rechnungen, Tarife, Mahnwesen, Gutsprachen, Zahlungen
# Kennt alle Schweizer Tarif-Regeln (311/312, 338/325, 590/999)

from datetime import datetime, date, timedelta
from sqlalchemy import or_
from models import (db, Invoice, InvoiceItem, Payment, Patient, TreatmentSeries,
                    TreatmentSeriesTemplate, Employee, InsuranceProvider, Doctor,
                    CostApproval, TaxPointValue, DunningConfig, Appointment, Organization)
from ai.base_agent import BaseAgent

SYSTEM_PROMPT = """Du bist der Abrechnungs-Spezialist der OMNIA Praxissoftware. Du bist Experte für das Schweizer Gesundheitswesen und kennst alle Abrechnungsregeln.

Dein Fachwissen:
- Tarif 311: Physiotherapie UVG/IVG/MVG (48 TP pro 30 Min., Taxpunktwert variiert nach Kanton)
- Tarif 312: Physiotherapie KVG (48 TP pro 30 Min., Taxpunktwert ca. CHF 1.00)
- Tarif 338/325: Ergotherapie (56 TP pro 30 Min.)
- Tarif 590/999: EMR Komplementärmedizin (Pauschal, ca. 108 TP pro 60 Min.)
- Pauschal/Privat: Freie Preisgestaltung, keine Taxpunkte

Abrechnungsmodelle:
- Tiers Garant: Patient zahlt die Rechnung und wird von der Versicherung entschädigt. Mahngebühren werden dem Patienten berechnet.
- Tiers Payant: Versicherung zahlt direkt an die Praxis. Keine Mahngebühren.
- KVG: Normalerweise Tiers Garant (ausser bei Sozialversicherungsfällen)
- UVG/MVG/IVG: Normalerweise Tiers Payant

Versicherungstypen:
- KVG: Grundversicherung
- UVG: Unfallversicherung
- MVG: Militärversicherung
- IVG: Invalidenversicherung
- Privat: Zusatzversicherung
- Selbstzahler: Patient zahlt selbst

Mahnwesen (3 Stufen):
- Stufe 1: Zahlungserinnerung (30 Tage nach Fälligkeit)
- Stufe 2: 1. Mahnung (60 Tage, Gebühr bei Tiers Garant)
- Stufe 3: 2. Mahnung / Inkasso (90 Tage, höhere Gebühr bei Tiers Garant)

Regeln:
- Antworte immer auf Deutsch, kurz und professionell
- Bei Rechnungen: nenne immer Nummer, Betrag, Status und Patient
- Bei Tarifberechnungen: zeige Taxpunkte × Taxpunktwert × Anzahl = Betrag
- Weise auf überfällige Rechnungen hin
- Bei Gutsprachen: nenne Patient, Versicherer und Status"""

TOOLS = [
    {
        "name": "rechnung_erstellen",
        "description": "Erstellt eine Rechnung aus einer abgeschlossenen Behandlungsserie.",
        "input_schema": {
            "type": "object",
            "properties": {
                "serie_id": {"type": "integer", "description": "ID der Behandlungsserie"},
            },
            "required": ["serie_id"]
        }
    },
    {
        "name": "rechnung_anzeigen",
        "description": "Zeigt die Details einer Rechnung an.",
        "input_schema": {
            "type": "object",
            "properties": {
                "rechnung_id": {"type": "integer", "description": "ID der Rechnung"},
            },
            "required": ["rechnung_id"]
        }
    },
    {
        "name": "rechnungen_auflisten",
        "description": "Listet Rechnungen auf, optional gefiltert nach Status oder Patient.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "description": "Status-Filter: open/sent/answered/partially_paid/paid/in_collection"},
                "patient_name": {"type": "string", "description": "Patientenname zum Filtern"},
            },
        }
    },
    {
        "name": "mahnung_senden",
        "description": "Sendet eine Mahnung (nächste Stufe) für eine überfällige Rechnung.",
        "input_schema": {
            "type": "object",
            "properties": {
                "rechnung_id": {"type": "integer", "description": "ID der Rechnung"},
            },
            "required": ["rechnung_id"]
        }
    },
    {
        "name": "zahlung_verbuchen",
        "description": "Verbucht eine Zahlung für eine Rechnung.",
        "input_schema": {
            "type": "object",
            "properties": {
                "rechnung_id": {"type": "integer", "description": "ID der Rechnung"},
                "betrag": {"type": "number", "description": "Zahlungsbetrag in CHF"},
                "referenz": {"type": "string", "description": "Zahlungsreferenz (optional)"},
                "quelle": {"type": "string", "description": "Zahlungsquelle: manual/vesr/medidata", "default": "manual"},
            },
            "required": ["rechnung_id", "betrag"]
        }
    },
    {
        "name": "gutsprache_erstellen",
        "description": "Erstellt eine neue Kostengutsprache.",
        "input_schema": {
            "type": "object",
            "properties": {
                "patient_id": {"type": "integer", "description": "ID des Patienten"},
                "versicherer_id": {"type": "integer", "description": "ID des Versicherers"},
                "arzt_id": {"type": "integer", "description": "ID des verordnenden Arztes"},
                "serie_id": {"type": "integer", "description": "ID der Behandlungsserie (optional)"},
                "diagnose": {"type": "string", "description": "Diagnose"},
                "behandlungsart": {"type": "string", "description": "Art der Behandlung (z.B. Physiotherapie)"},
                "anzahl_sitzungen": {"type": "integer", "description": "Beantragte Anzahl Sitzungen"},
            },
            "required": ["patient_id"]
        }
    },
    {
        "name": "gutsprache_status",
        "description": "Zeigt den Status einer Gutsprache oder listet alle Gutsprachen auf.",
        "input_schema": {
            "type": "object",
            "properties": {
                "gutsprache_id": {"type": "integer", "description": "ID der Gutsprache (optional, wenn leer: alle auflisten)"},
                "patient_name": {"type": "string", "description": "Patientenname zum Filtern"},
            },
        }
    },
    {
        "name": "tarif_berechnen",
        "description": "Berechnet den Betrag für eine Behandlung basierend auf Tarif, Dauer und Taxpunktwert.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tarif": {"type": "string", "description": "Tarif-Code: 311/312/338/325/590/999/flatrate"},
                "dauer_minuten": {"type": "integer", "description": "Behandlungsdauer in Minuten"},
                "anzahl": {"type": "integer", "description": "Anzahl Behandlungen", "default": 1},
                "kanton": {"type": "string", "description": "Kanton (z.B. ZH, BE)", "default": "ZH"},
            },
            "required": ["tarif", "dauer_minuten"]
        }
    },
    {
        "name": "offene_posten_anzeigen",
        "description": "Zeigt alle offenen und überfälligen Rechnungen mit Beträgen.",
        "input_schema": {
            "type": "object",
            "properties": {
                "nur_ueberfaellig": {"type": "boolean", "description": "Nur überfällige Rechnungen anzeigen", "default": False},
            },
        }
    },
]


def _execute_tool(tool_name, tool_input):
    """Führt ein Abrechnungs-Tool aus."""

    if tool_name == 'rechnung_erstellen':
        return _rechnung_erstellen(tool_input)
    elif tool_name == 'rechnung_anzeigen':
        return _rechnung_anzeigen(tool_input)
    elif tool_name == 'rechnungen_auflisten':
        return _rechnungen_auflisten(tool_input)
    elif tool_name == 'mahnung_senden':
        return _mahnung_senden(tool_input)
    elif tool_name == 'zahlung_verbuchen':
        return _zahlung_verbuchen(tool_input)
    elif tool_name == 'gutsprache_erstellen':
        return _gutsprache_erstellen(tool_input)
    elif tool_name == 'gutsprache_status':
        return _gutsprache_status(tool_input)
    elif tool_name == 'tarif_berechnen':
        return _tarif_berechnen(tool_input)
    elif tool_name == 'offene_posten_anzeigen':
        return _offene_posten_anzeigen(tool_input)
    else:
        return {'error': f'Unbekanntes Tool: {tool_name}'}


def _rechnung_erstellen(inp):
    """Erstellt eine Rechnung aus einer Behandlungsserie."""
    serie = TreatmentSeries.query.get(inp['serie_id'])
    if not serie:
        return {'error': f'Serie {inp["serie_id"]} nicht gefunden.'}

    patient = Patient.query.get(serie.patient_id)
    if not patient:
        return {'error': 'Patient nicht gefunden.'}

    # Prüfen ob bereits eine Rechnung existiert
    existing = Invoice.query.filter_by(series_id=serie.id).first()
    if existing:
        return {
            'hinweis': f'Für diese Serie existiert bereits Rechnung {existing.invoice_number} '
                       f'(Status: {existing.status_label}, Betrag: CHF {existing.amount:.2f}).',
            'rechnung_id': existing.id,
        }

    # Tarif und Taxpunktwert bestimmen
    tariff_type = serie.template.tariff_type if serie.template else '312'
    tp_value = TaxPointValue.get_value(tariff_type, 'ZH', patient.insurance_provider_id)
    duration = serie.template.duration_minutes if serie.template else 30

    # Taxpunkte berechnen
    tax_points = _calc_tax_points(tariff_type, duration)

    # Abrechnungsmodell automatisch bestimmen
    billing_model = serie.billing_model
    if not billing_model:
        if serie.insurance_type in ('UVG', 'MVG', 'IVG'):
            billing_model = 'tiers_payant'
        else:
            billing_model = 'tiers_garant'

    # Rechnung erstellen
    invoice = Invoice(
        invoice_number=Invoice.generate_invoice_number(),
        series_id=serie.id,
        patient_id=patient.id,
        insurance_provider_id=patient.insurance_provider_id,
        therapist_id=serie.therapist_id,
        doctor_id=serie.prescribing_doctor_id,
        billing_type=serie.insurance_type or 'KVG',
        billing_model=billing_model,
        tariff_type=tariff_type,
        due_date=date.today() + timedelta(days=30),
    )
    db.session.add(invoice)
    db.session.flush()

    # Positionen erstellen
    appointments = serie.appointments.filter(
        Appointment.status.in_(['completed', 'scheduled'])
    ).order_by(Appointment.start_time).all()

    total = 0
    for i, appt in enumerate(appointments):
        amount = round(tax_points * tp_value, 2)
        item = InvoiceItem(
            invoice_id=invoice.id,
            tariff_code=tariff_type,
            description=f'Behandlung {serie.template.name if serie.template else "Therapie"} ({duration} Min.)',
            quantity=1,
            tax_points=tax_points,
            tax_point_value=tp_value,
            amount=amount,
            appointment_id=appt.id,
            position=i + 1,
        )
        db.session.add(item)
        total += amount

    invoice.amount = round(total, 2)
    invoice.qr_reference = _gen_qr_ref(invoice.id)

    db.session.commit()

    return {
        'erfolg': True,
        'rechnung_id': invoice.id,
        'rechnungsnummer': invoice.invoice_number,
        'patient': patient.full_name,
        'betrag': f'CHF {invoice.amount:.2f}',
        'positionen': len(appointments),
        'tarif': tariff_type,
        'taxpunktwert': tp_value,
        'taxpunkte_pro_sitzung': tax_points,
        'abrechnungsmodell': 'Tiers Garant' if billing_model == 'tiers_garant' else 'Tiers Payant',
        'versicherungstyp': serie.insurance_type or 'KVG',
        'faellig_am': invoice.due_date.strftime('%d.%m.%Y'),
    }


def _rechnung_anzeigen(inp):
    """Zeigt Details einer Rechnung."""
    rechnung = Invoice.query.get(inp['rechnung_id'])
    if not rechnung:
        return {'error': f'Rechnung {inp["rechnung_id"]} nicht gefunden.'}

    positionen = rechnung.items.all()
    zahlungen = rechnung.payments.all()

    return {
        'rechnung_id': rechnung.id,
        'rechnungsnummer': rechnung.invoice_number,
        'patient': rechnung.patient.full_name if rechnung.patient else '-',
        'status': rechnung.status_label,
        'betrag': f'CHF {rechnung.amount:.2f}',
        'bezahlt': f'CHF {rechnung.total_paid:.2f}',
        'offen': f'CHF {rechnung.outstanding:.2f}',
        'versicherungstyp': rechnung.billing_type_label,
        'abrechnungsmodell': 'Tiers Garant' if rechnung.billing_model == 'tiers_garant' else 'Tiers Payant',
        'tarif': rechnung.tariff_type or '-',
        'erstellt': rechnung.created_at.strftime('%d.%m.%Y'),
        'faellig': rechnung.due_date.strftime('%d.%m.%Y') if rechnung.due_date else '-',
        'mahnstufe': rechnung.dunning_level,
        'mahngebuehren': f'CHF {rechnung.dunning_fees:.2f}' if rechnung.dunning_fees else 'CHF 0.00',
        'versicherer': rechnung.insurance_provider.name if rechnung.insurance_provider else '-',
        'therapeut': rechnung.therapist.display_name if rechnung.therapist else '-',
        'positionen': [
            {
                'pos': p.position,
                'tarif': p.tariff_code,
                'beschreibung': p.description,
                'tp': p.tax_points,
                'tp_wert': p.tax_point_value,
                'betrag': f'CHF {p.amount:.2f}',
            } for p in positionen
        ],
        'zahlungen': [
            {
                'datum': z.payment_date.strftime('%d.%m.%Y'),
                'betrag': f'CHF {z.amount:.2f}',
                'quelle': z.source,
                'referenz': z.reference or '-',
            } for z in zahlungen
        ],
    }


def _rechnungen_auflisten(inp):
    """Listet Rechnungen auf."""
    query = Invoice.query.order_by(Invoice.created_at.desc())

    status = inp.get('status')
    if status:
        query = query.filter(Invoice.status == status)

    patient_name = inp.get('patient_name')
    if patient_name:
        query = query.join(Patient).filter(
            or_(
                Patient.first_name.ilike(f'%{patient_name}%'),
                Patient.last_name.ilike(f'%{patient_name}%'),
            )
        )

    rechnungen = query.limit(20).all()

    if not rechnungen:
        return {'hinweis': 'Keine Rechnungen gefunden.', 'rechnungen': []}

    return {
        'anzahl': len(rechnungen),
        'rechnungen': [
            {
                'id': r.id,
                'nummer': r.invoice_number,
                'patient': r.patient.full_name if r.patient else '-',
                'betrag': f'CHF {r.amount:.2f}',
                'offen': f'CHF {r.outstanding:.2f}',
                'status': r.status_label,
                'faellig': r.due_date.strftime('%d.%m.%Y') if r.due_date else '-',
                'mahnstufe': r.dunning_level,
            } for r in rechnungen
        ],
    }


def _mahnung_senden(inp):
    """Sendet eine Mahnung (eskaliert zur nächsten Stufe)."""
    rechnung = Invoice.query.get(inp['rechnung_id'])
    if not rechnung:
        return {'error': f'Rechnung {inp["rechnung_id"]} nicht gefunden.'}

    if rechnung.status == 'paid':
        return {'hinweis': 'Rechnung ist bereits bezahlt.'}

    if rechnung.dunning_level >= 3:
        return {'hinweis': 'Maximale Mahnstufe (3) bereits erreicht. Rechnung ist im Inkasso.'}

    new_level = rechnung.dunning_level + 1

    # Mahngebühr (nur bei Tiers Garant)
    fee = 0
    if rechnung.billing_model == 'tiers_garant':
        config = DunningConfig.query.filter_by(level=new_level).first()
        if config:
            fee = config.fee
        else:
            # Standard-Mahngebühren
            fee = {1: 0, 2: 10.0, 3: 20.0}.get(new_level, 0)

    rechnung.dunning_level = new_level
    rechnung.last_dunning_date = date.today()
    rechnung.dunning_fees = (rechnung.dunning_fees or 0) + fee

    if new_level == 3:
        rechnung.status = 'in_collection'

    db.session.commit()

    stufen_namen = {1: 'Zahlungserinnerung', 2: '1. Mahnung', 3: '2. Mahnung / Inkasso'}

    return {
        'erfolg': True,
        'rechnungsnummer': rechnung.invoice_number,
        'patient': rechnung.patient.full_name if rechnung.patient else '-',
        'mahnstufe': new_level,
        'mahnstufe_name': stufen_namen.get(new_level, f'Stufe {new_level}'),
        'mahngebuehr': f'CHF {fee:.2f}' if fee > 0 else ('Keine (Stufe 1)' if rechnung.billing_model == 'tiers_garant' else 'Keine (Tiers Payant)'),
        'offener_betrag': f'CHF {rechnung.outstanding:.2f}',
        'abrechnungsmodell': 'Tiers Garant' if rechnung.billing_model == 'tiers_garant' else 'Tiers Payant',
    }


def _zahlung_verbuchen(inp):
    """Verbucht eine Zahlung."""
    rechnung = Invoice.query.get(inp['rechnung_id'])
    if not rechnung:
        return {'error': f'Rechnung {inp["rechnung_id"]} nicht gefunden.'}

    betrag = inp['betrag']
    if betrag <= 0:
        return {'error': 'Betrag muss grösser als 0 sein.'}

    zahlung = Payment(
        invoice_id=rechnung.id,
        amount=betrag,
        payment_date=date.today(),
        reference=inp.get('referenz', ''),
        source=inp.get('quelle', 'manual'),
    )
    db.session.add(zahlung)

    # Status aktualisieren
    total_paid = rechnung.total_paid + betrag
    total_due = (rechnung.amount or 0) + (rechnung.dunning_fees or 0)

    if total_paid >= total_due:
        rechnung.status = 'paid'
        rechnung.paid_at = datetime.utcnow()
        status_text = 'vollständig bezahlt'
    elif total_paid > 0:
        rechnung.status = 'partially_paid'
        status_text = 'teilbezahlt'
    else:
        status_text = rechnung.status_label

    db.session.commit()

    return {
        'erfolg': True,
        'rechnungsnummer': rechnung.invoice_number,
        'patient': rechnung.patient.full_name if rechnung.patient else '-',
        'zahlung': f'CHF {betrag:.2f}',
        'total_bezahlt': f'CHF {total_paid:.2f}',
        'offen': f'CHF {rechnung.outstanding:.2f}',
        'neuer_status': status_text,
    }


def _gutsprache_erstellen(inp):
    """Erstellt eine Kostengutsprache."""
    patient = Patient.query.get(inp['patient_id'])
    if not patient:
        return {'error': f'Patient {inp["patient_id"]} nicht gefunden.'}

    gutsprache = CostApproval(
        patient_id=patient.id,
        insurance_provider_id=inp.get('versicherer_id', patient.insurance_provider_id),
        doctor_id=inp.get('arzt_id'),
        series_id=inp.get('serie_id'),
        diagnosis=inp.get('diagnose', ''),
        treatment_type=inp.get('behandlungsart', ''),
        approved_sessions=inp.get('anzahl_sitzungen'),
        valid_until=date.today() + timedelta(days=90),
    )
    db.session.add(gutsprache)
    db.session.commit()

    return {
        'erfolg': True,
        'gutsprache_id': gutsprache.id,
        'patient': patient.full_name,
        'versicherer': gutsprache.insurance_provider.name if gutsprache.insurance_provider else '-',
        'arzt': gutsprache.doctor.name if gutsprache.doctor else '-',
        'status': gutsprache.status_label,
        'gueltig_bis': gutsprache.valid_until.strftime('%d.%m.%Y') if gutsprache.valid_until else '-',
    }


def _gutsprache_status(inp):
    """Zeigt Gutsprachen-Status oder listet alle auf."""
    gutsprache_id = inp.get('gutsprache_id')
    if gutsprache_id:
        gs = CostApproval.query.get(gutsprache_id)
        if not gs:
            return {'error': f'Gutsprache {gutsprache_id} nicht gefunden.'}
        return {
            'gutsprache_id': gs.id,
            'patient': gs.patient.full_name if gs.patient else '-',
            'versicherer': gs.insurance_provider.name if gs.insurance_provider else '-',
            'arzt': gs.doctor.name if gs.doctor else '-',
            'status': gs.status_label,
            'diagnose': gs.diagnosis or '-',
            'behandlungsart': gs.treatment_type or '-',
            'bewilligte_sitzungen': gs.approved_sessions or '-',
            'bewilligter_betrag': f'CHF {gs.approved_amount:.2f}' if gs.approved_amount else '-',
            'gueltig_bis': gs.valid_until.strftime('%d.%m.%Y') if gs.valid_until else '-',
            'erstellt': gs.created_at.strftime('%d.%m.%Y'),
        }

    # Alle Gutsprachen auflisten
    query = CostApproval.query.order_by(CostApproval.created_at.desc())
    patient_name = inp.get('patient_name')
    if patient_name:
        query = query.join(Patient).filter(
            or_(
                Patient.first_name.ilike(f'%{patient_name}%'),
                Patient.last_name.ilike(f'%{patient_name}%'),
            )
        )

    gutsprachen = query.limit(20).all()
    return {
        'anzahl': len(gutsprachen),
        'gutsprachen': [
            {
                'id': gs.id,
                'patient': gs.patient.full_name if gs.patient else '-',
                'versicherer': gs.insurance_provider.name if gs.insurance_provider else '-',
                'status': gs.status_label,
                'behandlungsart': gs.treatment_type or '-',
                'erstellt': gs.created_at.strftime('%d.%m.%Y'),
            } for gs in gutsprachen
        ],
    }


def _tarif_berechnen(inp):
    """Berechnet den Betrag für eine Behandlung."""
    tarif = inp['tarif']
    dauer = inp['dauer_minuten']
    anzahl = inp.get('anzahl', 1)
    kanton = inp.get('kanton', 'ZH')

    if tarif == 'flatrate':
        return {
            'tarif': 'Pauschal/Privat',
            'hinweis': 'Bei Pauschal/Privat gibt es keine Taxpunkte. Der Preis wird frei vereinbart.',
        }

    # Taxpunkte berechnen
    tax_points = _calc_tax_points(tarif, dauer)
    tp_value = TaxPointValue.get_value(tarif, kanton)
    betrag_pro_sitzung = round(tax_points * tp_value, 2)
    total = round(betrag_pro_sitzung * anzahl, 2)

    tarif_namen = {
        '311': 'Physiotherapie UVG/IVG/MVG',
        '312': 'Physiotherapie KVG',
        '338': 'Ergotherapie',
        '325': 'Ergotherapie',
        '590': 'EMR Komplementärmedizin',
        '999': 'EMR Komplementärmedizin',
    }

    return {
        'tarif': tarif,
        'tarif_name': tarif_namen.get(tarif, tarif),
        'dauer_minuten': dauer,
        'taxpunkte': tax_points,
        'taxpunktwert': f'CHF {tp_value:.4f}',
        'kanton': kanton,
        'betrag_pro_sitzung': f'CHF {betrag_pro_sitzung:.2f}',
        'anzahl_sitzungen': anzahl,
        'total': f'CHF {total:.2f}',
        'berechnung': f'{tax_points} TP × CHF {tp_value:.4f} × {anzahl} = CHF {total:.2f}',
    }


def _offene_posten_anzeigen(inp):
    """Zeigt alle offenen und überfälligen Rechnungen."""
    nur_ueberfaellig = inp.get('nur_ueberfaellig', False)
    today = date.today()

    query = Invoice.query.filter(
        Invoice.status.in_(['open', 'sent', 'answered', 'partially_paid'])
    )

    if nur_ueberfaellig:
        query = query.filter(Invoice.due_date < today)

    rechnungen = query.order_by(Invoice.due_date).all()

    total_offen = sum(r.outstanding for r in rechnungen)
    total_ueberfaellig = sum(r.outstanding for r in rechnungen if r.due_date and r.due_date < today)

    return {
        'anzahl': len(rechnungen),
        'total_offen': f'CHF {total_offen:.2f}',
        'total_ueberfaellig': f'CHF {total_ueberfaellig:.2f}',
        'rechnungen': [
            {
                'id': r.id,
                'nummer': r.invoice_number,
                'patient': r.patient.full_name if r.patient else '-',
                'betrag': f'CHF {r.amount:.2f}',
                'offen': f'CHF {r.outstanding:.2f}',
                'faellig': r.due_date.strftime('%d.%m.%Y') if r.due_date else '-',
                'ueberfaellig': r.is_overdue,
                'tage_ueberfaellig': (today - r.due_date).days if r.due_date and r.due_date < today else 0,
                'mahnstufe': r.dunning_level,
                'status': r.status_label,
            } for r in rechnungen
        ],
    }


def _calc_tax_points(tariff_type, duration_minutes):
    """Berechnet Taxpunkte basierend auf Tarif und Dauer."""
    tp_map = {
        '311': 48.0, '312': 48.0,
        '338': 56.0, '325': 56.0,
        '590': 54.0, '999': 54.0,
    }
    base_tp = tp_map.get(tariff_type, 48.0)
    return round(base_tp * (duration_minutes / 30.0), 1)


def _gen_qr_ref(invoice_id):
    """Generiert eine QR-Referenznummer."""
    ref_base = str(invoice_id).zfill(26)
    checksum = sum(int(d) for d in ref_base) % 10
    return ref_base + str(checksum)


def create_abrechnungs_agent():
    """Erstellt den Abrechnungs-Agenten."""
    return BaseAgent(
        name='abrechnungs_agent',
        system_prompt=SYSTEM_PROMPT,
        tools=TOOLS,
        tool_executor=_execute_tool,
    )
