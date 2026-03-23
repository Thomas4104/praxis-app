"""Automatische Aufgaben-Erkennung und -Generierung"""
from datetime import datetime, date, timedelta
from models import (db, Task, Patient, TreatmentSeries, Invoice, CostApproval,
                    Appointment, InsuranceProvider)


class TaskGenerator:
    """Prueft auf fehlende Daten und erstellt/entfernt automatische Aufgaben"""

    def __init__(self, organization_id):
        self.organization_id = organization_id

    def run(self):
        """Fuehrt alle Pruefungen durch und gibt (erstellt, entfernt) zurueck"""
        created = 0
        removed = 0

        created += self._check_missing_insurance()
        created += self._check_missing_prescription()
        created += self._check_missing_doctor()
        created += self._check_expiring_approvals()
        created += self._check_overdue_invoices()
        created += self._check_completed_series_not_billed()

        removed += self._remove_resolved_tasks()

        return created, removed

    def _task_exists(self, task_type, related_id, id_field='related_patient_id'):
        """Prueft ob eine automatische Aufgabe bereits existiert"""
        query = Task.query.filter_by(
            organization_id=self.organization_id,
            task_type=task_type,
            auto_generated=True,
            status='open'
        )
        if id_field == 'related_patient_id':
            query = query.filter_by(related_patient_id=related_id)
        elif id_field == 'related_series_id':
            query = query.filter_by(related_series_id=related_id)
        elif id_field == 'related_invoice_id':
            query = query.filter_by(related_invoice_id=related_id)
        return query.first() is not None

    def _create_task(self, title, description, category, priority, task_type,
                     patient_id=None, series_id=None, invoice_id=None):
        """Erstellt eine automatische Aufgabe"""
        task = Task(
            organization_id=self.organization_id,
            title=title,
            description=description,
            category=category,
            priority=priority,
            task_type=task_type,
            status='open',
            auto_generated=True,
            related_patient_id=patient_id,
            related_series_id=series_id,
            related_invoice_id=invoice_id
        )
        db.session.add(task)
        db.session.commit()
        return 1

    def _check_missing_insurance(self):
        """Patienten mit aktiver Serie aber fehlender Versicherung"""
        created = 0
        # Aktive Serien ohne Versicherungsdaten beim Patienten
        serien = TreatmentSeries.query.filter_by(status='active').all()
        for serie in serien:
            patient = Patient.query.get(serie.patient_id)
            if not patient:
                continue
            if patient.organization_id != self.organization_id:
                continue
            if not patient.insurance_provider_id and not patient.insurance_number:
                if not self._task_exists('missing_insurance', patient.id):
                    created += self._create_task(
                        title=f'Fehlende Versicherungsdaten: {patient.first_name} {patient.last_name}',
                        description=f'Patient {patient.patient_number} hat eine aktive Behandlungsserie aber keine Versicherungsdaten.',
                        category='versicherung',
                        priority='high',
                        task_type='missing_insurance',
                        patient_id=patient.id,
                        series_id=serie.id
                    )
        return created

    def _check_missing_prescription(self):
        """Serien ohne Verordnung"""
        created = 0
        serien = TreatmentSeries.query.filter_by(status='active').all()
        for serie in serien:
            patient = Patient.query.get(serie.patient_id)
            if not patient or patient.organization_id != self.organization_id:
                continue
            if not serie.prescription_date and not serie.prescription_document_path:
                if not self._task_exists('missing_prescription', serie.id, 'related_series_id'):
                    created += self._create_task(
                        title=f'Fehlende Verordnung: {patient.first_name} {patient.last_name}',
                        description=f'Behandlungsserie (Diagnose: {serie.diagnosis_text or serie.diagnosis_code or "unbekannt"}) hat keine Verordnung.',
                        category='verordnung',
                        priority='high',
                        task_type='missing_prescription',
                        patient_id=patient.id,
                        series_id=serie.id
                    )
        return created

    def _check_missing_doctor(self):
        """Serien ohne zuweisenden Arzt"""
        created = 0
        serien = TreatmentSeries.query.filter_by(status='active').all()
        for serie in serien:
            patient = Patient.query.get(serie.patient_id)
            if not patient or patient.organization_id != self.organization_id:
                continue
            if not serie.prescribing_doctor_id:
                if not self._task_exists('missing_doctor', serie.id, 'related_series_id'):
                    created += self._create_task(
                        title=f'Fehlende Arzt-Zuweisung: {patient.first_name} {patient.last_name}',
                        description=f'Behandlungsserie hat keinen zuweisenden Arzt.',
                        category='arzt',
                        priority='normal',
                        task_type='missing_doctor',
                        patient_id=patient.id,
                        series_id=serie.id
                    )
        return created

    def _check_expiring_approvals(self):
        """Gutsprachen die in weniger als 30 Tagen ablaufen"""
        created = 0
        threshold = date.today() + timedelta(days=30)
        approvals = CostApproval.query.filter(
            CostApproval.organization_id == self.organization_id,
            CostApproval.status.in_(['approved', 'partially_approved']),
            CostApproval.valid_until.isnot(None),
            CostApproval.valid_until <= threshold,
            CostApproval.valid_until >= date.today()
        ).all()

        for gs in approvals:
            if not self._task_exists('expiring_approval', gs.patient_id):
                patient_name = f'{gs.patient.first_name} {gs.patient.last_name}' if gs.patient else 'Unbekannt'
                created += self._create_task(
                    title=f'Ablaufende Gutsprache: {patient_name}',
                    description=f'Gutsprache {gs.approval_number} läuft am {gs.valid_until.strftime("%d.%m.%Y")} ab.',
                    category='gutsprache',
                    priority='high',
                    task_type='expiring_approval',
                    patient_id=gs.patient_id,
                    series_id=gs.series_id
                )
        return created

    def _check_overdue_invoices(self):
        """Ueberfaellige Rechnungen"""
        created = 0
        invoices = Invoice.query.filter(
            Invoice.organization_id == self.organization_id,
            Invoice.status.in_(['sent', 'overdue']),
            Invoice.due_date.isnot(None),
            Invoice.due_date < date.today()
        ).all()

        for inv in invoices:
            if not self._task_exists('overdue_invoice', inv.id, 'related_invoice_id'):
                patient_name = f'{inv.patient.first_name} {inv.patient.last_name}' if inv.patient else 'Unbekannt'
                created += self._create_task(
                    title=f'Überfällige Rechnung: {inv.invoice_number}',
                    description=f'Rechnung {inv.invoice_number} ({patient_name}) ist seit {inv.due_date.strftime("%d.%m.%Y")} überfällig. Betrag: CHF {inv.amount_open:.2f}.',
                    category='abrechnung',
                    priority='high',
                    task_type='overdue_invoice',
                    patient_id=inv.patient_id,
                    invoice_id=inv.id
                )
        return created

    def _check_completed_series_not_billed(self):
        """Abgeschlossene Serien ohne Rechnung"""
        created = 0
        serien = TreatmentSeries.query.filter_by(status='completed').all()
        for serie in serien:
            patient = Patient.query.get(serie.patient_id)
            if not patient or patient.organization_id != self.organization_id:
                continue
            # Alle Termine abgeschlossen?
            all_appointments = serie.appointments.all()
            if not all_appointments:
                continue
            completed_count = sum(1 for a in all_appointments if a.status == 'completed')
            if completed_count == 0:
                continue
            # Hat die Serie eine Rechnung?
            has_invoice = serie.invoices.first() is not None
            if not has_invoice:
                if not self._task_exists('series_not_billed', serie.id, 'related_series_id'):
                    created += self._create_task(
                        title=f'Serie nicht abgerechnet: {patient.first_name} {patient.last_name}',
                        description=f'Abgeschlossene Behandlungsserie ({serie.diagnosis_text or serie.diagnosis_code}) wurde noch nicht abgerechnet.',
                        category='abrechnung',
                        priority='normal',
                        task_type='series_not_billed',
                        patient_id=patient.id,
                        series_id=serie.id
                    )
        return created

    def _remove_resolved_tasks(self):
        """Entfernt automatische Aufgaben deren Problem behoben wurde"""
        removed = 0

        auto_tasks = Task.query.filter_by(
            organization_id=self.organization_id,
            auto_generated=True,
            status='open'
        ).all()

        for task in auto_tasks:
            should_remove = False

            if task.task_type == 'missing_insurance' and task.related_patient_id:
                patient = Patient.query.get(task.related_patient_id)
                if patient and (patient.insurance_provider_id or patient.insurance_number):
                    should_remove = True

            elif task.task_type == 'missing_prescription' and task.related_series_id:
                serie = TreatmentSeries.query.get(task.related_series_id)
                if serie and (serie.prescription_date or serie.prescription_document_path):
                    should_remove = True
                if serie and serie.status != 'active':
                    should_remove = True

            elif task.task_type == 'missing_doctor' and task.related_series_id:
                serie = TreatmentSeries.query.get(task.related_series_id)
                if serie and serie.prescribing_doctor_id:
                    should_remove = True
                if serie and serie.status != 'active':
                    should_remove = True

            elif task.task_type == 'expiring_approval':
                # Pruefe ob Gutsprache abgelaufen oder erneuert
                approvals = CostApproval.query.filter_by(
                    patient_id=task.related_patient_id,
                    status='approved'
                ).filter(
                    db.or_(
                        CostApproval.valid_until.is_(None),
                        CostApproval.valid_until > date.today() + timedelta(days=30)
                    )
                ).first()
                if approvals:
                    should_remove = True

            elif task.task_type == 'series_not_billed' and task.related_series_id:
                serie = TreatmentSeries.query.get(task.related_series_id)
                if serie and serie.invoices.first() is not None:
                    should_remove = True

            if should_remove:
                task.status = 'completed'
                task.completed_at = datetime.utcnow()
                removed += 1

        db.session.commit()
        return removed
