"""KI-Tools fuer den Ressourcen-Bereich"""
from datetime import datetime, timedelta, date, time
from flask_login import current_user
from models import db, Resource, ResourceBooking, MaintenanceRecord, Appointment, Location


RESOURCE_TOOLS = [
    {
        'name': 'ressource_suchen',
        'description': 'Sucht Ressourcen (Raeume, Geraete) nach Name oder Typ.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'name_oder_typ': {
                    'type': 'string',
                    'description': 'Suchbegriff (Name der Ressource oder Typ wie "room", "device", "Behandlungsraum")'
                }
            },
            'required': ['name_oder_typ']
        }
    },
    {
        'name': 'ressource_verfuegbarkeit',
        'description': 'Prueft ob eine bestimmte Ressource an einem Tag frei ist und zeigt die Belegung.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'ressource_id': {
                    'type': 'integer',
                    'description': 'ID der Ressource'
                },
                'datum': {
                    'type': 'string',
                    'description': 'Datum (TT.MM.JJJJ) oder "heute", "morgen"'
                }
            },
            'required': ['ressource_id', 'datum']
        }
    },
    {
        'name': 'freie_raeume',
        'description': 'Findet freie Raeume an einem bestimmten Standort zu einer bestimmten Zeit.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'standort_id': {
                    'type': 'integer',
                    'description': 'ID des Standorts'
                },
                'datum': {
                    'type': 'string',
                    'description': 'Datum (TT.MM.JJJJ) oder "heute", "morgen"'
                },
                'uhrzeit': {
                    'type': 'string',
                    'description': 'Uhrzeit (HH:MM)'
                },
                'dauer_minuten': {
                    'type': 'integer',
                    'description': 'Gewuenschte Dauer in Minuten (Standard: 30)'
                }
            },
            'required': ['standort_id', 'datum', 'uhrzeit']
        }
    },
    {
        'name': 'wartung_faellig',
        'description': 'Listet alle Geraete auf, bei denen eine Wartung faellig oder ueberfaellig ist.',
        'input_schema': {
            'type': 'object',
            'properties': {},
            'required': []
        }
    }
]


def _parse_datum(datum_str):
    """Hilfsfunktion: Parst ein Datum aus verschiedenen Formaten"""
    datum_str = datum_str.strip().lower()
    now = datetime.now()

    if datum_str == 'heute':
        return now.date()
    elif datum_str == 'morgen':
        return (now + timedelta(days=1)).date()
    else:
        try:
            return datetime.strptime(datum_str, '%d.%m.%Y').date()
        except ValueError:
            return None


def resource_tool_executor(tool_name, tool_input):
    """Fuehrt die Ressourcen-Tools aus"""
    org_id = current_user.organization_id

    if tool_name == 'ressource_suchen':
        suchbegriff = tool_input['name_oder_typ'].strip()
        ressourcen = Resource.query.filter(
            Resource.organization_id == org_id,
            db.or_(
                Resource.name.ilike(f'%{suchbegriff}%'),
                Resource.resource_type.ilike(f'%{suchbegriff}%')
            ),
            Resource.is_active == True
        ).limit(20).all()

        if not ressourcen:
            return {'ergebnis': 'Keine Ressourcen gefunden.', 'anzahl': 0}

        ergebnisse = []
        for r in ressourcen:
            ergebnisse.append({
                'id': r.id,
                'name': r.name,
                'typ': r.resource_type,
                'standort': r.location.name if r.location else '-',
                'kapazitaet': r.capacity,
                'beschreibung': r.description or '-'
            })

        return {'ergebnis': ergebnisse, 'anzahl': len(ergebnisse)}

    elif tool_name == 'ressource_verfuegbarkeit':
        ressource = Resource.query.get(tool_input['ressource_id'])
        if not ressource or ressource.organization_id != org_id:
            return {'error': 'Ressource nicht gefunden.'}

        tag = _parse_datum(tool_input['datum'])
        if not tag:
            return {'error': 'Ungueltiges Datum. Verwende TT.MM.JJJJ, "heute" oder "morgen".'}

        start_dt = datetime.combine(tag, time(0, 0))
        end_dt = datetime.combine(tag, time(23, 59))

        # Termine mit dieser Ressource laden
        termine = Appointment.query.filter(
            Appointment.resource_id == ressource.id,
            Appointment.start_time >= start_dt,
            Appointment.end_time <= end_dt,
            Appointment.status.in_(['scheduled', 'confirmed'])
        ).order_by(Appointment.start_time).all()

        belegungen = []
        for t in termine:
            belegungen.append({
                'zeit': f'{t.start_time.strftime("%H:%M")} - {t.end_time.strftime("%H:%M")}',
                'patient': f'{t.patient.first_name} {t.patient.last_name}' if t.patient else '-',
                'therapeut': f'{t.employee.user.first_name} {t.employee.user.last_name}' if t.employee and t.employee.user else '-',
                'titel': t.title or t.appointment_type
            })

        return {
            'ergebnis': {
                'ressource': ressource.name,
                'datum': tag.strftime('%d.%m.%Y'),
                'anzahl_termine': len(belegungen),
                'belegungen': belegungen,
                'zusammenfassung': f'{ressource.name} hat am {tag.strftime("%d.%m.%Y")} {len(belegungen)} Belegung(en).' if belegungen else f'{ressource.name} ist am {tag.strftime("%d.%m.%Y")} frei.'
            }
        }

    elif tool_name == 'freie_raeume':
        standort = Location.query.get(tool_input['standort_id'])
        if not standort or standort.organization_id != org_id:
            return {'error': 'Standort nicht gefunden.'}

        tag = _parse_datum(tool_input['datum'])
        if not tag:
            return {'error': 'Ungueltiges Datum. Verwende TT.MM.JJJJ, "heute" oder "morgen".'}

        try:
            uhrzeit = datetime.strptime(tool_input['uhrzeit'], '%H:%M').time()
        except ValueError:
            return {'error': 'Ungueltige Uhrzeit. Verwende Format HH:MM.'}

        dauer = tool_input.get('dauer_minuten', 30)
        start_dt = datetime.combine(tag, uhrzeit)
        end_dt = start_dt + timedelta(minutes=dauer)

        # Alle Raeume am Standort
        raeume = Resource.query.filter(
            Resource.location_id == standort.id,
            Resource.resource_type.in_(['room', 'Behandlungsraum', 'Trainingsraum', 'Gruppenraum']),
            Resource.is_active == True
        ).all()

        freie = []
        for raum in raeume:
            # Pruefen ob Kollision
            kollision = Appointment.query.filter(
                Appointment.resource_id == raum.id,
                Appointment.start_time < end_dt,
                Appointment.end_time > start_dt,
                Appointment.status.in_(['scheduled', 'confirmed'])
            ).first()

            if not kollision:
                freie.append({
                    'id': raum.id,
                    'name': raum.name,
                    'kapazitaet': raum.capacity,
                    'beschreibung': raum.description or '-'
                })

        if not freie:
            return {
                'ergebnis': f'Keine freien Raeume am {standort.name} fuer {tag.strftime("%d.%m.%Y")} {tool_input["uhrzeit"]} ({dauer} Min.) gefunden.',
                'anzahl': 0
            }

        return {
            'ergebnis': freie,
            'anzahl': len(freie),
            'zusammenfassung': f'{len(freie)} freie(r) Raum/Raeume am {standort.name} fuer {tag.strftime("%d.%m.%Y")} {tool_input["uhrzeit"]} ({dauer} Min.).'
        }

    elif tool_name == 'wartung_faellig':
        heute = date.today()

        # Alle Geraete mit Wartungseintraegen laden
        geraete = Resource.query.filter(
            Resource.organization_id == org_id,
            Resource.resource_type.in_(['device', 'Geraet', 'Fahrzeug']),
            Resource.is_active == True
        ).all()

        faellige = []
        for geraet in geraete:
            letzte_wartung = MaintenanceRecord.query.filter_by(
                resource_id=geraet.id
            ).order_by(MaintenanceRecord.performed_at.desc()).first()

            if letzte_wartung and letzte_wartung.next_due:
                if letzte_wartung.next_due <= heute:
                    tage_ueberfaellig = (heute - letzte_wartung.next_due).days
                    faellige.append({
                        'id': geraet.id,
                        'name': geraet.name,
                        'standort': geraet.location.name if geraet.location else '-',
                        'letzte_wartung': letzte_wartung.performed_at.strftime('%d.%m.%Y'),
                        'faellig_seit': letzte_wartung.next_due.strftime('%d.%m.%Y'),
                        'tage_ueberfaellig': tage_ueberfaellig,
                        'status': 'UEBERFAELLIG' if tage_ueberfaellig > 0 else 'Heute faellig'
                    })

        if not faellige:
            return {'ergebnis': 'Keine Geraete mit faelliger Wartung gefunden.', 'anzahl': 0}

        return {
            'ergebnis': faellige,
            'anzahl': len(faellige),
            'zusammenfassung': f'{len(faellige)} Geraet(e) mit faelliger oder ueberfaelliger Wartung.'
        }

    return {'error': f'Unbekanntes Tool: {tool_name}'}
