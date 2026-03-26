"""
Automatische Terminplanung nach Cenplex-Vorbild
Scoring-basierter Algorithmus fuer optimale Terminverteilung
"""
from datetime import datetime, timedelta, time
from models import Appointment, Employee, WorkSchedule, Absence, db


# Scoring-Gewichtungen (Cenplex AppointmentFinder)
INTERVAL_WEIGHT = 1.0
TIME_WEIGHT = 0.5
WEEKDAY_WEIGHT = 1.4
WEEKDAY_SWITCH_PENALTY = 3.5
WEEKDAY_DISPERSION_MULTIPLIER = 8.0
WEEKDAY_COHESION_BOOST = 1.5


def find_available_slots(employee_id, start_date, end_date, duration_minutes=30,
                         preferred_days=None, preferred_time_start=None,
                         preferred_time_end=None, min_interval_days=2,
                         preferred_interval_days=7, location_id=None,
                         exclude_appointment_ids=None):
    """
    Findet verfuegbare Zeitslots fuer einen Therapeuten.
    Beruecksichtigt Arbeitszeiten, bestehende Termine und Abwesenheiten.

    Returns: Liste von {datetime, score} Dictionaries, sortiert nach Score
    """
    slots = []
    current_date = start_date

    while current_date <= end_date:
        # Wochentag-Filter
        if preferred_days and current_date.weekday() not in preferred_days:
            current_date += timedelta(days=1)
            continue

        # Arbeitszeiten fuer diesen Tag laden
        day_schedules = WorkSchedule.query.filter_by(
            employee_id=employee_id,
            day_of_week=current_date.weekday()
        ).filter(
            (WorkSchedule.valid_from == None) | (WorkSchedule.valid_from <= current_date),
            (WorkSchedule.valid_to == None) | (WorkSchedule.valid_to >= current_date)
        ).all()

        if not day_schedules:
            current_date += timedelta(days=1)
            continue

        # Abwesenheiten pruefen
        absences = Absence.query.filter(
            Absence.employee_id == employee_id,
            Absence.start_date <= current_date,
            Absence.end_date >= current_date
        ).first()

        if absences:
            current_date += timedelta(days=1)
            continue

        # Bestehende Termine laden
        day_start = datetime.combine(current_date, time(0, 0))
        day_end = datetime.combine(current_date, time(23, 59))
        existing = Appointment.query.filter(
            Appointment.employee_id == employee_id,
            Appointment.start_time >= day_start,
            Appointment.start_time <= day_end,
            Appointment.status.notin_(['cancelled', 'deleted'])
        ).all()

        if exclude_appointment_ids:
            existing = [a for a in existing if a.id not in exclude_appointment_ids]

        # Fuer jeden Arbeitszeit-Block freie Slots finden
        for schedule in day_schedules:
            if schedule.work_type not in ('treatment', 'regular'):
                continue

            slot_start = datetime.combine(current_date, schedule.start_time)
            slot_end = datetime.combine(current_date, schedule.end_time)

            # Zeitfilter anwenden
            if preferred_time_start:
                pref_start = datetime.combine(current_date, preferred_time_start)
                if slot_start < pref_start:
                    slot_start = pref_start
            if preferred_time_end:
                pref_end = datetime.combine(current_date, preferred_time_end)
                if slot_end > pref_end:
                    slot_end = pref_end

            # 5-Minuten-Slots durchgehen
            current_slot = slot_start
            while current_slot + timedelta(minutes=duration_minutes) <= slot_end:
                slot_end_time = current_slot + timedelta(minutes=duration_minutes)

                # Konflikt pruefen
                conflict = False
                for appt in existing:
                    if current_slot < appt.end_time and slot_end_time > appt.start_time:
                        conflict = True
                        break

                if not conflict:
                    slots.append({
                        'start': current_slot,
                        'end': slot_end_time,
                        'employee_id': employee_id,
                        'score': 0  # Wird spaeter berechnet
                    })

                current_slot += timedelta(minutes=5)

        current_date += timedelta(days=1)

    return slots


def score_slots(slots, existing_appointments, preferred_interval_days=7, preferred_days=None):
    """
    Bewertet Slots nach Cenplex-Scoring-Algorithmus.
    Hoehere Scores = bessere Slots.
    """
    if not slots or not existing_appointments:
        return slots

    last_appt_dates = sorted([a.start_time for a in existing_appointments])
    last_date = last_appt_dates[-1] if last_appt_dates else None

    # Bevorzugte Wochentage aus bestehenden Terminen ableiten
    existing_weekdays = [a.start_time.weekday() for a in existing_appointments]
    most_common_weekday = max(set(existing_weekdays), key=existing_weekdays.count) if existing_weekdays else None

    for slot in slots:
        score = 100.0  # Basis-Score

        # Intervall-Score: Naehe zum bevorzugten Intervall
        if last_date:
            days_diff = (slot['start'] - last_date).days
            interval_diff = abs(days_diff - preferred_interval_days)
            score -= interval_diff * INTERVAL_WEIGHT

        # Uhrzeit-Score: Aehnliche Uhrzeit wie bisherige Termine
        if existing_appointments:
            avg_hour = sum(a.start_time.hour + a.start_time.minute / 60 for a in existing_appointments) / len(existing_appointments)
            slot_hour = slot['start'].hour + slot['start'].minute / 60
            time_diff = abs(slot_hour - avg_hour)
            score -= time_diff * TIME_WEIGHT

        # Wochentag-Score: Gleicher Wochentag bevorzugt
        if most_common_weekday is not None:
            if slot['start'].weekday() == most_common_weekday:
                score += WEEKDAY_COHESION_BOOST
            else:
                score -= WEEKDAY_SWITCH_PENALTY

        slot['score'] = round(score, 2)

    # Nach Score sortieren (hoechster zuerst)
    slots.sort(key=lambda s: s['score'], reverse=True)
    return slots


def schedule_series_appointments(series_id, total_appointments, duration_minutes=30,
                                  start_date=None, preferred_interval_days=7,
                                  preferred_days=None, preferred_time_start=None,
                                  preferred_time_end=None):
    """
    Plant automatisch eine Serie von Terminen (Cenplex: ScheduleAppointments).

    Returns: Liste von geplanten Slot-Vorschlaegen
    """
    from models import TreatmentSeries
    series = TreatmentSeries.query.get(series_id)
    if not series:
        return []

    employee_id = series.therapist_id
    if not start_date:
        start_date = datetime.now().date()

    end_date = start_date + timedelta(days=365)  # Max 1 Jahr voraus

    # Bestehende Termine der Serie
    existing = Appointment.query.filter_by(
        series_id=series_id
    ).filter(
        Appointment.status.notin_(['cancelled', 'deleted'])
    ).order_by(Appointment.start_time).all()

    appointments_needed = total_appointments - len(existing)
    if appointments_needed <= 0:
        return []

    # Verfuegbare Slots finden
    all_slots = find_available_slots(
        employee_id=employee_id,
        start_date=start_date,
        end_date=end_date,
        duration_minutes=duration_minutes,
        preferred_days=preferred_days,
        preferred_time_start=preferred_time_start,
        preferred_time_end=preferred_time_end,
        location_id=series.location_id
    )

    # Slots bewerten
    scored_slots = score_slots(all_slots, existing, preferred_interval_days, preferred_days)

    # Greedy: Beste Slots auswaehlen mit Mindestabstand
    selected = []
    min_interval = timedelta(days=max(1, preferred_interval_days - 2))

    for slot in scored_slots:
        if len(selected) >= appointments_needed:
            break

        # Mindestabstand zu allen bereits gewaehlten pruefen
        too_close = False
        for sel in selected:
            if abs((slot['start'] - sel['start']).days) < min_interval.days:
                too_close = True
                break
        # Auch Abstand zu bestehenden Terminen pruefen
        for appt in existing:
            if abs((slot['start'] - appt.start_time).days) < min_interval.days:
                too_close = True
                break

        if not too_close:
            selected.append(slot)

    return selected


def get_waitlist_suggestions(appointment_id, max_suggestions=5):
    """
    Findet freie Slots fuer einen Wartelisten-Termin (Cenplex: WaitList).
    """
    appointment = Appointment.query.get(appointment_id)
    if not appointment:
        return []

    start_date = datetime.now().date()
    end_date = start_date + timedelta(days=30)

    slots = find_available_slots(
        employee_id=appointment.employee_id,
        start_date=start_date,
        end_date=end_date,
        duration_minutes=appointment.duration_minutes or 30
    )

    return slots[:max_suggestions]
