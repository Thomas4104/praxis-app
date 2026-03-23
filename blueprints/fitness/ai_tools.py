"""KI-Tools fuer den Fitness-Bereich"""
import json
from datetime import datetime, date, timedelta
from models import (db, SubscriptionTemplate, Subscription, FitnessVisit,
                    Patient, Location, Invoice)
from sqlalchemy import func, or_


FITNESS_TOOLS = [
    {
        'name': 'abo_suchen',
        'description': 'Sucht das Abo eines Patienten anhand des Namens.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'patient_name': {'type': 'string', 'description': 'Name des Patienten (Vor- oder Nachname)'}
            },
            'required': ['patient_name']
        }
    },
    {
        'name': 'abo_erstellen',
        'description': 'Erstellt ein neues Fitness-Abonnement fuer einen Patienten.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'patient_id': {'type': 'integer', 'description': 'ID des Patienten'},
                'vorlage_id': {'type': 'integer', 'description': 'ID der Abo-Vorlage'},
                'startdatum': {'type': 'string', 'description': 'Startdatum (YYYY-MM-DD), Standard: heute'}
            },
            'required': ['patient_id', 'vorlage_id']
        }
    },
    {
        'name': 'abo_status',
        'description': 'Zeigt Status und Details eines Abonnements an.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'abo_id': {'type': 'integer', 'description': 'ID des Abonnements'}
            },
            'required': ['abo_id']
        }
    },
    {
        'name': 'abo_pausieren',
        'description': 'Pausiert ein aktives Abonnement.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'abo_id': {'type': 'integer', 'description': 'ID des Abonnements'},
                'bis_datum': {'type': 'string', 'description': 'Pause bis Datum (YYYY-MM-DD), optional'}
            },
            'required': ['abo_id']
        }
    },
    {
        'name': 'abo_kuendigen',
        'description': 'Kuendigt ein aktives oder pausiertes Abonnement.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'abo_id': {'type': 'integer', 'description': 'ID des Abonnements'}
            },
            'required': ['abo_id']
        }
    },
    {
        'name': 'checkin',
        'description': 'Fuehrt einen Check-in fuer einen Patienten durch (Badge-Nummer oder Name).',
        'input_schema': {
            'type': 'object',
            'properties': {
                'badge_oder_name': {'type': 'string', 'description': 'Badge-Nummer oder Patientenname'}
            },
            'required': ['badge_oder_name']
        }
    },
    {
        'name': 'besuche_heute',
        'description': 'Zeigt alle heutigen Fitness-Besuche an.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'standort_id': {'type': 'integer', 'description': 'Standort-ID (optional, 0 = alle)'}
            },
            'required': []
        }
    },
    {
        'name': 'ablaufende_abos',
        'description': 'Listet Abos auf, die in den naechsten X Tagen ablaufen.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'tage': {'type': 'integer', 'description': 'Anzahl Tage voraus (Standard: 30)'}
            },
            'required': []
        }
    },
    {
        'name': 'fitness_umsatz',
        'description': 'Berechnet den Fitness-Umsatz fuer einen bestimmten Monat.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'monat': {'type': 'integer', 'description': 'Monat (1-12)'},
                'jahr': {'type': 'integer', 'description': 'Jahr (z.B. 2026)'}
            },
            'required': ['monat', 'jahr']
        }
    }
]


def fitness_tool_executor(tool_name, tool_input):
    """Fuehrt Fitness-Tools aus"""
    from flask_login import current_user
    org_id = current_user.organization_id

    if tool_name == 'abo_suchen':
        name = tool_input.get('patient_name', '')
        patients = Patient.query.filter(
            Patient.organization_id == org_id,
            or_(
                Patient.first_name.ilike(f'%{name}%'),
                Patient.last_name.ilike(f'%{name}%')
            )
        ).all()

        ergebnisse = []
        for p in patients:
            abos = Subscription.query.filter_by(
                organization_id=org_id, patient_id=p.id
            ).all()
            for abo in abos:
                ergebnisse.append({
                    'abo_id': abo.id,
                    'abo_nummer': abo.subscription_number,
                    'patient': f'{p.first_name} {p.last_name}',
                    'typ': abo.template.name if abo.template else 'Unbekannt',
                    'status': abo.status,
                    'gueltig_bis': abo.end_date.strftime('%d.%m.%Y') if abo.end_date else 'Unbegrenzt',
                    'besuche': abo.visits_used or 0
                })

        if not ergebnisse:
            return {'message': f'Kein Abo fuer "{name}" gefunden.'}
        return {'abos': ergebnisse}

    elif tool_name == 'abo_erstellen':
        patient_id = tool_input.get('patient_id')
        vorlage_id = tool_input.get('vorlage_id')
        startdatum_str = tool_input.get('startdatum', '')

        patient = Patient.query.get(patient_id)
        vorlage = SubscriptionTemplate.query.get(vorlage_id)

        if not patient or patient.organization_id != org_id:
            return {'error': 'Patient nicht gefunden.'}
        if not vorlage or vorlage.organization_id != org_id:
            return {'error': 'Abo-Vorlage nicht gefunden.'}

        start = date.today()
        if startdatum_str:
            try:
                start = datetime.strptime(startdatum_str, '%Y-%m-%d').date()
            except ValueError:
                return {'error': 'Ungueltiges Datumsformat. Bitte YYYY-MM-DD verwenden.'}

        end = None
        if vorlage.duration_months > 0:
            import calendar
            month = start.month - 1 + vorlage.duration_months
            year = start.year + month // 12
            month = month % 12 + 1
            day = min(start.day, calendar.monthrange(year, month)[1])
            end = date(year, month, day)

        count = Subscription.query.filter_by(organization_id=org_id).count()
        abo_nummer = f'ABO-{count + 1:05d}'

        abo = Subscription(
            organization_id=org_id,
            patient_id=patient_id,
            template_id=vorlage_id,
            subscription_number=abo_nummer,
            start_date=start,
            end_date=end,
            status='active',
            visits_used=0
        )
        db.session.add(abo)
        db.session.commit()

        return {
            'success': True,
            'abo_id': abo.id,
            'abo_nummer': abo_nummer,
            'patient': f'{patient.first_name} {patient.last_name}',
            'vorlage': vorlage.name,
            'start': start.strftime('%d.%m.%Y'),
            'ende': end.strftime('%d.%m.%Y') if end else 'Unbegrenzt',
            'preis': f'CHF {vorlage.price:.2f}'
        }

    elif tool_name == 'abo_status':
        abo_id = tool_input.get('abo_id')
        abo = Subscription.query.get(abo_id)
        if not abo or abo.organization_id != org_id:
            return {'error': 'Abo nicht gefunden.'}

        vorlage = abo.template
        patient = abo.patient
        rest_besuche = None
        if vorlage and vorlage.max_visits > 0:
            rest_besuche = vorlage.max_visits - (abo.visits_used or 0)

        return {
            'abo_id': abo.id,
            'abo_nummer': abo.subscription_number,
            'patient': f'{patient.first_name} {patient.last_name}',
            'typ': vorlage.name if vorlage else 'Unbekannt',
            'status': abo.status,
            'start': abo.start_date.strftime('%d.%m.%Y'),
            'ende': abo.end_date.strftime('%d.%m.%Y') if abo.end_date else 'Unbegrenzt',
            'besuche_genutzt': abo.visits_used or 0,
            'rest_besuche': rest_besuche,
            'badge': abo.badge_number or 'Nicht zugewiesen',
            'pausiert_von': abo.paused_from.strftime('%d.%m.%Y') if abo.paused_from else None,
            'pausiert_bis': abo.paused_until.strftime('%d.%m.%Y') if abo.paused_until else None
        }

    elif tool_name == 'abo_pausieren':
        abo_id = tool_input.get('abo_id')
        bis_datum_str = tool_input.get('bis_datum', '')

        abo = Subscription.query.get(abo_id)
        if not abo or abo.organization_id != org_id:
            return {'error': 'Abo nicht gefunden.'}
        if abo.status != 'active':
            return {'error': f'Abo kann nicht pausiert werden (Status: {abo.status}).'}

        abo.status = 'paused'
        abo.paused_from = date.today()
        if bis_datum_str:
            try:
                abo.paused_until = datetime.strptime(bis_datum_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        db.session.commit()

        return {
            'success': True,
            'message': f'Abo {abo.subscription_number} pausiert.',
            'pausiert_ab': date.today().strftime('%d.%m.%Y'),
            'pausiert_bis': abo.paused_until.strftime('%d.%m.%Y') if abo.paused_until else 'Bis auf Weiteres'
        }

    elif tool_name == 'abo_kuendigen':
        abo_id = tool_input.get('abo_id')
        abo = Subscription.query.get(abo_id)
        if not abo or abo.organization_id != org_id:
            return {'error': 'Abo nicht gefunden.'}
        if abo.status not in ('active', 'paused'):
            return {'error': f'Abo kann nicht gekuendigt werden (Status: {abo.status}).'}

        abo.status = 'cancelled'
        db.session.commit()

        return {
            'success': True,
            'message': f'Abo {abo.subscription_number} wurde gekuendigt.'
        }

    elif tool_name == 'checkin':
        eingabe = tool_input.get('badge_oder_name', '').strip()
        if not eingabe:
            return {'error': 'Bitte Badge-Nummer oder Name angeben.'}

        # Per Badge suchen
        abo = Subscription.query.filter(
            Subscription.organization_id == org_id,
            Subscription.badge_number == eingabe,
            Subscription.status == 'active'
        ).first()

        if not abo:
            patient = Patient.query.filter(
                Patient.organization_id == org_id,
                or_(
                    Patient.last_name.ilike(f'%{eingabe}%'),
                    Patient.first_name.ilike(f'%{eingabe}%')
                )
            ).first()
            if patient:
                abo = Subscription.query.filter(
                    Subscription.organization_id == org_id,
                    Subscription.patient_id == patient.id,
                    Subscription.status == 'active'
                ).first()

        if not abo:
            return {'error': 'Kein gueltiges Abo gefunden.'}

        vorlage = abo.template
        if abo.end_date and abo.end_date < date.today():
            return {'error': f'Abo abgelaufen am {abo.end_date.strftime("%d.%m.%Y")}.'}

        if vorlage and vorlage.max_visits > 0 and abo.visits_used >= vorlage.max_visits:
            return {'error': f'Alle {vorlage.max_visits} Besuche aufgebraucht.'}

        besuch = FitnessVisit(
            subscription_id=abo.id,
            patient_id=abo.patient_id,
            check_in=datetime.now()
        )
        db.session.add(besuch)
        abo.visits_used = (abo.visits_used or 0) + 1
        db.session.commit()

        patient = abo.patient
        result = {
            'success': True,
            'message': f'Check-in erfolgreich: {patient.first_name} {patient.last_name}',
            'zeit': datetime.now().strftime('%H:%M'),
            'abo': vorlage.name if vorlage else 'Unbekannt'
        }
        if vorlage and vorlage.max_visits > 0:
            result['rest_besuche'] = vorlage.max_visits - abo.visits_used
        return result

    elif tool_name == 'besuche_heute':
        standort_id = tool_input.get('standort_id', 0)
        today = date.today()

        query = FitnessVisit.query.join(Subscription).filter(
            Subscription.organization_id == org_id,
            func.date(FitnessVisit.check_in) == today
        )
        if standort_id:
            query = query.filter(FitnessVisit.location_id == standort_id)

        besuche = query.order_by(FitnessVisit.check_in.desc()).all()

        return {
            'datum': today.strftime('%d.%m.%Y'),
            'anzahl': len(besuche),
            'besuche': [{
                'patient': f'{b.patient.first_name} {b.patient.last_name}',
                'check_in': b.check_in.strftime('%H:%M'),
                'check_out': b.check_out.strftime('%H:%M') if b.check_out else 'Noch da',
                'abo': b.subscription.template.name if b.subscription.template else ''
            } for b in besuche]
        }

    elif tool_name == 'ablaufende_abos':
        tage = tool_input.get('tage', 30)
        today = date.today()
        bis = today + timedelta(days=tage)

        abos = Subscription.query.filter(
            Subscription.organization_id == org_id,
            Subscription.status == 'active',
            Subscription.end_date != None,
            Subscription.end_date >= today,
            Subscription.end_date <= bis
        ).order_by(Subscription.end_date).all()

        return {
            'zeitraum': f'{today.strftime("%d.%m.%Y")} bis {bis.strftime("%d.%m.%Y")}',
            'anzahl': len(abos),
            'abos': [{
                'abo_id': a.id,
                'abo_nummer': a.subscription_number,
                'patient': f'{a.patient.first_name} {a.patient.last_name}',
                'typ': a.template.name if a.template else '',
                'ablaufdatum': a.end_date.strftime('%d.%m.%Y'),
                'auto_verlaengerung': a.template.auto_renew if a.template else False
            } for a in abos]
        }

    elif tool_name == 'fitness_umsatz':
        monat = tool_input.get('monat')
        jahr = tool_input.get('jahr')

        start = date(jahr, monat, 1)
        if monat == 12:
            end = date(jahr + 1, 1, 1) - timedelta(days=1)
        else:
            end = date(jahr, monat + 1, 1) - timedelta(days=1)

        umsatz = db.session.query(func.sum(Invoice.amount_total)).filter(
            Invoice.organization_id == org_id,
            Invoice.category == 'fitness',
            Invoice.created_at >= datetime.combine(start, datetime.min.time()),
            Invoice.created_at <= datetime.combine(end, datetime.max.time())
        ).scalar() or 0

        bezahlt = db.session.query(func.sum(Invoice.amount_paid)).filter(
            Invoice.organization_id == org_id,
            Invoice.category == 'fitness',
            Invoice.created_at >= datetime.combine(start, datetime.min.time()),
            Invoice.created_at <= datetime.combine(end, datetime.max.time())
        ).scalar() or 0

        anzahl = Invoice.query.filter(
            Invoice.organization_id == org_id,
            Invoice.category == 'fitness',
            Invoice.created_at >= datetime.combine(start, datetime.min.time()),
            Invoice.created_at <= datetime.combine(end, datetime.max.time())
        ).count()

        return {
            'monat': f'{monat:02d}/{jahr}',
            'umsatz_total': f'CHF {umsatz:.2f}',
            'bezahlt': f'CHF {bezahlt:.2f}',
            'offen': f'CHF {(umsatz - bezahlt):.2f}',
            'anzahl_rechnungen': anzahl
        }

    return {'error': f'Unbekanntes Tool: {tool_name}'}
