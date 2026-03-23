"""Constraint-Solver fuer automatische Terminvorschlaege.

Beruecksichtigt alle 7 Abhaengigkeiten:
1. Praxis-Oeffnungszeiten (inkl. Feiertage)
2. Arbeitszeiten des Therapeuten
3. Absenzen des Therapeuten
4. Bestehende Termine (keine Ueberlappung)
5. Ressourcen-Verfuegbarkeit (Raeume/Geraete)
6. Mindestabstand zwischen Terminen der Serie
7. Patientenpraeferenzen (bevorzugte Zeiten)
"""
import json
from datetime import datetime, date, time, timedelta
from models import db, Appointment, Employee, WorkSchedule, Absence, Holiday, \
    Location, Resource, ResourceBooking


def find_available_slots(
    employee_id,
    location_id=None,
    duration_minutes=30,
    num_slots=5,
    min_interval_days=0,
    preferred_days=None,
    preferred_times=None,
    start_date=None,
    resource_type=None,
):
    """
    Findet verfuegbare Terminslots unter Beruecksichtigung aller Einschraenkungen.

    Returns: Liste von {datum, start_zeit, end_zeit, raum_id, score, dauer_minuten}
    """
    if start_date is None:
        start_date = date.today()
    if isinstance(start_date, str):
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        except ValueError:
            start_date = date.today()

    employee = Employee.query.get(employee_id)
    if not employee:
        return []

    if not location_id and employee.default_location_id:
        location_id = employee.default_location_id

    # Daten vorab laden (max. 60 Tage voraus suchen)
    end_search = start_date + timedelta(days=60)

    # 1. Feiertage laden
    holidays_set = set()
    holidays = Holiday.query.filter(
        Holiday.date >= start_date,
        Holiday.date <= end_search
    ).all()
    for h in holidays:
        holidays_set.add(h.date)

    # 2. Arbeitszeiten des Therapeuten
    work_schedules = WorkSchedule.query.filter_by(employee_id=employee_id).all()
    work_by_day = {}  # day_of_week -> [(start_time, end_time)]
    for ws in work_schedules:
        if ws.day_of_week not in work_by_day:
            work_by_day[ws.day_of_week] = []
        work_by_day[ws.day_of_week].append((ws.start_time, ws.end_time))

    # 3. Absenzen des Therapeuten
    absences = Absence.query.filter(
        Absence.employee_id == employee_id,
        Absence.status == 'approved',
        Absence.start_date <= end_search,
        Absence.end_date >= start_date
    ).all()
    absence_dates = set()
    for a in absences:
        current = a.start_date
        while current <= a.end_date:
            absence_dates.add(current)
            current += timedelta(days=1)

    # 4. Bestehende Termine laden
    existing_appointments = Appointment.query.filter(
        Appointment.employee_id == employee_id,
        Appointment.status.notin_(['cancelled', 'no_show']),
        Appointment.start_time >= datetime.combine(start_date, time(0, 0)),
        Appointment.start_time <= datetime.combine(end_search, time(23, 59))
    ).all()

    # Termine nach Tag gruppieren
    appts_by_date = {}
    for appt in existing_appointments:
        d = appt.start_time.date()
        if d not in appts_by_date:
            appts_by_date[d] = []
        appts_by_date[d].append((appt.start_time.time(), appt.end_time.time()))

    # 5. Oeffnungszeiten der Praxis
    opening_hours = {}
    if location_id:
        location = Location.query.get(location_id)
        if location and location.opening_hours_json:
            try:
                oh = json.loads(location.opening_hours_json)
                day_names = ['montag', 'dienstag', 'mittwoch', 'donnerstag', 'freitag', 'samstag', 'sonntag']
                for idx, day_name in enumerate(day_names):
                    if day_name in oh and oh[day_name]:
                        opening_hours[idx] = (
                            _parse_time(oh[day_name]['von']),
                            _parse_time(oh[day_name]['bis'])
                        )
            except (json.JSONDecodeError, KeyError):
                pass

    # Slots sammeln — maximal 3 pro Tag, damit verschiedene Tage vertreten sind
    found_slots = []
    last_slot_date = None
    current_search_date = start_date
    MAX_PER_DAY = 3

    while current_search_date <= end_search and len(found_slots) < num_slots * 5:
        dow = current_search_date.weekday()
        day_slot_count = 0

        # Feiertag pruefen
        if current_search_date in holidays_set:
            current_search_date += timedelta(days=1)
            continue

        # Absenz pruefen
        if current_search_date in absence_dates:
            current_search_date += timedelta(days=1)
            continue

        # Mindestabstand pruefen
        if last_slot_date and min_interval_days > 0:
            if (current_search_date - last_slot_date).days < min_interval_days:
                current_search_date += timedelta(days=1)
                continue

        # Bevorzugte Tage pruefen
        day_score_bonus = 0
        if preferred_days is not None:
            if dow not in preferred_days:
                day_score_bonus = -10  # Nicht bevorzugter Tag, aber trotzdem moeglich
            else:
                day_score_bonus = 5

        # Arbeitszeiten fuer diesen Wochentag
        work_windows = work_by_day.get(dow, [])
        if not work_windows:
            current_search_date += timedelta(days=1)
            continue

        # Oeffnungszeiten pruefen
        if dow in opening_hours:
            oh_start, oh_end = opening_hours[dow]
        else:
            # Wenn keine Oeffnungszeiten -> dieser Tag ist geschlossen
            if opening_hours:  # Nur wenn Oeffnungszeiten definiert sind
                current_search_date += timedelta(days=1)
                continue
            oh_start = time(6, 0)
            oh_end = time(20, 0)

        # Bestehende Termine fuer diesen Tag
        day_appts = appts_by_date.get(current_search_date, [])

        # Freie Slots in den Arbeitszeiten finden
        for ws_start, ws_end in work_windows:
            # Arbeitszeit mit Oeffnungszeiten einschraenken
            eff_start = max(ws_start, oh_start)
            eff_end = min(ws_end, oh_end)

            # In 15-Minuten-Schritten durchgehen
            slot_time = datetime.combine(current_search_date, eff_start)
            slot_end_limit = datetime.combine(current_search_date, eff_end) - timedelta(minutes=duration_minutes)

            while slot_time <= slot_end_limit:
                slot_end = slot_time + timedelta(minutes=duration_minutes)

                # Ueberschneidung mit bestehenden Terminen pruefen
                is_free = True
                for appt_start, appt_end in day_appts:
                    appt_start_dt = datetime.combine(current_search_date, appt_start)
                    appt_end_dt = datetime.combine(current_search_date, appt_end)
                    if slot_time < appt_end_dt and slot_end > appt_start_dt:
                        is_free = False
                        break

                if is_free:
                    # Score berechnen
                    score = 50 + day_score_bonus

                    # Bevorzugte Zeiten
                    hour = slot_time.hour
                    if preferred_times:
                        if 'morning' in preferred_times and 8 <= hour < 12:
                            score += 10
                        elif 'afternoon' in preferred_times and 13 <= hour < 17:
                            score += 10
                        elif 'evening' in preferred_times and 17 <= hour < 20:
                            score += 10

                    # Fruehe Termine bevorzugen (weniger Wartezeit)
                    days_ahead = (current_search_date - start_date).days
                    score -= days_ahead  # Je frueher, desto besser

                    found_slots.append({
                        'datum': current_search_date.isoformat(),
                        'start_zeit': slot_time.strftime('%H:%M'),
                        'end_zeit': slot_end.strftime('%H:%M'),
                        'raum_id': None,
                        'score': max(0, score),
                        'dauer_minuten': duration_minutes
                    })

                    day_slot_count += 1
                    if day_slot_count >= MAX_PER_DAY:
                        break

                    if len(found_slots) >= num_slots * 5:
                        break

                slot_time += timedelta(minutes=15)

        if found_slots:
            # Letzten gefundenen Slot-Datum merken fuer Mindestabstand
            last_slot_date = current_search_date

        current_search_date += timedelta(days=1)

    # Nach Score sortieren und Top-Ergebnisse zurueckgeben
    found_slots.sort(key=lambda s: s['score'], reverse=True)

    # Mindestabstand zwischen den zurueckgegebenen Slots beruecksichtigen
    if min_interval_days > 0:
        filtered = []
        last_date = None
        for slot in found_slots:
            slot_date = datetime.strptime(slot['datum'], '%Y-%m-%d').date()
            if last_date is None or (slot_date - last_date).days >= min_interval_days:
                filtered.append(slot)
                last_date = slot_date
                if len(filtered) >= num_slots:
                    break
        return filtered

    return found_slots[:num_slots]


def check_availability(employee_id, check_date, check_time, duration_minutes):
    """Prueft ob ein Therapeut zu einer bestimmten Zeit verfuegbar ist.

    Returns: {available: bool, reason: str}
    """
    if isinstance(check_date, str):
        check_date = datetime.strptime(check_date, '%Y-%m-%d').date()
    if isinstance(check_time, str):
        parts = check_time.split(':')
        check_time = time(int(parts[0]), int(parts[1]))

    start_dt = datetime.combine(check_date, check_time)
    end_dt = start_dt + timedelta(minutes=duration_minutes)

    # 1. Feiertag?
    holiday = Holiday.query.filter_by(date=check_date).first()
    if holiday:
        return {'available': False, 'reason': f'Feiertag: {holiday.name}'}

    # 2. Absenz?
    absence = Absence.query.filter(
        Absence.employee_id == employee_id,
        Absence.status == 'approved',
        Absence.start_date <= check_date,
        Absence.end_date >= check_date
    ).first()
    if absence:
        types = {
            'vacation': 'Ferien', 'sick': 'Krank', 'accident': 'Unfall',
            'training': 'Weiterbildung', 'military': 'Militär'
        }
        return {'available': False, 'reason': f'Absenz: {types.get(absence.absence_type, absence.absence_type)}'}

    # 3. Arbeitszeit?
    dow = check_date.weekday()
    schedules = WorkSchedule.query.filter_by(
        employee_id=employee_id, day_of_week=dow
    ).all()

    in_work_time = False
    for ws in schedules:
        if ws.start_time <= check_time and ws.end_time >= end_dt.time():
            in_work_time = True
            break

    if schedules and not in_work_time:
        return {'available': False, 'reason': 'Ausserhalb der Arbeitszeit'}

    # 4. Bestehender Termin?
    conflict = Appointment.query.filter(
        Appointment.employee_id == employee_id,
        Appointment.status.notin_(['cancelled', 'no_show']),
        Appointment.start_time < end_dt,
        Appointment.end_time > start_dt
    ).first()

    if conflict:
        patient_name = ''
        if conflict.patient:
            patient_name = f'{conflict.patient.first_name} {conflict.patient.last_name}'
        return {'available': False, 'reason': f'Termin belegt ({patient_name}, {conflict.start_time.strftime("%H:%M")}-{conflict.end_time.strftime("%H:%M")})'}

    return {'available': True, 'reason': 'Verfügbar'}


def find_gaps(target_date, location_id=None, min_duration=15):
    """Findet freie Luecken im Kalender eines Tages."""
    if isinstance(target_date, str):
        target_date = datetime.strptime(target_date, '%Y-%m-%d').date()

    # Alle aktiven Therapeuten am Standort
    query = Employee.query.filter_by(is_active=True)
    if location_id:
        query = query.filter_by(default_location_id=location_id)
    employees = query.all()

    gaps = []
    for emp in employees:
        emp_name = f'{emp.user.first_name} {emp.user.last_name}' if emp.user else f'MA #{emp.id}'

        # Arbeitszeiten
        dow = target_date.weekday()
        schedules = WorkSchedule.query.filter_by(
            employee_id=emp.id, day_of_week=dow
        ).all()

        if not schedules:
            continue

        # Termine des Tages
        day_start = datetime.combine(target_date, time(0, 0))
        day_end = datetime.combine(target_date + timedelta(days=1), time(0, 0))
        appts = Appointment.query.filter(
            Appointment.employee_id == emp.id,
            Appointment.status.notin_(['cancelled', 'no_show']),
            Appointment.start_time >= day_start,
            Appointment.start_time < day_end
        ).order_by(Appointment.start_time).all()

        for ws in schedules:
            ws_start = datetime.combine(target_date, ws.start_time)
            ws_end = datetime.combine(target_date, ws.end_time)

            # Freie Zeiten innerhalb der Arbeitszeit finden
            current = ws_start
            for appt in appts:
                if appt.start_time > current and appt.start_time <= ws_end:
                    gap_minutes = int((appt.start_time - current).total_seconds() / 60)
                    if gap_minutes >= min_duration:
                        gaps.append({
                            'therapeut': emp_name,
                            'therapeut_id': emp.id,
                            'datum': target_date.isoformat(),
                            'von': current.strftime('%H:%M'),
                            'bis': appt.start_time.strftime('%H:%M'),
                            'dauer_minuten': gap_minutes
                        })
                if appt.end_time > current:
                    current = appt.end_time

            # Restzeit nach letztem Termin
            if current < ws_end:
                gap_minutes = int((ws_end - current).total_seconds() / 60)
                if gap_minutes >= min_duration:
                    gaps.append({
                        'therapeut': emp_name,
                        'therapeut_id': emp.id,
                        'datum': target_date.isoformat(),
                        'von': current.strftime('%H:%M'),
                        'bis': ws_end.strftime('%H:%M'),
                        'dauer_minuten': gap_minutes
                    })

    return gaps


def _parse_time(time_str):
    """Parst einen Zeit-String (HH:MM) in ein time-Objekt."""
    parts = time_str.split(':')
    return time(int(parts[0]), int(parts[1]))
