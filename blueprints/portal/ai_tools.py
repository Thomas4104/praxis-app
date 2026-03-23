"""
KI-Tools fuer das Patientenportal
"""
from datetime import datetime
from flask_login import current_user
from models import db, Patient, PortalAccount, PortalMessage, OnlineBookingRequest, Task


PORTAL_TOOLS = [
    {
        'name': 'portal_aktivieren',
        'description': 'Portal-Zugang fuer einen Patienten aktivieren oder deaktivieren',
        'input_schema': {
            'type': 'object',
            'properties': {
                'patient_id': {
                    'type': 'integer',
                    'description': 'ID des Patienten'
                },
                'aktivieren': {
                    'type': 'boolean',
                    'description': 'True = aktivieren, False = deaktivieren'
                }
            },
            'required': ['patient_id']
        }
    },
    {
        'name': 'portal_buchungen_auflisten',
        'description': 'Online-Buchungsanfragen aus dem Patientenportal auflisten',
        'input_schema': {
            'type': 'object',
            'properties': {
                'status': {
                    'type': 'string',
                    'description': 'Filterstatus: pending, confirmed, rejected oder alle',
                    'enum': ['pending', 'confirmed', 'rejected', 'alle']
                }
            },
            'required': []
        }
    },
    {
        'name': 'portal_buchung_bestaetigen',
        'description': 'Eine Online-Buchungsanfrage bestätigen',
        'input_schema': {
            'type': 'object',
            'properties': {
                'request_id': {
                    'type': 'integer',
                    'description': 'ID der Buchungsanfrage'
                }
            },
            'required': ['request_id']
        }
    },
    {
        'name': 'portal_nachricht_senden',
        'description': 'Eine Nachricht an einen Patienten über das Portal senden',
        'input_schema': {
            'type': 'object',
            'properties': {
                'patient_id': {
                    'type': 'integer',
                    'description': 'ID des Patienten'
                },
                'betreff': {
                    'type': 'string',
                    'description': 'Betreff der Nachricht'
                },
                'text': {
                    'type': 'string',
                    'description': 'Nachrichtentext'
                }
            },
            'required': ['patient_id', 'betreff', 'text']
        }
    },
    {
        'name': 'portal_statistik',
        'description': 'Statistiken zum Patientenportal abrufen: Konten, Buchungen, Nachrichten',
        'input_schema': {
            'type': 'object',
            'properties': {},
            'required': []
        }
    }
]


def portal_tool_executor(tool_name, tool_input):
    """Fuehrt Portal-KI-Tools aus"""
    org_id = current_user.organization_id

    if tool_name == 'portal_aktivieren':
        patient_id = tool_input['patient_id']
        aktivieren = tool_input.get('aktivieren', True)

        patient = Patient.query.get(patient_id)
        if not patient or patient.organization_id != org_id:
            return {'error': f'Patient mit ID {patient_id} nicht gefunden'}

        account = PortalAccount.query.filter_by(patient_id=patient_id).first()
        if not account:
            if not aktivieren:
                return {'error': 'Patient hat keinen Portal-Zugang'}
            # Neuen Account erstellen
            account = PortalAccount(
                patient_id=patient_id,
                email=patient.email or f'patient{patient_id}@portal.local',
                is_active=True,
                is_verified=True
            )
            account.set_password('portal123')  # Temporaeres Passwort
            db.session.add(account)
            db.session.commit()
            return {
                'success': True,
                'message': f'Portal-Zugang für {patient.first_name} {patient.last_name} erstellt und aktiviert. '
                           f'Temporäres Passwort: portal123'
            }

        account.is_active = aktivieren
        if aktivieren:
            account.is_verified = True
        db.session.commit()

        status = 'aktiviert' if aktivieren else 'deaktiviert'
        return {
            'success': True,
            'message': f'Portal-Zugang für {patient.first_name} {patient.last_name} wurde {status}.'
        }

    elif tool_name == 'portal_buchungen_auflisten':
        status_filter = tool_input.get('status', 'alle')

        query = OnlineBookingRequest.query.join(Patient).filter(Patient.organization_id == org_id)
        if status_filter and status_filter != 'alle':
            query = query.filter(OnlineBookingRequest.status == status_filter)

        bookings = query.order_by(OnlineBookingRequest.created_at.desc()).limit(20).all()

        result = []
        for b in bookings:
            patient = Patient.query.get(b.patient_id)
            result.append({
                'id': b.id,
                'patient': f'{patient.first_name} {patient.last_name}' if patient else 'Unbekannt',
                'behandlung': b.template.name if b.template else 'Unbekannt',
                'datum': b.requested_date.strftime('%d.%m.%Y'),
                'zeit': b.requested_time.strftime('%H:%M'),
                'status': b.status,
                'erstellt': b.created_at.strftime('%d.%m.%Y %H:%M')
            })

        return {
            'buchungen': result,
            'anzahl': len(result)
        }

    elif tool_name == 'portal_buchung_bestaetigen':
        request_id = tool_input['request_id']
        booking = OnlineBookingRequest.query.get(request_id)
        if not booking:
            return {'error': f'Buchungsanfrage mit ID {request_id} nicht gefunden'}

        # Org-Zugehoerigkeit ueber Patient pruefen
        patient_check = Patient.query.get(booking.patient_id)
        if not patient_check or patient_check.organization_id != org_id:
            return {'error': f'Buchungsanfrage mit ID {request_id} nicht gefunden'}

        booking.status = 'confirmed'
        db.session.commit()

        patient = Patient.query.get(booking.patient_id)
        return {
            'success': True,
            'message': f'Buchungsanfrage von {patient.first_name} {patient.last_name} '
                       f'am {booking.requested_date.strftime("%d.%m.%Y")} wurde bestätigt.'
        }

    elif tool_name == 'portal_nachricht_senden':
        patient_id = tool_input['patient_id']
        betreff = tool_input['betreff']
        text = tool_input['text']

        patient = Patient.query.get(patient_id)
        if not patient or patient.organization_id != org_id:
            return {'error': f'Patient mit ID {patient_id} nicht gefunden'}

        account = PortalAccount.query.filter_by(patient_id=patient_id).first()
        if not account or not account.is_active:
            return {'error': f'Patient {patient.first_name} {patient.last_name} hat keinen aktiven Portal-Zugang'}

        msg = PortalMessage(
            patient_id=patient_id,
            sender_type='practice',
            sender_name='OMNIA Praxisteam',
            subject=betreff,
            body=text
        )
        db.session.add(msg)
        db.session.commit()

        return {
            'success': True,
            'message': f'Nachricht "{betreff}" an {patient.first_name} {patient.last_name} gesendet.'
        }

    elif tool_name == 'portal_statistik':
        # Alle Abfragen auf Patienten der eigenen Organisation einschraenken
        total_accounts = PortalAccount.query.join(Patient).filter(Patient.organization_id == org_id).count()
        active_accounts = PortalAccount.query.join(Patient).filter(
            Patient.organization_id == org_id, PortalAccount.is_active == True
        ).count()
        pending_bookings = OnlineBookingRequest.query.join(Patient).filter(
            Patient.organization_id == org_id, OnlineBookingRequest.status == 'pending'
        ).count()
        total_bookings = OnlineBookingRequest.query.join(Patient).filter(Patient.organization_id == org_id).count()
        total_messages = PortalMessage.query.join(Patient).filter(Patient.organization_id == org_id).count()
        patient_messages = PortalMessage.query.join(Patient).filter(
            Patient.organization_id == org_id, PortalMessage.sender_type == 'patient'
        ).count()
        unread_messages = PortalMessage.query.join(Patient).filter(
            Patient.organization_id == org_id, PortalMessage.sender_type == 'patient'
        ).filter(PortalMessage.read_at.is_(None)).count()

        return {
            'portal_konten_gesamt': total_accounts,
            'portal_konten_aktiv': active_accounts,
            'portal_konten_ausstehend': total_accounts - active_accounts,
            'buchungsanfragen_gesamt': total_bookings,
            'buchungsanfragen_offen': pending_bookings,
            'nachrichten_gesamt': total_messages,
            'nachrichten_von_patienten': patient_messages,
            'nachrichten_ungelesen': unread_messages
        }

    return {'error': f'Unbekanntes Tool: {tool_name}'}
