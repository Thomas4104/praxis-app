# Kontext-Manager: Sammelt Informationen über den aktuellen Benutzer und die Situation

from datetime import datetime, date
from flask_login import current_user


def get_user_context():
    """Erstellt den Kontext für die KI basierend auf dem aktuellen Benutzer."""
    if not current_user or not current_user.is_authenticated:
        return {}

    context = {
        'user_id': current_user.id,
        'user_name': current_user.name,
        'user_role': current_user.role,
        'current_date': date.today().isoformat(),
        'current_time': datetime.now().strftime('%H:%M'),
        'current_weekday': ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag'][date.today().weekday()],
    }

    # Mitarbeiter-Informationen hinzufügen falls vorhanden
    if current_user.employee:
        emp = current_user.employee
        context['employee_id'] = emp.id
        context['organization_id'] = emp.organization_id
        context['organization_name'] = emp.organization.name if emp.organization else ''

    return context


def format_context_for_prompt(context):
    """Formatiert den Kontext als lesbaren Text für den System-Prompt."""
    if not context:
        return ''

    lines = [
        f"Aktueller Benutzer: {context.get('user_name', 'Unbekannt')}",
        f"Rolle: {context.get('user_role', 'Unbekannt')}",
        f"Organisation: {context.get('organization_name', 'Unbekannt')}",
        f"Datum: {context.get('current_weekday', '')}, {context.get('current_date', '')}",
        f"Uhrzeit: {context.get('current_time', '')}",
    ]
    return '\n'.join(lines)
