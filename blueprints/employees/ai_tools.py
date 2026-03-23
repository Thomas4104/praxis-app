"""KI-Tools fuer den Mitarbeiter-Bereich"""
import json
from datetime import datetime, date, timedelta
from flask_login import current_user
from models import db, Employee, User, WorkSchedule, Absence, AbsenceQuota, Certificate, Location


EMPLOYEE_TOOLS = [
    {
        'name': 'mitarbeiter_suchen',
        'description': 'Sucht Mitarbeiter nach Name (Vor- oder Nachname).',
        'input_schema': {
            'type': 'object',
            'properties': {
                'name': {
                    'type': 'string',
                    'description': 'Suchbegriff (Teil des Vor- oder Nachnamens)'
                }
            },
            'required': ['name']
        }
    },
    {
        'name': 'mitarbeiter_details',
        'description': 'Zeigt alle Details eines Mitarbeiters (Basisdaten, Rolle, Standort, Pensum, Qualifikationen).',
        'input_schema': {
            'type': 'object',
            'properties': {
                'employee_id': {
                    'type': 'integer',
                    'description': 'ID des Mitarbeiters'
                }
            },
            'required': ['employee_id']
        }
    },
    {
        'name': 'mitarbeiter_auflisten',
        'description': 'Listet alle Mitarbeiter auf, optional gefiltert nach Standort oder Rolle.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'standort_id': {
                    'type': 'integer',
                    'description': 'Standort-ID zum Filtern (optional)'
                },
                'rolle': {
                    'type': 'string',
                    'description': 'Rolle zum Filtern: admin, therapist, reception (optional)'
                }
            },
            'required': []
        }
    },
    {
        'name': 'arbeitszeiten_anzeigen',
        'description': 'Zeigt die Arbeitszeiten eines Mitarbeiters an einem bestimmten Tag oder die gesamte Woche.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'employee_id': {
                    'type': 'integer',
                    'description': 'ID des Mitarbeiters'
                },
                'datum': {
                    'type': 'string',
                    'description': 'Datum im Format YYYY-MM-DD (optional, leer = ganze Woche)'
                }
            },
            'required': ['employee_id']
        }
    },
    {
        'name': 'verfuegbarkeit_pruefen',
        'description': 'Prueft, ob ein Mitarbeiter an einem bestimmten Datum und Uhrzeit verfuegbar ist.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'employee_id': {
                    'type': 'integer',
                    'description': 'ID des Mitarbeiters'
                },
                'datum': {
                    'type': 'string',
                    'description': 'Datum im Format YYYY-MM-DD'
                },
                'uhrzeit': {
                    'type': 'string',
                    'description': 'Uhrzeit im Format HH:MM'
                }
            },
            'required': ['employee_id', 'datum', 'uhrzeit']
        }
    },
    {
        'name': 'absenzen_anzeigen',
        'description': 'Zeigt die Absenzen eines Mitarbeiters, optional gefiltert nach Monat.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'employee_id': {
                    'type': 'integer',
                    'description': 'ID des Mitarbeiters'
                },
                'monat': {
                    'type': 'integer',
                    'description': 'Monat (1-12, optional)'
                },
                'jahr': {
                    'type': 'integer',
                    'description': 'Jahr (optional, Standard: aktuelles Jahr)'
                }
            },
            'required': ['employee_id']
        }
    },
    {
        'name': 'absenz_erstellen',
        'description': 'Erstellt eine neue Absenz fuer einen Mitarbeiter.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'employee_id': {
                    'type': 'integer',
                    'description': 'ID des Mitarbeiters'
                },
                'typ': {
                    'type': 'string',
                    'description': 'Absenztyp: vacation, sick, accident, training, military, maternity, paternity, unpaid, other'
                },
                'von_datum': {
                    'type': 'string',
                    'description': 'Startdatum im Format YYYY-MM-DD'
                },
                'bis_datum': {
                    'type': 'string',
                    'description': 'Enddatum im Format YYYY-MM-DD'
                }
            },
            'required': ['employee_id', 'typ', 'von_datum', 'bis_datum']
        }
    },
    {
        'name': 'ferientage_rest',
        'description': 'Zeigt die verbleibenden Ferientage eines Mitarbeiters im aktuellen Jahr.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'employee_id': {
                    'type': 'integer',
                    'description': 'ID des Mitarbeiters'
                }
            },
            'required': ['employee_id']
        }
    },
    {
        'name': 'wer_arbeitet_heute',
        'description': 'Zeigt, welche Mitarbeiter heute an einem bestimmten Standort arbeiten.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'standort_id': {
                    'type': 'integer',
                    'description': 'Standort-ID (optional, leer = alle Standorte)'
                }
            },
            'required': []
        }
    },
    {
        'name': 'wer_ist_abwesend',
        'description': 'Zeigt, wer an einem bestimmten Datum abwesend ist.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'datum': {
                    'type': 'string',
                    'description': 'Datum im Format YYYY-MM-DD (optional, Standard: heute)'
                }
            },
            'required': []
        }
    }
]


def employee_tool_executor(tool_name, tool_input):
    """Fuehrt die Mitarbeiter-Tools aus"""
    org_id = current_user.organization_id

    if tool_name == 'mitarbeiter_suchen':
        name = tool_input['name']
        employees = Employee.query.join(User).filter(
            Employee.organization_id == org_id,
            Employee.is_active == True,
            db.or_(
                User.first_name.ilike(f'%{name}%'),
                User.last_name.ilike(f'%{name}%')
            )
        ).all()

        if not employees:
            return {'ergebnis': f'Kein Mitarbeiter mit dem Namen "{name}" gefunden.', 'anzahl': 0}

        ergebnisse = []
        for emp in employees:
            ergebnisse.append({
                'id': emp.id,
                'name': f'{emp.user.first_name} {emp.user.last_name}',
                'rolle': emp.user.role,
                'standort': emp.default_location.name if emp.default_location else '-',
                'pensum': f'{emp.pensum_percent}%'
            })

        return {'ergebnis': ergebnisse, 'anzahl': len(ergebnisse)}

    elif tool_name == 'mitarbeiter_details':
        emp = Employee.query.get(tool_input['employee_id'])
        if not emp or emp.organization_id != org_id:
            return {'error': 'Mitarbeiter nicht gefunden.'}

        quals = []
        if emp.qualifications_json:
            try:
                quals = json.loads(emp.qualifications_json)
            except (json.JSONDecodeError, TypeError):
                pass

        specs = []
        if emp.specializations_json:
            try:
                specs = json.loads(emp.specializations_json)
            except (json.JSONDecodeError, TypeError):
                pass

        return {
            'ergebnis': {
                'id': emp.id,
                'name': f'{emp.user.first_name} {emp.user.last_name}',
                'mitarbeiternummer': emp.employee_number,
                'email': emp.user.email or '-',
                'rolle': emp.user.role,
                'standort': emp.default_location.name if emp.default_location else '-',
                'pensum': f'{emp.pensum_percent}%',
                'anstellungsmodell': emp.employment_model or 'Festanstellung',
                'zsr_nummer': emp.zsr_number or '-',
                'gln_nummer': emp.gln_number or '-',
                'qualifikationen': quals,
                'spezialisierungen': specs,
                'aktiv': emp.is_active
            }
        }

    elif tool_name == 'mitarbeiter_auflisten':
        query = Employee.query.filter_by(organization_id=org_id, is_active=True)

        standort_id = tool_input.get('standort_id')
        if standort_id:
            query = query.filter_by(default_location_id=standort_id)

        employees = query.all()

        rolle = tool_input.get('rolle')
        if rolle:
            employees = [e for e in employees if e.user and e.user.role == rolle]

        ergebnisse = []
        for emp in employees:
            ergebnisse.append({
                'id': emp.id,
                'name': f'{emp.user.first_name} {emp.user.last_name}',
                'rolle': emp.user.role,
                'standort': emp.default_location.name if emp.default_location else '-',
                'pensum': f'{emp.pensum_percent}%'
            })

        return {'ergebnis': ergebnisse, 'anzahl': len(ergebnisse)}

    elif tool_name == 'arbeitszeiten_anzeigen':
        emp = Employee.query.get(tool_input['employee_id'])
        if not emp or emp.organization_id != org_id:
            return {'error': 'Mitarbeiter nicht gefunden.'}

        datum_str = tool_input.get('datum')
        if datum_str:
            try:
                d = datetime.strptime(datum_str, '%Y-%m-%d').date()
                schedules = WorkSchedule.query.filter_by(
                    employee_id=emp.id,
                    day_of_week=d.weekday()
                ).order_by(WorkSchedule.start_time).all()
            except ValueError:
                return {'error': 'Ungueliges Datumsformat. Bitte YYYY-MM-DD verwenden.'}
        else:
            schedules = WorkSchedule.query.filter_by(
                employee_id=emp.id
            ).order_by(WorkSchedule.day_of_week, WorkSchedule.start_time).all()

        tage = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag']
        typen = {
            'treatment': 'Behandlung', 'group_therapy': 'Gruppentherapie', 'mtt': 'MTT',
            'office': 'Buerozeit', 'break': 'Pause', 'overtime_buffer': 'Ueberzeitpuffer'
        }

        ergebnisse = []
        for ws in schedules:
            ergebnisse.append({
                'tag': tage[ws.day_of_week],
                'von': ws.start_time.strftime('%H:%M'),
                'bis': ws.end_time.strftime('%H:%M'),
                'art': typen.get(ws.work_type, ws.work_type),
                'standort': ws.location.name if ws.location else '-'
            })

        return {
            'ergebnis': ergebnisse,
            'mitarbeiter': f'{emp.user.first_name} {emp.user.last_name}',
            'anzahl_bloecke': len(ergebnisse)
        }

    elif tool_name == 'verfuegbarkeit_pruefen':
        emp = Employee.query.get(tool_input['employee_id'])
        if not emp or emp.organization_id != org_id:
            return {'error': 'Mitarbeiter nicht gefunden.'}

        try:
            d = datetime.strptime(tool_input['datum'], '%Y-%m-%d').date()
            t = datetime.strptime(tool_input['uhrzeit'], '%H:%M').time()
        except ValueError:
            return {'error': 'Ungueltiges Datums- oder Zeitformat.'}

        # Absenz pruefen
        absence = Absence.query.filter(
            Absence.employee_id == emp.id,
            Absence.start_date <= d,
            Absence.end_date >= d,
            Absence.status == 'approved'
        ).first()

        if absence:
            return {
                'ergebnis': {
                    'verfuegbar': False,
                    'grund': f'Abwesend ({absence.absence_type})',
                    'mitarbeiter': f'{emp.user.first_name} {emp.user.last_name}'
                }
            }

        # Arbeitszeit pruefen
        schedules = WorkSchedule.query.filter_by(
            employee_id=emp.id,
            day_of_week=d.weekday()
        ).all()

        is_working = any(ws.start_time <= t < ws.end_time for ws in schedules)

        if not is_working:
            return {
                'ergebnis': {
                    'verfuegbar': False,
                    'grund': 'Keine Arbeitszeit zu diesem Zeitpunkt',
                    'mitarbeiter': f'{emp.user.first_name} {emp.user.last_name}'
                }
            }

        # Termin pruefen
        from models import Appointment
        check_dt = datetime.combine(d, t)
        existing = Appointment.query.filter(
            Appointment.employee_id == emp.id,
            Appointment.start_time <= check_dt,
            Appointment.end_time > check_dt,
            Appointment.status != 'cancelled'
        ).first()

        if existing:
            return {
                'ergebnis': {
                    'verfuegbar': False,
                    'grund': f'Termin mit {existing.patient.first_name} {existing.patient.last_name}',
                    'mitarbeiter': f'{emp.user.first_name} {emp.user.last_name}'
                }
            }

        return {
            'ergebnis': {
                'verfuegbar': True,
                'mitarbeiter': f'{emp.user.first_name} {emp.user.last_name}'
            }
        }

    elif tool_name == 'absenzen_anzeigen':
        emp = Employee.query.get(tool_input['employee_id'])
        if not emp or emp.organization_id != org_id:
            return {'error': 'Mitarbeiter nicht gefunden.'}

        query = Absence.query.filter_by(employee_id=emp.id)

        monat = tool_input.get('monat')
        jahr = tool_input.get('jahr', date.today().year)
        if monat:
            import calendar
            _, days = calendar.monthrange(jahr, monat)
            start = date(jahr, monat, 1)
            end = date(jahr, monat, days)
            query = query.filter(Absence.start_date <= end, Absence.end_date >= start)

        absences = query.order_by(Absence.start_date.desc()).all()

        typen = {
            'vacation': 'Ferien', 'sick': 'Krankheit', 'accident': 'Unfall',
            'training': 'Weiterbildung', 'military': 'Militaer',
            'maternity': 'Mutterschaft', 'paternity': 'Vaterschaft',
            'unpaid': 'Unbezahlter Urlaub', 'other': 'Sonstiges'
        }

        ergebnisse = []
        for a in absences:
            ergebnisse.append({
                'typ': typen.get(a.absence_type, a.absence_type),
                'von': a.start_date.strftime('%d.%m.%Y'),
                'bis': a.end_date.strftime('%d.%m.%Y'),
                'halber_tag': a.half_day,
                'status': a.status,
                'bemerkung': a.notes or '-'
            })

        return {
            'ergebnis': ergebnisse,
            'mitarbeiter': f'{emp.user.first_name} {emp.user.last_name}',
            'anzahl': len(ergebnisse)
        }

    elif tool_name == 'absenz_erstellen':
        emp = Employee.query.get(tool_input['employee_id'])
        if not emp or emp.organization_id != org_id:
            return {'error': 'Mitarbeiter nicht gefunden.'}

        try:
            start = datetime.strptime(tool_input['von_datum'], '%Y-%m-%d').date()
            end = datetime.strptime(tool_input['bis_datum'], '%Y-%m-%d').date()
        except ValueError:
            return {'error': 'Ungueltiges Datumsformat. Bitte YYYY-MM-DD verwenden.'}

        if end < start:
            return {'error': 'Enddatum darf nicht vor dem Startdatum liegen.'}

        absence = Absence(
            employee_id=emp.id,
            absence_type=tool_input['typ'],
            start_date=start,
            end_date=end,
            status='approved'
        )
        db.session.add(absence)

        # Ferientage zaehlen und Kontingent aktualisieren
        if tool_input['typ'] == 'vacation':
            days = 0
            current = start
            while current <= end:
                if current.weekday() < 5:
                    days += 1
                current += timedelta(days=1)

            quota = AbsenceQuota.query.filter_by(
                employee_id=emp.id,
                year=start.year,
                absence_type='vacation'
            ).first()
            if quota:
                quota.used_days += days

        db.session.commit()

        return {
            'ergebnis': f'Absenz fuer {emp.user.first_name} {emp.user.last_name} wurde erstellt: '
                        f'{start.strftime("%d.%m.%Y")} bis {end.strftime("%d.%m.%Y")} ({tool_input["typ"]})'
        }

    elif tool_name == 'ferientage_rest':
        emp = Employee.query.get(tool_input['employee_id'])
        if not emp or emp.organization_id != org_id:
            return {'error': 'Mitarbeiter nicht gefunden.'}

        quota = AbsenceQuota.query.filter_by(
            employee_id=emp.id,
            year=date.today().year,
            absence_type='vacation'
        ).first()

        if not quota:
            return {'ergebnis': f'Kein Ferienkontingent fuer {date.today().year} gefunden.'}

        return {
            'ergebnis': {
                'mitarbeiter': f'{emp.user.first_name} {emp.user.last_name}',
                'jahr': quota.year,
                'anspruch': quota.total_days,
                'uebertrag': quota.carryover_days,
                'bezogen': quota.used_days,
                'verbleibend': quota.total_days + quota.carryover_days - quota.used_days
            }
        }

    elif tool_name == 'wer_arbeitet_heute':
        heute = date.today()
        standort_id = tool_input.get('standort_id')

        # Alle Mitarbeiter mit Arbeitszeit heute (nur eigene Organisation)
        query = WorkSchedule.query.join(Employee).filter(
            Employee.organization_id == org_id,
            WorkSchedule.day_of_week == heute.weekday()
        )
        if standort_id:
            query = query.filter_by(location_id=standort_id)
        schedules = query.all()

        # Mitarbeiter IDs sammeln (eindeutig)
        emp_ids = set(ws.employee_id for ws in schedules)

        # Abwesende filtern
        abwesende = Absence.query.filter(
            Absence.start_date <= heute,
            Absence.end_date >= heute,
            Absence.status == 'approved'
        ).all()
        abwesende_ids = {a.employee_id for a in abwesende}

        anwesende = []
        for emp_id in emp_ids:
            if emp_id in abwesende_ids:
                continue
            emp = Employee.query.get(emp_id)
            if emp and emp.is_active:
                emp_schedules = [ws for ws in schedules if ws.employee_id == emp_id]
                zeiten = ', '.join(f'{ws.start_time.strftime("%H:%M")}-{ws.end_time.strftime("%H:%M")}' for ws in emp_schedules)
                anwesende.append({
                    'name': f'{emp.user.first_name} {emp.user.last_name}',
                    'rolle': emp.user.role,
                    'zeiten': zeiten,
                    'standort': emp_schedules[0].location.name if emp_schedules[0].location else '-'
                })

        standort_name = ''
        if standort_id:
            loc = Location.query.get(standort_id)
            standort_name = loc.name if loc else ''

        return {
            'ergebnis': anwesende,
            'datum': heute.strftime('%d.%m.%Y'),
            'standort': standort_name or 'Alle Standorte',
            'anzahl': len(anwesende)
        }

    elif tool_name == 'wer_ist_abwesend':
        datum_str = tool_input.get('datum')
        if datum_str:
            try:
                d = datetime.strptime(datum_str, '%Y-%m-%d').date()
            except ValueError:
                return {'error': 'Ungueltiges Datumsformat.'}
        else:
            d = date.today()

        absences = Absence.query.join(Employee).filter(
            Employee.organization_id == org_id,
            Absence.start_date <= d,
            Absence.end_date >= d,
            Absence.status.in_(['approved', 'pending'])
        ).all()

        typen = {
            'vacation': 'Ferien', 'sick': 'Krankheit', 'accident': 'Unfall',
            'training': 'Weiterbildung', 'military': 'Militaer',
            'maternity': 'Mutterschaft', 'paternity': 'Vaterschaft',
            'unpaid': 'Unbezahlter Urlaub', 'other': 'Sonstiges'
        }

        ergebnisse = []
        for a in absences:
            emp = a.employee
            ergebnisse.append({
                'name': f'{emp.user.first_name} {emp.user.last_name}',
                'typ': typen.get(a.absence_type, a.absence_type),
                'von': a.start_date.strftime('%d.%m.%Y'),
                'bis': a.end_date.strftime('%d.%m.%Y'),
                'status': a.status
            })

        return {
            'ergebnis': ergebnisse,
            'datum': d.strftime('%d.%m.%Y'),
            'anzahl': len(ergebnisse)
        }

    return {'error': f'Unbekanntes Tool: {tool_name}'}
