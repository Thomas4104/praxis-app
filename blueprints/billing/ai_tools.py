"""KI-Tools fuer den Abrechnungs-Bereich"""
import json
from datetime import datetime, date, timedelta
from models import (db, Invoice, InvoiceItem, Payment, TaxPointValue, TreatmentSeries,
                    Patient, InsuranceProvider, DunningRecord)
from services.billing_service import (
    create_invoice_from_series, record_payment, process_dunning,
    run_dunning_batch, get_tax_point_value, calculate_invoice_from_series
)


BILLING_TOOLS = [
    {
        'name': 'rechnung_erstellen',
        'description': 'Erstellt eine neue Rechnung aus einer Behandlungsserie. Berechnet automatisch Positionen, Taxpunkte und Betraege.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'serie_id': {'type': 'integer', 'description': 'ID der Behandlungsserie'}
            },
            'required': ['serie_id']
        }
    },
    {
        'name': 'rechnung_details',
        'description': 'Zeigt Details einer Rechnung an: Positionen, Zahlungen, Mahnungen, Status.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'rechnung_id': {'type': 'integer', 'description': 'ID der Rechnung'}
            },
            'required': ['rechnung_id']
        }
    },
    {
        'name': 'rechnungen_auflisten',
        'description': 'Listet Rechnungen auf, optional gefiltert nach Status, Patient oder Zeitraum.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'status': {'type': 'string', 'description': 'Statusfilter: draft, checked, sent, paid, partially_paid, overdue, cancelled'},
                'patient_id': {'type': 'integer', 'description': 'ID des Patienten'},
                'zeitraum_von': {'type': 'string', 'description': 'Von-Datum (YYYY-MM-DD)'},
                'zeitraum_bis': {'type': 'string', 'description': 'Bis-Datum (YYYY-MM-DD)'}
            },
            'required': []
        }
    },
    {
        'name': 'zahlung_verbuchen',
        'description': 'Verbucht eine Zahlung auf eine Rechnung. Aktualisiert automatisch offenen Betrag und Status.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'rechnung_id': {'type': 'integer', 'description': 'ID der Rechnung'},
                'betrag': {'type': 'number', 'description': 'Zahlungsbetrag in CHF'},
                'datum': {'type': 'string', 'description': 'Zahlungsdatum (YYYY-MM-DD), Standard: heute'},
                'methode': {'type': 'string', 'description': 'Zahlungsmethode: bank_transfer, credit_card, twint, cash, esr_qr'}
            },
            'required': ['rechnung_id', 'betrag']
        }
    },
    {
        'name': 'mahnung_senden',
        'description': 'Sendet die naechste Mahnstufe fuer eine Rechnung. Eskaliert automatisch (1. -> 2. -> 3. Mahnung).',
        'input_schema': {
            'type': 'object',
            'properties': {
                'rechnung_id': {'type': 'integer', 'description': 'ID der Rechnung'}
            },
            'required': ['rechnung_id']
        }
    },
    {
        'name': 'offene_posten',
        'description': 'Zeigt alle offenen Rechnungen mit Gesamtsumme an.',
        'input_schema': {
            'type': 'object',
            'properties': {},
            'required': []
        }
    },
    {
        'name': 'ueberfaellige_rechnungen',
        'description': 'Zeigt alle ueberfaelligen Rechnungen mit Faelligkeit und Mahnstufe.',
        'input_schema': {
            'type': 'object',
            'properties': {},
            'required': []
        }
    },
    {
        'name': 'tarif_berechnen',
        'description': 'Berechnet den Betrag fuer eine Tarifposition basierend auf Taxpunkten und Taxpunktwert.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'tarif_typ': {'type': 'string', 'description': 'Tariftyp: TarReha, Tarif 312, Tarif 311, Physiotarif, Tarif 590'},
                'taxpunkte': {'type': 'number', 'description': 'Anzahl Taxpunkte'},
                'anzahl': {'type': 'integer', 'description': 'Anzahl Sitzungen/Leistungen'}
            },
            'required': ['tarif_typ', 'taxpunkte', 'anzahl']
        }
    },
    {
        'name': 'umsatz_zeitraum',
        'description': 'Berechnet den Umsatz (bezahlte Rechnungen) in einem bestimmten Zeitraum.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'von_datum': {'type': 'string', 'description': 'Von-Datum (YYYY-MM-DD)'},
                'bis_datum': {'type': 'string', 'description': 'Bis-Datum (YYYY-MM-DD)'}
            },
            'required': ['von_datum', 'bis_datum']
        }
    },
    {
        'name': 'mahnlauf_starten',
        'description': 'Startet einen automatischen Mahnlauf fuer alle faelligen Rechnungen. Prueft alle offenen Rechnungen und mahnt nach Einstellungen.',
        'input_schema': {
            'type': 'object',
            'properties': {},
            'required': []
        }
    }
]


def billing_tool_executor(tool_name, tool_input):
    """Fuehrt Abrechnungs-Tools aus"""
    from flask_login import current_user
    org_id = current_user.organization_id

    if tool_name == 'rechnung_erstellen':
        serie_id = tool_input.get('serie_id')
        invoice, error = create_invoice_from_series(serie_id, org_id)
        if error:
            return {'error': error}
        return {
            'success': True,
            'rechnung_id': invoice.id,
            'rechnungsnummer': invoice.invoice_number,
            'betrag_total': invoice.amount_total,
            'patient': f'{invoice.patient.first_name} {invoice.patient.last_name}' if invoice.patient else '-',
            'status': invoice.status,
            'faellig_am': invoice.due_date.strftime('%d.%m.%Y') if invoice.due_date else '-'
        }

    elif tool_name == 'rechnung_details':
        rechnung_id = tool_input.get('rechnung_id')
        invoice = Invoice.query.get(rechnung_id)
        if not invoice:
            return {'error': 'Rechnung nicht gefunden.'}

        items = InvoiceItem.query.filter_by(invoice_id=rechnung_id).order_by(InvoiceItem.position).all()
        payments = Payment.query.filter_by(invoice_id=rechnung_id).order_by(Payment.payment_date.desc()).all()
        dunnings = DunningRecord.query.filter_by(invoice_id=rechnung_id).order_by(DunningRecord.dunning_date.desc()).all()

        return {
            'rechnungsnummer': invoice.invoice_number,
            'status': invoice.status,
            'patient': f'{invoice.patient.first_name} {invoice.patient.last_name}' if invoice.patient else '-',
            'versicherung': invoice.insurance_provider.name if invoice.insurance_provider else '-',
            'typ': invoice.billing_type,
            'modell': invoice.billing_model,
            'betrag_total': invoice.amount_total,
            'betrag_bezahlt': invoice.amount_paid,
            'betrag_offen': invoice.amount_open,
            'faellig_am': invoice.due_date.strftime('%d.%m.%Y') if invoice.due_date else '-',
            'mahnstufe': invoice.dunning_level or 0,
            'positionen': [{
                'position': i.position,
                'tarifziffer': i.tariff_code,
                'beschreibung': i.description,
                'anzahl': i.quantity,
                'taxpunkte': i.tax_points,
                'tp_wert': i.tax_point_value,
                'betrag': i.amount
            } for i in items],
            'zahlungen': [{
                'datum': p.payment_date.strftime('%d.%m.%Y') if p.payment_date else '-',
                'betrag': p.amount,
                'methode': p.payment_method
            } for p in payments],
            'mahnungen': [{
                'stufe': d.dunning_level,
                'datum': d.dunning_date.strftime('%d.%m.%Y') if d.dunning_date else '-',
                'gebuehr': d.dunning_fee
            } for d in dunnings]
        }

    elif tool_name == 'rechnungen_auflisten':
        query = Invoice.query.filter_by(organization_id=org_id)

        if tool_input.get('status'):
            query = query.filter(Invoice.status == tool_input['status'])
        if tool_input.get('patient_id'):
            query = query.filter(Invoice.patient_id == tool_input['patient_id'])
        if tool_input.get('zeitraum_von'):
            try:
                df = datetime.strptime(tool_input['zeitraum_von'], '%Y-%m-%d').date()
                query = query.filter(Invoice.created_at >= datetime.combine(df, datetime.min.time()))
            except ValueError:
                pass
        if tool_input.get('zeitraum_bis'):
            try:
                dt = datetime.strptime(tool_input['zeitraum_bis'], '%Y-%m-%d').date()
                query = query.filter(Invoice.created_at <= datetime.combine(dt, datetime.max.time()))
            except ValueError:
                pass

        rechnungen = query.order_by(Invoice.created_at.desc()).limit(50).all()
        return {
            'anzahl': len(rechnungen),
            'rechnungen': [{
                'id': r.id,
                'rechnungsnummer': r.invoice_number,
                'patient': f'{r.patient.first_name} {r.patient.last_name}' if r.patient else '-',
                'betrag_total': r.amount_total,
                'betrag_offen': r.amount_open,
                'status': r.status,
                'faellig_am': r.due_date.strftime('%d.%m.%Y') if r.due_date else '-'
            } for r in rechnungen]
        }

    elif tool_name == 'zahlung_verbuchen':
        rechnung_id = tool_input.get('rechnung_id')
        betrag = tool_input.get('betrag')
        datum = tool_input.get('datum', date.today().strftime('%Y-%m-%d'))
        methode = tool_input.get('methode', 'bank_transfer')

        payment, error = record_payment(rechnung_id, betrag, datum, methode)
        if error:
            return {'error': error}

        invoice = Invoice.query.get(rechnung_id)
        return {
            'success': True,
            'zahlung_betrag': betrag,
            'neuer_status': invoice.status,
            'betrag_bezahlt': invoice.amount_paid,
            'betrag_offen': invoice.amount_open
        }

    elif tool_name == 'mahnung_senden':
        rechnung_id = tool_input.get('rechnung_id')
        record, error = process_dunning(rechnung_id, org_id)
        if error:
            return {'error': error}
        return {
            'success': True,
            'mahnstufe': record.dunning_level,
            'mahngebuehr': record.dunning_fee,
            'mahndatum': record.dunning_date.strftime('%d.%m.%Y') if record.dunning_date else '-'
        }

    elif tool_name == 'offene_posten':
        offene = Invoice.query.filter(
            Invoice.organization_id == org_id,
            Invoice.status.in_(['sent', 'partially_paid', 'overdue']),
            Invoice.amount_open > 0
        ).order_by(Invoice.due_date.asc()).all()

        total_offen = sum(r.amount_open or 0 for r in offene)
        return {
            'anzahl': len(offene),
            'total_offen': round(total_offen, 2),
            'rechnungen': [{
                'id': r.id,
                'rechnungsnummer': r.invoice_number,
                'patient': f'{r.patient.first_name} {r.patient.last_name}' if r.patient else '-',
                'betrag_offen': r.amount_open,
                'faellig_am': r.due_date.strftime('%d.%m.%Y') if r.due_date else '-',
                'mahnstufe': r.dunning_level or 0
            } for r in offene]
        }

    elif tool_name == 'ueberfaellige_rechnungen':
        ueberfaellige = Invoice.query.filter(
            Invoice.organization_id == org_id,
            Invoice.status.in_(['sent', 'overdue', 'partially_paid']),
            Invoice.due_date < date.today(),
            Invoice.amount_open > 0
        ).order_by(Invoice.due_date.asc()).all()

        total = sum(r.amount_open or 0 for r in ueberfaellige)
        return {
            'anzahl': len(ueberfaellige),
            'total_ueberfaellig': round(total, 2),
            'rechnungen': [{
                'id': r.id,
                'rechnungsnummer': r.invoice_number,
                'patient': f'{r.patient.first_name} {r.patient.last_name}' if r.patient else '-',
                'betrag_offen': r.amount_open,
                'faellig_am': r.due_date.strftime('%d.%m.%Y') if r.due_date else '-',
                'tage_ueberfaellig': (date.today() - r.due_date).days if r.due_date else 0,
                'mahnstufe': r.dunning_level or 0
            } for r in ueberfaellige]
        }

    elif tool_name == 'tarif_berechnen':
        tarif_typ = tool_input.get('tarif_typ', 'Tarif 312')
        taxpunkte = tool_input.get('taxpunkte', 0)
        anzahl = tool_input.get('anzahl', 1)

        tp_wert = get_tax_point_value(org_id, tarif_typ)
        betrag_pro_sitzung = round(taxpunkte * tp_wert, 2)
        betrag_total = round(betrag_pro_sitzung * anzahl, 2)

        return {
            'tarif_typ': tarif_typ,
            'taxpunkte': taxpunkte,
            'taxpunktwert': tp_wert,
            'anzahl': anzahl,
            'betrag_pro_sitzung': betrag_pro_sitzung,
            'betrag_total': betrag_total
        }

    elif tool_name == 'umsatz_zeitraum':
        von = tool_input.get('von_datum')
        bis = tool_input.get('bis_datum')

        try:
            von_date = datetime.strptime(von, '%Y-%m-%d').date()
            bis_date = datetime.strptime(bis, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return {'error': 'Ungueltiges Datumsformat. Bitte YYYY-MM-DD verwenden.'}

        # Bezahlte Summe
        bezahlt = db.session.query(db.func.sum(Payment.amount)).join(
            Invoice, Payment.invoice_id == Invoice.id
        ).filter(
            Invoice.organization_id == org_id,
            Payment.payment_date >= von_date,
            Payment.payment_date <= bis_date
        ).scalar() or 0

        # Erstellte Rechnungen
        erstellt = db.session.query(db.func.sum(Invoice.amount_total)).filter(
            Invoice.organization_id == org_id,
            Invoice.created_at >= datetime.combine(von_date, datetime.min.time()),
            Invoice.created_at <= datetime.combine(bis_date, datetime.max.time()),
            Invoice.status != 'cancelled'
        ).scalar() or 0

        return {
            'zeitraum': f'{von_date.strftime("%d.%m.%Y")} - {bis_date.strftime("%d.%m.%Y")}',
            'umsatz_bezahlt': round(bezahlt, 2),
            'umsatz_erstellt': round(erstellt, 2)
        }

    elif tool_name == 'mahnlauf_starten':
        results = run_dunning_batch(org_id)
        return {
            'success': True,
            'anzahl_mahnungen': len(results),
            'mahnungen': results
        }

    return {'error': f'Unbekanntes Tool: {tool_name}'}
