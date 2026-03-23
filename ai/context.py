from datetime import datetime
from flask_login import current_user
from models import db, Employee, Appointment, Location


class ContextManager:
    """Baut den Kontext fuer KI-Anfragen zusammen"""

    @staticmethod
    def build_context(user=None):
        """Erstellt den vollstaendigen Kontext fuer den KI-Agenten"""
        if user is None:
            from flask_login import current_user
            user = current_user

        now = datetime.now()
        hour = now.hour
        if hour < 12:
            tageszeit = 'Morgen'
        elif hour < 17:
            tageszeit = 'Nachmittag'
        else:
            tageszeit = 'Abend'

        context_parts = [
            f"Aktuelle Zeit: {now.strftime('%d.%m.%Y %H:%M')} ({tageszeit})",
            f"Benutzer: {user.first_name} {user.last_name}",
            f"Rolle: {user.role}",
        ]

        # Mitarbeiter-Daten laden
        employee = Employee.query.filter_by(user_id=user.id).first()
        if employee:
            if employee.default_location:
                context_parts.append(f"Standort: {employee.default_location.name}")

            # Heutige Termine zaehlen
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
            today_appointments = Appointment.query.filter(
                Appointment.employee_id == employee.id,
                Appointment.start_time >= today_start,
                Appointment.start_time <= today_end,
                Appointment.status.in_(['scheduled', 'confirmed'])
            ).count()
            context_parts.append(f"Heutige Termine: {today_appointments}")

        # Standorte auflisten
        locations = Location.query.filter_by(
            organization_id=user.organization_id,
            is_active=True
        ).all()
        if locations:
            standorte = ', '.join([loc.name for loc in locations])
            context_parts.append(f"Verfuegbare Standorte: {standorte}")

        return '\n'.join(context_parts)
