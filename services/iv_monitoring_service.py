"""
Service zur Ueberwachung von IV-Verfuegungen.
Erstellt automatisch Aufgaben bei ablaufenden oder abgelaufenen IV-Behandlungen.
"""
from datetime import date, timedelta
from models import db, TreatmentSeries, Task
import logging

logger = logging.getLogger(__name__)


def check_iv_expiry(org_id, warning_days=30):
    """Prueft alle IV-Serien auf ablaufende Verfuegungen.

    Args:
        org_id: Organisation-ID
        warning_days: Tage vor Ablauf fuer Vorwarnung (Standard: 30)

    Returns:
        dict mit 'expiring' und 'expired' Zaehler
    """
    today = date.today()
    warning_date = today + timedelta(days=warning_days)

    results = {'expiring': 0, 'expired': 0, 'tasks_created': 0}

    # Aktive IV-Serien mit Verfuegungsdatum
    series_list = TreatmentSeries.query.filter(
        TreatmentSeries.status == 'active',
        TreatmentSeries.insurance_type == 'IV',
        TreatmentSeries.iv_valid_until.isnot(None),
    ).join(TreatmentSeries.patient).filter_by(
        organization_id=org_id
    ).all()

    for series in series_list:
        if series.iv_valid_until < today:
            # Bereits abgelaufen
            results['expired'] += 1
            _create_iv_task(
                series,
                f'IV-Verfuegung abgelaufen: {series.patient.last_name} {series.patient.first_name}',
                f'Die IV-Verfuegung ({series.iv_decision_number or "ohne Nr."}) '
                f'ist am {series.iv_valid_until.strftime("%d.%m.%Y")} abgelaufen. '
                f'Bitte Verlaengerung beantragen oder Serie abschliessen.',
                'high'
            )
            results['tasks_created'] += 1

        elif series.iv_valid_until <= warning_date:
            # Laeuft bald ab
            days_remaining = (series.iv_valid_until - today).days
            results['expiring'] += 1
            _create_iv_task(
                series,
                f'IV-Verfuegung laeuft in {days_remaining} Tagen ab: '
                f'{series.patient.last_name} {series.patient.first_name}',
                f'Die IV-Verfuegung ({series.iv_decision_number or "ohne Nr."}) '
                f'laeuft am {series.iv_valid_until.strftime("%d.%m.%Y")} ab. '
                f'Bitte rechtzeitig Verlaengerung beantragen.',
                'medium'
            )
            results['tasks_created'] += 1

    db.session.commit()
    logger.info(f'IV-Monitoring: {results}')
    return results


def _create_iv_task(series, title, description, priority):
    """Erstellt eine Aufgabe fuer eine IV-Verfuegung, wenn nicht bereits vorhanden."""
    # Pruefen ob bereits eine offene Aufgabe existiert
    existing = Task.query.filter(
        Task.organization_id == series.patient.organization_id,
        Task.title.contains(f'IV-Verfuegung'),
        Task.title.contains(series.patient.last_name),
        Task.status.in_(['open', 'in_progress']),
    ).first()

    if existing:
        return  # Nicht doppelt erstellen

    task = Task(
        organization_id=series.patient.organization_id,
        title=title,
        description=description,
        priority=priority,
        status='open',
    )
    db.session.add(task)


def get_iv_status_summary(org_id):
    """Gibt eine Zusammenfassung aller IV-Serien zurueck."""
    today = date.today()

    total = TreatmentSeries.query.filter(
        TreatmentSeries.status == 'active',
        TreatmentSeries.insurance_type == 'IV',
    ).join(TreatmentSeries.patient).filter_by(
        organization_id=org_id
    ).count()

    with_expiry = TreatmentSeries.query.filter(
        TreatmentSeries.status == 'active',
        TreatmentSeries.insurance_type == 'IV',
        TreatmentSeries.iv_valid_until.isnot(None),
    ).join(TreatmentSeries.patient).filter_by(
        organization_id=org_id
    ).count()

    expired = TreatmentSeries.query.filter(
        TreatmentSeries.status == 'active',
        TreatmentSeries.insurance_type == 'IV',
        TreatmentSeries.iv_valid_until < today,
    ).join(TreatmentSeries.patient).filter_by(
        organization_id=org_id
    ).count()

    expiring_30d = TreatmentSeries.query.filter(
        TreatmentSeries.status == 'active',
        TreatmentSeries.insurance_type == 'IV',
        TreatmentSeries.iv_valid_until >= today,
        TreatmentSeries.iv_valid_until <= today + timedelta(days=30),
    ).join(TreatmentSeries.patient).filter_by(
        organization_id=org_id
    ).count()

    return {
        'total_active': total,
        'with_expiry_date': with_expiry,
        'expired': expired,
        'expiring_30d': expiring_30d,
    }
