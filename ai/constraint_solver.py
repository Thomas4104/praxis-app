# Constraint-Solver: Intelligenter Planungsassistent
# Prüft 7 Abhängigkeiten bei der Terminplanung:
# 1. Praxis-Öffnungszeiten (inkl. Feiertage)
# 2. Arbeitszeiten des Therapeuten (inkl. Abwesenheiten)
# 3. Kapazität des Therapeuten
# 4. Patientenpräferenzen (bevorzugte Zeiten)
# 5. Bestehende Termine (Überlappungsprüfung)
# 6. Ressourcen-Verfügbarkeit (Räume, Geräte)
# 7. Serien-Templates (Mindestabstände zwischen Terminen)

from datetime import datetime, date, time, timedelta
from models import (db, Appointment, Employee, Patient, WorkSchedule,
                    Resource, Location, Absence, TreatmentSeries,
                    TreatmentSeriesTemplate)


class ConstraintResult:
    """Ergebnis einer Constraint-Prüfung"""
    def __init__(self, ok, reason=''):
        self.ok = ok
        self.reason = reason

    def __bool__(self):
        return self.ok


class SlotSuggestion:
    """Ein vorgeschlagener Terminslot"""
    def __init__(self, start_dt, end_dt, employee_id, location_id, resource_id=None, score=100):
        self.start = start_dt
        self.end = end_dt
        self.employee_id = employee_id
        self.location_id = location_id
        self.resource_id = resource_id
        self.score = score  # Qualitätsbewertung 0-100
        self.warnings = []

    def to_dict(self):
        return {
            'datum': self.start.strftime('%d.%m.%Y'),
            'wochentag': ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag'][self.start.weekday()],
            'start': self.start.strftime('%H:%M'),
            'ende': self.end.strftime('%H:%M'),
            'employee_id': self.employee_id,
            'location_id': self.location_id,
            'resource_id': self.resource_id,
            'score': self.score,
            'warnungen': self.warnings,
        }


class ConstraintSolver:
    """
    Intelligenter Planungsassistent.
    Findet optimale Terminslots unter Berücksichtigung aller 7 Abhängigkeiten.
    """

    def check_all_constraints(self, start_dt, end_dt, employee_id, location_id=None,
                               resource_id=None, patient_id=None, series_id=None,
                               exclude_appointment_id=None):
        """
        Prüft ALLE 7 Constraints für einen bestimmten Zeitslot.
        Gibt eine Liste von ConstraintResults zurück.
        """
        results = []

        # 1. Praxis-Öffnungszeiten
        results.append(self._check_opening_hours(start_dt, end_dt, location_id, employee_id))

        # 2. Arbeitszeiten des Therapeuten
        results.append(self._check_work_schedule(start_dt, end_dt, employee_id))

        # 3. Abwesenheiten des Therapeuten
        results.append(self._check_absences(start_dt, employee_id))

        # 4. Bestehende Termine (Überlappung)
        results.append(self._check_overlapping_appointments(
            start_dt, end_dt, employee_id, exclude_appointment_id))

        # 5. Patientenpräferenzen
        if patient_id:
            results.append(self._check_patient_preferences(start_dt, patient_id))

        # 6. Ressourcen-Verfügbarkeit
        if resource_id:
            results.append(self._check_resource_availability(
                start_dt, end_dt, resource_id, exclude_appointment_id))

        # 7. Serien-Templates (Mindestabstände)
        if series_id:
            results.append(self._check_series_interval(start_dt, series_id))

        return results

    def find_slots(self, employee_id, duration_minutes=30, num_slots=5,
                   start_date=None, patient_id=None, series_id=None,
                   preferred_days=None, preferred_time_from=None,
                   preferred_time_to=None, requires_resource_type=None,
                   max_days_ahead=28):
        """
        Findet die besten verfügbaren Terminslots.

        Args:
            employee_id: Therapeut-ID
            duration_minutes: Dauer des Termins
            num_slots: Anzahl gewünschter Vorschläge
            start_date: Ab welchem Datum suchen
            patient_id: Patient-ID (für Präferenzen)
            series_id: Serien-ID (für Mindestabstände)
            preferred_days: Liste von Wochentagen (0=Mo, 6=So)
            preferred_time_from: Früheste Uhrzeit (str "HH:MM")
            preferred_time_to: Späteste Uhrzeit (str "HH:MM")
            requires_resource_type: Ressourcentyp benötigt ('room'/'equipment')
            max_days_ahead: Maximale Tage in die Zukunft suchen

        Returns:
            list[SlotSuggestion]: Sortiert nach Qualität (beste zuerst)
        """
        if start_date is None:
            start_date = date.today()

        employee = Employee.query.get(employee_id)
        if not employee:
            return []

        # Patientenpräferenzen laden
        patient_prefs = {}
        if patient_id:
            patient = Patient.query.get(patient_id)
            if patient and patient.preferred_appointment_times_json:
                patient_prefs = patient.preferred_appointment_times_json

        # Zeitfenster für bevorzugte Zeiten
        pref_from = None
        pref_to = None
        if preferred_time_from:
            pref_from = datetime.strptime(preferred_time_from, '%H:%M').time()
        if preferred_time_to:
            pref_to = datetime.strptime(preferred_time_to, '%H:%M').time()

        # Mindestabstand aus Serie ermitteln
        min_interval = 0
        last_series_appointment = None
        if series_id:
            series = TreatmentSeries.query.get(series_id)
            if series and series.template:
                min_interval = series.template.min_interval_days or 0
            # Letzten Termin der Serie finden
            last_apt = Appointment.query.filter(
                Appointment.series_id == series_id,
                Appointment.status != 'cancelled'
            ).order_by(Appointment.start_time.desc()).first()
            if last_apt:
                last_series_appointment = last_apt.start_time.date()

        # Effektives Startdatum (Mindestabstand berücksichtigen)
        effective_start = start_date
        if last_series_appointment and min_interval > 0:
            min_start = last_series_appointment + timedelta(days=min_interval)
            if min_start > effective_start:
                effective_start = min_start

        slots = []
        duration = timedelta(minutes=duration_minutes)

        for day_offset in range(max_days_ahead):
            check_date = effective_start + timedelta(days=day_offset)
            weekday = check_date.weekday()

            # Bevorzugte Tage prüfen
            if preferred_days is not None and weekday not in preferred_days:
                continue

            # Arbeitszeiten für diesen Tag
            schedules = WorkSchedule.query.filter_by(
                employee_id=employee_id,
                day_of_week=weekday,
                work_type='working'
            ).order_by(WorkSchedule.start_time).all()

            if not schedules:
                continue

            # Abwesenheit prüfen
            absence = Absence.query.filter(
                Absence.employee_id == employee_id,
                Absence.start_date <= check_date,
                Absence.end_date >= check_date,
                Absence.status != 'rejected'
            ).first()
            if absence:
                continue

            for sched in schedules:
                location_id = sched.location_id

                # Öffnungszeiten der Praxis prüfen
                location = Location.query.get(location_id) if location_id else None
                opening_start = sched.start_time
                opening_end = sched.end_time

                if location and location.opening_hours_json:
                    day_hours = location.opening_hours_json.get(str(weekday))
                    if not day_hours:
                        continue
                    loc_open = datetime.strptime(day_hours['open'], '%H:%M').time()
                    loc_close = datetime.strptime(day_hours['close'], '%H:%M').time()
                    # Arbeitszeit muss innerhalb der Öffnungszeiten liegen
                    opening_start = max(sched.start_time, loc_open)
                    opening_end = min(sched.end_time, loc_close)

                # Feiertage prüfen
                if location and location.holidays_json:
                    date_str = check_date.isoformat()
                    if date_str in location.holidays_json:
                        continue

                # Bevorzugte Zeitfenster einschränken
                slot_from = opening_start
                slot_to = opening_end
                if pref_from and pref_from > slot_from:
                    slot_from = pref_from
                if pref_to and pref_to < slot_to:
                    slot_to = pref_to

                # Bestehende Termine an diesem Tag/Block laden
                block_start = datetime.combine(check_date, slot_from)
                block_end = datetime.combine(check_date, slot_to)

                existing = Appointment.query.filter(
                    Appointment.employee_id == employee_id,
                    Appointment.status != 'cancelled',
                    Appointment.start_time < block_end,
                    Appointment.end_time > block_start
                ).order_by(Appointment.start_time).all()

                # Freie Slots in diesem Block finden
                current = block_start
                for apt in existing:
                    if apt.start_time > current and (apt.start_time - current) >= duration:
                        slot = self._create_slot(
                            current, current + duration, employee_id,
                            location_id, check_date, patient_prefs,
                            requires_resource_type
                        )
                        if slot:
                            slots.append(slot)
                            if len(slots) >= num_slots * 3:
                                break
                    current = max(current, apt.end_time)

                # Nach letztem Termin
                if current + duration <= block_end:
                    slot = self._create_slot(
                        current, current + duration, employee_id,
                        location_id, check_date, patient_prefs,
                        requires_resource_type
                    )
                    if slot:
                        slots.append(slot)

            if len(slots) >= num_slots * 3:
                break

        # Nach Score sortieren und beste zurückgeben
        slots.sort(key=lambda s: s.score, reverse=True)
        return slots[:num_slots]

    def plan_series(self, patient_id, employee_id, template_id,
                    start_date=None, preferred_day=None,
                    preferred_time=None, series_id=None):
        """
        Plant eine komplette Behandlungsserie.
        Gibt Terminvorschläge für alle Termine der Serie zurück.

        Args:
            patient_id: Patient-ID
            employee_id: Therapeut-ID
            template_id: Template-ID
            start_date: Startdatum
            preferred_day: Bevorzugter Wochentag (0-6)
            preferred_time: Bevorzugte Uhrzeit ("HH:MM")
            series_id: Optionale Serien-ID (wenn bereits erstellt)

        Returns:
            list[dict]: Liste von Terminvorschlägen
        """
        template = TreatmentSeriesTemplate.query.get(template_id)
        if not template:
            return {'error': 'Template nicht gefunden'}

        if start_date is None:
            start_date = date.today() + timedelta(days=1)

        num_appointments = template.num_appointments
        duration = template.duration_minutes
        min_interval = template.min_interval_days or 1
        requires_resource = template.requires_resource

        preferred_days = [preferred_day] if preferred_day is not None else None
        resource_type = 'room' if requires_resource else None

        suggestions = []
        current_date = start_date

        for i in range(num_appointments):
            # Slot für diesen Termin finden
            slot_results = self.find_slots(
                employee_id=employee_id,
                duration_minutes=duration,
                num_slots=1,
                start_date=current_date,
                patient_id=patient_id,
                preferred_days=preferred_days,
                preferred_time_from=preferred_time,
                preferred_time_to=None,
                requires_resource_type=resource_type,
                max_days_ahead=60,
            )

            if slot_results:
                slot = slot_results[0]
                suggestion = slot.to_dict()
                suggestion['termin_nr'] = i + 1
                suggestions.append(suggestion)
                # Nächster Termin frühestens nach Mindestabstand
                current_date = slot.start.date() + timedelta(days=min_interval)
            else:
                suggestions.append({
                    'termin_nr': i + 1,
                    'error': f'Kein freier Slot gefunden ab {current_date.strftime("%d.%m.%Y")}',
                })
                current_date = current_date + timedelta(days=min_interval)

        return {
            'template': template.name,
            'anzahl_termine': num_appointments,
            'dauer_minuten': duration,
            'vorschlaege': suggestions,
        }

    # === Private Constraint-Prüfungen ===

    def _check_opening_hours(self, start_dt, end_dt, location_id, employee_id):
        """Constraint 1: Praxis-Öffnungszeiten"""
        location = None
        if location_id:
            location = Location.query.get(location_id)
        else:
            # Standort aus Arbeitsplan ermitteln
            sched = WorkSchedule.query.filter_by(
                employee_id=employee_id,
                day_of_week=start_dt.weekday()
            ).first()
            if sched and sched.location_id:
                location = Location.query.get(sched.location_id)

        if not location:
            return ConstraintResult(True)  # Kein Standort → keine Einschränkung

        weekday = str(start_dt.weekday())
        hours = location.opening_hours_json or {}
        if weekday not in hours:
            return ConstraintResult(False, f'Praxis {location.name} ist am {start_dt.strftime("%A")} geschlossen')

        day_hours = hours[weekday]
        loc_open = datetime.strptime(day_hours['open'], '%H:%M').time()
        loc_close = datetime.strptime(day_hours['close'], '%H:%M').time()

        if start_dt.time() < loc_open:
            return ConstraintResult(False, f'Vor Öffnungszeit ({day_hours["open"]})')
        if end_dt.time() > loc_close:
            return ConstraintResult(False, f'Nach Schliessungszeit ({day_hours["close"]})')

        # Feiertage
        if location.holidays_json:
            date_str = start_dt.date().isoformat()
            if date_str in location.holidays_json:
                return ConstraintResult(False, 'Feiertag')

        return ConstraintResult(True)

    def _check_work_schedule(self, start_dt, end_dt, employee_id):
        """Constraint 2: Arbeitszeiten des Therapeuten"""
        weekday = start_dt.weekday()
        schedules = WorkSchedule.query.filter_by(
            employee_id=employee_id,
            day_of_week=weekday,
            work_type='working'
        ).all()

        if not schedules:
            return ConstraintResult(False, 'Therapeut arbeitet an diesem Tag nicht')

        # Prüfen ob der Slot in einem Arbeitsblock liegt
        for sched in schedules:
            if start_dt.time() >= sched.start_time and end_dt.time() <= sched.end_time:
                return ConstraintResult(True)

        return ConstraintResult(False, 'Ausserhalb der Arbeitszeiten des Therapeuten')

    def _check_absences(self, start_dt, employee_id):
        """Constraint 2b: Abwesenheiten"""
        absence = Absence.query.filter(
            Absence.employee_id == employee_id,
            Absence.start_date <= start_dt.date(),
            Absence.end_date >= start_dt.date(),
            Absence.status != 'rejected'
        ).first()

        if absence:
            type_names = {'vacation': 'Ferien', 'illness': 'Krankheit', 'training': 'Weiterbildung'}
            return ConstraintResult(False, f'Therapeut ist abwesend ({type_names.get(absence.type, absence.type)})')

        return ConstraintResult(True)

    def _check_overlapping_appointments(self, start_dt, end_dt, employee_id, exclude_id=None):
        """Constraint 5: Bestehende Termine"""
        query = Appointment.query.filter(
            Appointment.employee_id == employee_id,
            Appointment.status != 'cancelled',
            Appointment.start_time < end_dt,
            Appointment.end_time > start_dt
        )
        if exclude_id:
            query = query.filter(Appointment.id != exclude_id)

        overlap = query.first()
        if overlap:
            return ConstraintResult(
                False,
                f'Terminkonflikt: {overlap.patient.full_name} von '
                f'{overlap.start_time.strftime("%H:%M")} bis {overlap.end_time.strftime("%H:%M")}'
            )

        return ConstraintResult(True)

    def _check_patient_preferences(self, start_dt, patient_id):
        """Constraint 4: Patientenpräferenzen"""
        patient = Patient.query.get(patient_id)
        if not patient or not patient.preferred_appointment_times_json:
            return ConstraintResult(True)

        prefs = patient.preferred_appointment_times_json
        weekday = start_dt.weekday()
        hour = start_dt.hour

        # Bevorzugte Tage prüfen
        pref_days = prefs.get('days', [])
        if pref_days and weekday not in pref_days:
            day_names = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']
            return ConstraintResult(True)  # Warnung, kein hartes Constraint

        # Bevorzugte Zeiten prüfen
        pref_from = prefs.get('time_from')
        pref_to = prefs.get('time_to')
        if pref_from:
            pref_time = datetime.strptime(pref_from, '%H:%M').time()
            if start_dt.time() < pref_time:
                return ConstraintResult(True)  # Weiche Präferenz

        return ConstraintResult(True)

    def _check_resource_availability(self, start_dt, end_dt, resource_id, exclude_id=None):
        """Constraint 6: Ressourcen-Verfügbarkeit"""
        resource = Resource.query.get(resource_id)
        if not resource or not resource.is_active:
            return ConstraintResult(False, 'Ressource nicht verfügbar')

        query = Appointment.query.filter(
            Appointment.resource_id == resource_id,
            Appointment.status != 'cancelled',
            Appointment.start_time < end_dt,
            Appointment.end_time > start_dt
        )
        if exclude_id:
            query = query.filter(Appointment.id != exclude_id)

        # Kapazität berücksichtigen (für Gruppentherapie)
        count = query.count()
        if count >= resource.capacity:
            return ConstraintResult(False, f'Ressource "{resource.name}" ist belegt')

        return ConstraintResult(True)

    def _check_series_interval(self, start_dt, series_id):
        """Constraint 7: Mindestabstand zwischen Serien-Terminen"""
        series = TreatmentSeries.query.get(series_id)
        if not series or not series.template:
            return ConstraintResult(True)

        min_interval = series.template.min_interval_days
        if not min_interval:
            return ConstraintResult(True)

        # Letzten Termin der Serie finden
        last_apt = Appointment.query.filter(
            Appointment.series_id == series_id,
            Appointment.status != 'cancelled'
        ).order_by(Appointment.start_time.desc()).first()

        if last_apt:
            days_diff = (start_dt.date() - last_apt.start_time.date()).days
            if days_diff < min_interval:
                return ConstraintResult(
                    False,
                    f'Mindestabstand nicht eingehalten: {days_diff} von {min_interval} Tagen'
                )

        return ConstraintResult(True)

    def _create_slot(self, start_dt, end_dt, employee_id, location_id,
                     check_date, patient_prefs, requires_resource_type):
        """Erstellt einen SlotSuggestion mit Score-Bewertung"""
        # Nur Termine in der Zukunft
        if start_dt <= datetime.now():
            return None

        score = 100

        # Patientenpräferenzen berücksichtigen
        if patient_prefs:
            pref_days = patient_prefs.get('days', [])
            if pref_days and check_date.weekday() in pref_days:
                score += 10  # Bonus für bevorzugten Tag

            pref_from = patient_prefs.get('time_from')
            pref_to = patient_prefs.get('time_to')
            if pref_from:
                pref_start = datetime.strptime(pref_from, '%H:%M').time()
                if start_dt.time() >= pref_start:
                    score += 5
            if pref_to:
                pref_end = datetime.strptime(pref_to, '%H:%M').time()
                if end_dt.time() <= pref_end:
                    score += 5

        # Ressource finden wenn benötigt
        resource_id = None
        if requires_resource_type and location_id:
            resource = Resource.query.filter_by(
                location_id=location_id,
                type=requires_resource_type,
                is_active=True
            ).first()
            if resource:
                # Verfügbarkeit prüfen
                occupied = Appointment.query.filter(
                    Appointment.resource_id == resource.id,
                    Appointment.status != 'cancelled',
                    Appointment.start_time < end_dt,
                    Appointment.end_time > start_dt
                ).count()
                if occupied < resource.capacity:
                    resource_id = resource.id
                else:
                    # Andere Ressourcen probieren
                    resources = Resource.query.filter_by(
                        location_id=location_id,
                        type=requires_resource_type,
                        is_active=True
                    ).all()
                    for res in resources:
                        occ = Appointment.query.filter(
                            Appointment.resource_id == res.id,
                            Appointment.status != 'cancelled',
                            Appointment.start_time < end_dt,
                            Appointment.end_time > start_dt
                        ).count()
                        if occ < res.capacity:
                            resource_id = res.id
                            break
                    if not resource_id:
                        return None  # Keine Ressource frei

        # Morgen-Slots leicht bevorzugen
        if start_dt.hour < 12:
            score += 2

        # Nähere Termine leicht bevorzugen
        days_from_now = (check_date - date.today()).days
        if days_from_now <= 7:
            score += 5
        elif days_from_now <= 14:
            score += 2

        slot = SlotSuggestion(start_dt, end_dt, employee_id, location_id, resource_id, score)
        return slot


# Globale Instanz
solver = ConstraintSolver()
