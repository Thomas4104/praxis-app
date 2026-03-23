"""KI-Tools fuer den Behandlungsplan-Bereich"""
import json
from datetime import datetime, date
from flask_login import current_user
from models import (db, TreatmentSeries, TreatmentSeriesTemplate, Appointment,
                    Patient, Employee, Doctor, TherapyGoal, Milestone,
                    Measurement, HealingPhase)


TREATMENT_TOOLS = [
    {
        'name': 'serien_auflisten',
        'description': 'Listet alle Behandlungsserien eines Patienten auf. Optional nach Status filterbar.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'patient_id': {'type': 'integer', 'description': 'ID des Patienten'},
                'status': {'type': 'string', 'description': 'Optionaler Statusfilter: active, completed, cancelled'}
            },
            'required': ['patient_id']
        }
    },
    {
        'name': 'serie_details',
        'description': 'Zeigt vollstaendige Details einer Behandlungsserie inkl. Termine, Ziele und Meilensteine.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'serie_id': {'type': 'integer', 'description': 'ID der Behandlungsserie'}
            },
            'required': ['serie_id']
        }
    },
    {
        'name': 'serie_erstellen',
        'description': 'Erstellt eine neue Behandlungsserie fuer einen Patienten.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'patient_id': {'type': 'integer', 'description': 'ID des Patienten'},
                'template_id': {'type': 'integer', 'description': 'ID der Serienvorlage'},
                'therapeut_id': {'type': 'integer', 'description': 'ID des Therapeuten'},
                'arzt_id': {'type': 'integer', 'description': 'ID des verordnenden Arztes'},
                'diagnose_code': {'type': 'string', 'description': 'ICD-10 Diagnosecode'},
                'diagnose_text': {'type': 'string', 'description': 'Diagnosetext'}
            },
            'required': ['patient_id', 'template_id', 'therapeut_id']
        }
    },
    {
        'name': 'serie_abschliessen',
        'description': 'Schliesst eine Behandlungsserie ab.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'serie_id': {'type': 'integer', 'description': 'ID der Behandlungsserie'}
            },
            'required': ['serie_id']
        }
    },
    {
        'name': 'behandlungsplan_anzeigen',
        'description': 'Zeigt den kompletten Behandlungsplan eines Patienten mit allen Serien, Zielen, Meilensteinen und Messungen.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'patient_id': {'type': 'integer', 'description': 'ID des Patienten'}
            },
            'required': ['patient_id']
        }
    },
    {
        'name': 'ziel_erstellen',
        'description': 'Erstellt ein neues Therapieziel fuer eine Behandlungsserie.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'serie_id': {'type': 'integer', 'description': 'ID der Behandlungsserie'},
                'beschreibung': {'type': 'string', 'description': 'Beschreibung des Therapieziels'},
                'zielwert': {'type': 'string', 'description': 'Zielwert (z.B. "NPRS <= 3")'}
            },
            'required': ['serie_id', 'beschreibung']
        }
    },
    {
        'name': 'ziel_aktualisieren',
        'description': 'Aktualisiert den Fortschritt eines Therapieziels.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'ziel_id': {'type': 'integer', 'description': 'ID des Therapieziels'},
                'aktueller_wert': {'type': 'string', 'description': 'Aktueller Wert'},
                'prozent': {'type': 'integer', 'description': 'Erreichungsgrad in Prozent (0-100)'}
            },
            'required': ['ziel_id']
        }
    },
    {
        'name': 'meilenstein_erstellen',
        'description': 'Erstellt einen neuen Meilenstein fuer eine Behandlungsserie.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'serie_id': {'type': 'integer', 'description': 'ID der Behandlungsserie'},
                'name': {'type': 'string', 'description': 'Name des Meilensteins'},
                'zieldatum': {'type': 'string', 'description': 'Zieldatum im Format YYYY-MM-DD'},
                'kriterien': {'type': 'string', 'description': 'Erreichungskriterien'}
            },
            'required': ['serie_id', 'name']
        }
    },
    {
        'name': 'messwert_erfassen',
        'description': 'Erfasst einen neuen Messwert fuer einen Patienten.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'patient_id': {'type': 'integer', 'description': 'ID des Patienten'},
                'typ': {'type': 'string', 'description': 'Messtyp: nprs, vas, odi, ndi, dash, custom'},
                'wert': {'type': 'number', 'description': 'Messwert'},
                'datum': {'type': 'string', 'description': 'Datum im Format YYYY-MM-DD (optional, Standard: heute)'}
            },
            'required': ['patient_id', 'typ', 'wert']
        }
    },
    {
        'name': 'messverlauf_anzeigen',
        'description': 'Zeigt alle Messwerte eines bestimmten Typs fuer einen Patienten ueber die Zeit.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'patient_id': {'type': 'integer', 'description': 'ID des Patienten'},
                'typ': {'type': 'string', 'description': 'Messtyp: nprs, vas, odi, ndi, dash, custom'}
            },
            'required': ['patient_id', 'typ']
        }
    },
    {
        'name': 'heilungsphase_setzen',
        'description': 'Aendert die aktuelle Heilungsphase einer Behandlungsserie.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'serie_id': {'type': 'integer', 'description': 'ID der Behandlungsserie'},
                'phase': {'type': 'string', 'description': 'Phase: initial, treatment, consolidation, autonomy'}
            },
            'required': ['serie_id', 'phase']
        }
    },
    {
        'name': 'soap_speichern',
        'description': 'Speichert SOAP-Notes fuer einen Termin.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'termin_id': {'type': 'integer', 'description': 'ID des Termins'},
                'subjektiv': {'type': 'string', 'description': 'Subjektive Beschwerden des Patienten'},
                'objektiv': {'type': 'string', 'description': 'Objektive Befunde des Therapeuten'},
                'assessment': {'type': 'string', 'description': 'Beurteilung'},
                'plan': {'type': 'string', 'description': 'Weiteres Vorgehen'}
            },
            'required': ['termin_id']
        }
    },
    {
        'name': 'templates_auflisten',
        'description': 'Listet alle verfuegbaren Serienvorlagen auf.',
        'input_schema': {
            'type': 'object',
            'properties': {},
            'required': []
        }
    }
]


def treatment_tool_executor(tool_name, tool_input):
    """Fuehrt die Behandlungsplan-Tools aus"""
    org_id = current_user.organization_id

    if tool_name == 'serien_auflisten':
        patient_id = tool_input['patient_id']
        patient = Patient.query.get(patient_id)
        if not patient or patient.organization_id != org_id:
            return {'error': 'Patient nicht gefunden.'}
        query = TreatmentSeries.query.filter_by(patient_id=patient_id)
        if tool_input.get('status'):
            query = query.filter_by(status=tool_input['status'])
        serien = query.order_by(TreatmentSeries.created_at.desc()).all()

        if not serien:
            return {'ergebnis': 'Keine Serien gefunden.', 'anzahl': 0}

        ergebnisse = []
        for s in serien:
            total = s.appointments.count()
            fertig = s.appointments.filter(Appointment.status == 'completed').count()
            ergebnisse.append({
                'id': s.id,
                'vorlage': s.template.name if s.template else '-',
                'therapeut': f'{s.therapist.user.first_name} {s.therapist.user.last_name}' if s.therapist and s.therapist.user else '-',
                'diagnose': f'{s.diagnosis_code} - {s.diagnosis_text}' if s.diagnosis_code else s.diagnosis_text or '-',
                'status': s.status,
                'fortschritt': f'{fertig}/{total} Termine',
                'erstellt': s.created_at.strftime('%d.%m.%Y') if s.created_at else '-'
            })

        return {'ergebnis': ergebnisse, 'anzahl': len(ergebnisse)}

    elif tool_name == 'serie_details':
        s = TreatmentSeries.query.get(tool_input['serie_id'])
        if not s or (s.patient and s.patient.organization_id != org_id):
            return {'error': 'Serie nicht gefunden.'}

        termine = []
        for t in s.appointments.order_by(Appointment.start_time).all():
            termine.append({
                'id': t.id,
                'datum': t.start_time.strftime('%d.%m.%Y %H:%M'),
                'status': t.status,
                'hat_soap': bool(t.soap_subjective or t.soap_objective)
            })

        ziele = []
        for z in s.goals.all():
            ziele.append({
                'beschreibung': z.description,
                'zielwert': z.target_value or '-',
                'aktueller_wert': z.current_value or '-',
                'erreichung': f'{z.achievement_percent}%',
                'status': z.status
            })

        meilensteine = []
        for m in s.milestones.order_by(Milestone.sort_order).all():
            meilensteine.append({
                'name': m.name,
                'zieldatum': m.target_date.strftime('%d.%m.%Y') if m.target_date else '-',
                'status': m.status
            })

        return {
            'ergebnis': {
                'id': s.id,
                'patient': f'{s.patient.first_name} {s.patient.last_name}' if s.patient else '-',
                'vorlage': s.template.name if s.template else '-',
                'therapeut': f'{s.therapist.user.first_name} {s.therapist.user.last_name}' if s.therapist and s.therapist.user else '-',
                'diagnose': f'{s.diagnosis_code} - {s.diagnosis_text}' if s.diagnosis_code else s.diagnosis_text or '-',
                'verordnung': s.prescription_date.strftime('%d.%m.%Y') if s.prescription_date else '-',
                'arzt': f'{s.prescribing_doctor.salutation} {s.prescribing_doctor.first_name} {s.prescribing_doctor.last_name}' if s.prescribing_doctor else '-',
                'versicherung': s.insurance_type,
                'abrechnungsmodell': s.billing_model,
                'status': s.status,
                'heilungsphase': s.healing_phase or '-',
                'termine': termine,
                'ziele': ziele,
                'meilensteine': meilensteine
            }
        }

    elif tool_name == 'serie_erstellen':
        template = TreatmentSeriesTemplate.query.get(tool_input['template_id'])
        if not template or template.organization_id != org_id:
            return {'error': 'Serienvorlage nicht gefunden.'}
        patient_check = Patient.query.get(tool_input['patient_id'])
        if not patient_check or patient_check.organization_id != org_id:
            return {'error': 'Patient nicht gefunden.'}

        serie = TreatmentSeries(
            patient_id=tool_input['patient_id'],
            template_id=tool_input['template_id'],
            therapist_id=tool_input['therapeut_id'],
            location_id=template.default_location_id,
            prescribing_doctor_id=tool_input.get('arzt_id'),
            diagnosis_code=tool_input.get('diagnose_code', ''),
            diagnosis_text=tool_input.get('diagnose_text', ''),
            prescription_date=date.today(),
            status='active',
            insurance_type='KVG',
            billing_model='tiers_garant'
        )
        db.session.add(serie)
        db.session.commit()

        return {'ergebnis': f'Neue Serie erstellt (ID: {serie.id})', 'serie_id': serie.id}

    elif tool_name == 'serie_abschliessen':
        s = TreatmentSeries.query.get(tool_input['serie_id'])
        if not s or (s.patient and s.patient.organization_id != org_id):
            return {'error': 'Serie nicht gefunden.'}
        s.status = 'completed'
        s.completed_at = datetime.utcnow()
        db.session.commit()
        return {'ergebnis': f'Serie {s.id} wurde abgeschlossen.'}

    elif tool_name == 'behandlungsplan_anzeigen':
        patient = Patient.query.get(tool_input['patient_id'])
        if not patient or patient.organization_id != org_id:
            return {'error': 'Patient nicht gefunden.'}

        serien = TreatmentSeries.query.filter_by(patient_id=patient.id).all()
        ziele = TherapyGoal.query.filter_by(patient_id=patient.id).all()
        meilensteine = Milestone.query.filter_by(patient_id=patient.id).order_by(Milestone.sort_order).all()

        return {
            'ergebnis': {
                'patient': f'{patient.first_name} {patient.last_name}',
                'serien': [{
                    'id': s.id,
                    'vorlage': s.template.name if s.template else '-',
                    'diagnose': f'{s.diagnosis_code} - {s.diagnosis_text}' if s.diagnosis_code else '-',
                    'status': s.status,
                    'heilungsphase': s.healing_phase or '-'
                } for s in serien],
                'therapieziele': [{
                    'beschreibung': z.description,
                    'erreichung': f'{z.achievement_percent}%',
                    'status': z.status
                } for z in ziele],
                'meilensteine': [{
                    'name': m.name,
                    'status': m.status,
                    'zieldatum': m.target_date.strftime('%d.%m.%Y') if m.target_date else '-'
                } for m in meilensteine]
            }
        }

    elif tool_name == 'ziel_erstellen':
        serie = TreatmentSeries.query.get(tool_input['serie_id'])
        if not serie or (serie.patient and serie.patient.organization_id != org_id):
            return {'error': 'Serie nicht gefunden.'}

        ziel = TherapyGoal(
            series_id=serie.id,
            patient_id=serie.patient_id,
            description=tool_input['beschreibung'],
            target_value=tool_input.get('zielwert', ''),
            status='open'
        )
        db.session.add(ziel)
        db.session.commit()
        return {'ergebnis': f'Therapieziel erstellt: {ziel.description}', 'ziel_id': ziel.id}

    elif tool_name == 'ziel_aktualisieren':
        ziel = TherapyGoal.query.get(tool_input['ziel_id'])
        if not ziel or (ziel.patient and ziel.patient.organization_id != org_id):
            return {'error': 'Therapieziel nicht gefunden.'}

        if 'aktueller_wert' in tool_input:
            ziel.current_value = tool_input['aktueller_wert']
        if 'prozent' in tool_input:
            ziel.achievement_percent = tool_input['prozent']
            if tool_input['prozent'] >= 100:
                ziel.status = 'achieved'
            elif tool_input['prozent'] > 0:
                ziel.status = 'in_progress'

        db.session.commit()
        return {'ergebnis': f'Ziel aktualisiert: {ziel.description} ({ziel.achievement_percent}%)'}

    elif tool_name == 'meilenstein_erstellen':
        serie = TreatmentSeries.query.get(tool_input['serie_id'])
        if not serie or (serie.patient and serie.patient.organization_id != org_id):
            return {'error': 'Serie nicht gefunden.'}

        m = Milestone(
            series_id=serie.id,
            patient_id=serie.patient_id,
            name=tool_input['name'],
            target_date=datetime.strptime(tool_input['zieldatum'], '%Y-%m-%d').date() if tool_input.get('zieldatum') else None,
            criteria=tool_input.get('kriterien', ''),
            status='open',
            sort_order=Milestone.query.filter_by(series_id=serie.id).count()
        )
        db.session.add(m)
        db.session.commit()
        return {'ergebnis': f'Meilenstein erstellt: {m.name}', 'meilenstein_id': m.id}

    elif tool_name == 'messwert_erfassen':
        patient = Patient.query.get(tool_input['patient_id'])
        if not patient or patient.organization_id != org_id:
            return {'error': 'Patient nicht gefunden.'}

        typ = tool_input['typ']
        wert = tool_input['wert']
        datum_str = tool_input.get('datum')
        gemessen_am = datetime.strptime(datum_str, '%Y-%m-%d') if datum_str else datetime.utcnow()

        typ_namen = {
            'nprs': 'NPRS (Schmerzskala)',
            'vas': 'VAS (Visuelle Analogskala)',
            'odi': 'ODI (Oswestry)',
            'ndi': 'NDI (Neck Disability)',
            'dash': 'DASH'
        }

        m = Measurement(
            patient_id=patient.id,
            measurement_type=typ,
            name=typ_namen.get(typ, typ),
            value_json=json.dumps({'value': wert}),
            measured_at=gemessen_am
        )
        db.session.add(m)
        db.session.commit()
        return {'ergebnis': f'Messwert erfasst: {typ.upper()} = {wert}', 'messung_id': m.id}

    elif tool_name == 'messverlauf_anzeigen':
        patient_check = Patient.query.get(tool_input['patient_id'])
        if not patient_check or patient_check.organization_id != org_id:
            return {'error': 'Patient nicht gefunden.'}
        messungen = Measurement.query.filter_by(
            patient_id=tool_input['patient_id'],
            measurement_type=tool_input['typ']
        ).order_by(Measurement.measured_at).all()

        if not messungen:
            return {'ergebnis': 'Keine Messungen gefunden.', 'anzahl': 0}

        verlauf = []
        for m in messungen:
            werte = json.loads(m.value_json) if m.value_json else {}
            verlauf.append({
                'datum': m.measured_at.strftime('%d.%m.%Y'),
                'wert': werte.get('value', werte),
                'notizen': m.notes or ''
            })

        return {'ergebnis': verlauf, 'anzahl': len(verlauf), 'typ': tool_input['typ'].upper()}

    elif tool_name == 'heilungsphase_setzen':
        serie = TreatmentSeries.query.get(tool_input['serie_id'])
        if not serie or (serie.patient and serie.patient.organization_id != org_id):
            return {'error': 'Serie nicht gefunden.'}

        phase = tool_input['phase']
        phasen_namen = {
            'initial': 'Initialphase',
            'treatment': 'Behandlungsphase',
            'consolidation': 'Konsolidierungsphase',
            'autonomy': 'Autonomiephase'
        }

        # Bestehende aktive Phase abschliessen
        aktive = HealingPhase.query.filter_by(series_id=serie.id, end_date=None).all()
        for p in aktive:
            p.end_date = date.today()

        neue_phase = HealingPhase(
            series_id=serie.id,
            phase_type=phase,
            start_date=date.today()
        )
        db.session.add(neue_phase)
        serie.healing_phase = phase
        db.session.commit()

        return {'ergebnis': f'Heilungsphase geaendert auf: {phasen_namen.get(phase, phase)}'}

    elif tool_name == 'soap_speichern':
        t = Appointment.query.get(tool_input['termin_id'])
        if not t or (t.patient and t.patient.organization_id != org_id):
            return {'error': 'Termin nicht gefunden.'}

        if 'subjektiv' in tool_input:
            t.soap_subjective = tool_input['subjektiv']
        if 'objektiv' in tool_input:
            t.soap_objective = tool_input['objektiv']
        if 'assessment' in tool_input:
            t.soap_assessment = tool_input['assessment']
        if 'plan' in tool_input:
            t.soap_plan = tool_input['plan']

        db.session.commit()
        return {'ergebnis': f'SOAP-Notes fuer Termin {t.id} gespeichert.'}

    elif tool_name == 'templates_auflisten':
        templates = TreatmentSeriesTemplate.query.filter_by(
            organization_id=org_id, is_active=True).all()

        if not templates:
            return {'ergebnis': 'Keine Vorlagen gefunden.', 'anzahl': 0}

        ergebnisse = [{
            'id': t.id,
            'name': t.name,
            'kurzname': t.short_name or '-',
            'tarif': t.tariff_type or '-',
            'anzahl_termine': t.num_appointments,
            'dauer_minuten': t.duration_minutes,
            'min_intervall_tage': t.min_interval_days
        } for t in templates]

        return {'ergebnis': ergebnisse, 'anzahl': len(ergebnisse)}

    return {'error': f'Unbekanntes Tool: {tool_name}'}
