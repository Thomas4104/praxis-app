# Cenplex vs. OMNIA - Konsolidierter Abgleich & Umbauplan

## Analysiert: 4611 C#-Dateien, 1700+ DTOs, 23 WCF-Services

---

## 1. PATIENTEN-MODUL

### Fehlend in OMNIA (muss hinzugefuegt werden):

**Versicherungs-Erweiterungen:**
- `costunit_uvg_id` (FK Contact) - UVG Kostentraeger
- `costunit_vvg_id` (FK Contact) - VVG/MVG Kostentraeger
- `insured_id_vvg` - Versichertennummer VVG
- `card_id_vvg` - Kartennummer VVG
- `card_vvg_expiry` - Karten-Ablauf VVG
- `is_kvg_base` (bool) - KVG Grundversicherung
- `kvg_model` (int) - HMO/PPO/Free
- `kvg_accident_coverage` (int) - Unfalldeckung ja/nein
- `insurance_extra_data` (JSON) - Zusatzdaten

**Premium-Zahler (Rechnungsempfaenger != Patient):**
- `premium_payer_firstname`, `premium_payer_lastname`
- `premium_payer_company`
- `premium_payer_address1`, `premium_payer_address2`
- `premium_payer_zipcode`, `premium_payer_town`
- `premium_payer_kanton`, `premium_payer_country`

**Externe System-IDs:**
- `egym_id`, `milon_id`, `vald_id`, `dividat_id`
- `mywellness_id`, `mywellness_device_type`

**Weitere fehlende Felder:**
- `preferred_communication` (int) - Bevorzugter Kanal
- `hobbies`, `profession` - Lebensstil
- `referenced_by_id` (FK Contact) - Zuweiser/Empfehlung
- `deposit_amount`, `deposit_payed_date`, `deposit_receipt_date`, `deposit_payed_back_date` - Kaution/Depot

---

## 2. BEHANDLUNGSPLAN-MODUL

### Fehlend in OMNIA:

**TreatmentPlan (eigenstaendige Entitaet, nicht nur Serie):**
- `hypothesis` - Arbeitshypothese
- `affected_side` (int) - 0=bilateral, 1=rechts, 2=links
- `finished_reason` - Abschlussgrund
- `icd_codes` (JSON) - ICD-10 Codes
- `diagnose_ids` (JSON)
- `finding_id` (FK Finding)
- `phase_template_id` (FK)
- `general_plantag_ids` (JSON)
- `flag_alerts` (JSON)

**Phasen-System (PhaseItem):**
- Neue Tabelle `treatment_phases`
- `title`, `position`, `default_duration`
- `start_date`, `end_date`, `finished_by_id`
- `check_states` (JSON)

**Befund/Finding (30 flexible Felder):**
- Neue Tabelle `findings`
- `finding_template_id` (FK)
- `problem`, `examination`, `marsman`
- `problem_positions` (JSON)
- `progress` (int)
- `info1` bis `info30` (string) - Template-basierte Felder
- `check_items` (JSON)
- `background_filekey`

**Finding-Templates:**
- Neue Tabelle `finding_templates`
- 30 Label/Position/Visibility-Konfigurationen
- Checkitem-Definitionen (JSON)

**Assessment-System:**
- Neue Tabelle `assessments`
- `assessment_type`, `assessment_template_id`
- `survey_template_id`, `execution_count`, `start_phase_id`
- Neue Tabelle `assessment_results`
- `text_value`, `sketch_value`, `calculated_value`

**Messwerte-System (erweitert):**
- `measurement_type` (int) - Kraft, ROM, Zeit, etc.
- `instrument` - Geraetename
- `manufacturer_id` (FK)
- `display_type`, `expected_min`, `expected_max`
- `measurement_values` - JSON Array mit Rohwerten pro Messung

**Therapieziele (hierarchisch):**
- `parent_id` (FK self) - Unterziele moeglich
- `due_date` - Zieldatum
- `finished` - Abschlussdatum
- Sub-Goal Completion Ratio berechnen

---

## 3. TERMIN/KALENDER-MODUL

### Fehlend in OMNIA:

**Termin-Erweiterungen:**
- `is_on_waitlist` (bool)
- `member_of_group_id` (FK) - Gruppentermin
- `is_remote` (bool) - Telemedizin
- `is_virtual` (bool)
- `is_mtt` (bool) - Medizinische Trainingstherapie
- `is_pauschal` (bool) + `pauschal_price` (decimal)
- `is_emr` (bool), `is_ergo` (bool)
- `cost_unit_id` (FK Contact) - Kostentraeger pro Termin
- `bill_state` (int) - Abrechnungsstatus
- `cancellation_date` - Absagedatum
- `additional_employees` (JSON) - Weitere Therapeuten
- `effort_notes` - Aufwandsnotizen
- `booking_messages` (JSON)
- `treatment4`, `treatment5` - Erweiterte SOAP-Felder
- `treatment_history` (JSON) - Behandlungsverlauf
- `sum_of_positions` (decimal) - Summe Tarifpositionen
- `uvg_positions`, `ergo_positions`, `emr_positions` (JSON)

**Online-Buchung:**
- `was_booked_online` (bool)
- `confirmed_by_patient` (bool)
- `booker_id`, `web_booker_id`
- `was_synced` (bool), `no_sync` (bool)
- `last_patient_action`, `last_patient_action_date`

**Benachrichtigungen:**
- `last_printed`, `last_mailed`, `last_sms_sent`
- `email_triggered` (bool)

**Warteliste:**
- Neues Feature: WaitList mit freien Slots finden
- `ManualStartTime` - Manuelle Zeiteingabe

**Automatische Terminplanung (Scheduling-Algorithmus):**
- `AppointmentFinder` mit Scoring:
  - `IntervalWeight = 1.0`
  - `TimeWeight = 0.5`
  - `WeekdayWeight = 1.4`
  - `WeekdaySwitchPenalty = 3.5`
  - `WeekdayDispersionMultiplier = 8.0`
  - `WeekdayCohesionBoost = 1.5`
- Optimale Terminverteilung berechnen

---

## 4. ABRECHNUNGS-MODUL

### Fehlend in OMNIA:

**Rechnungstypen (InvoiceType Enum - 14 Typen!):**
- 0: SerieInvoice (Therapie)
- 1: ProductInvoice (Produkt)
- 2: ProductCreditInvoice (Gutschrift)
- 3: PauschalInvoice (Pauschale)
- 4: PrivateInvoice (Privat)
- 5: CancelledAppointment
- 6: FitnessAbo
- 7: FitnessAboBreak
- 8: EmrInvoice
- 9: Voucher (Gutschein)
- 12: ErgoInvoice
- 13: AboProductInvoice
- 14: UvgInvoice

**Abrechnungsfaelle (BillingCase - 8 Typen!):**
- 0: Standard (KVG)
- 1: Suva (UVG)
- 2: Military (MVG)
- 3: Private
- 4: Hospital
- 5: Pension (IV)
- 6: VVG (Zusatzversicherung)
- 7: Pauschal

**Rechnungsposition-Erweiterungen:**
- `tarif_code` (string) - z.B. "001", "312", "590"
- `taxpoint` (string) - z.B. "001.0001"
- `taxpoint_value` (decimal) - CHF pro Taxpunkt
- `valuta_date` - fuer MwSt-Satz
- `is_credit` (bool)
- `remark` (string)
- Berechnung: `Betrag = UnitpriceNetto * Quantity * TaxpointValue`

**Zahlungen-Erweiterungen:**
- `payment_type` (int) - Bank=0, Cash=1, Card=2, Twint=3
- `reduction_reason` (int) - Skonto=1, Reduction=2, Rounding=3, Misc=4, Storno=5, PartlyStorno=6, Loss=7, Voucher=8
- `reference_number` - VESR-Referenz
- `is_fully_payed`, `payed_too_much`, `no_match_found`
- `is_from_file`, `is_inkasso`, `has_duplicate`

**Mahnwesen (3 Stufen):**
- Mahnung 1, 2, 3 mit eigenen Texten, Tagen, Gebuehren
- `reminder_text`, `reminder_fee`, `due_days`
- Original-Dokument als byte[]

**MediData-Integration:**
- `medidata_state` (0=pending, 1=picked up, 2=error)
- `transmission_reference`
- `medidata_responses` - Antworten von Versicherung
- `medidata_trackings` - Tracking-Eintraege
- `is_xml45` (bool)

**CAMT-Banking (Zahlungsimport):**
- CAMT02-08 XML-Parser
- VESR-Referenz-Parsing (26 Zeichen)
- Automatische Rechnungszuordnung

**Kostengutsprachen (erweitert):**
- `extension_of_id` (FK self) - Verlaengerung
- `verification_key`, `verification_key_valid_until`
- `request_id`
- `payload_type` (XML/JSON)
- MediData-Response-Tracking

---

## 5. MITARBEITER/HR-MODUL

### Fehlend in OMNIA:

**Mitarbeiter-Erweiterungen:**
- `degree` - Akademischer Grad
- `internal_number` - Personalnummer
- `asca_number` - ASCA-Nummer
- `temp_gln` - Temporaere GLN
- `medidata_client_id`
- `physiotec_id` (long)
- `booking_sync_from`, `booking_sync_till`
- `booking_book_active` (bool)
- `send_invoice_as_practice` (bool)
- `calendar_default_interval` (int)
- `app_settings` (JSON)
- `floor_plan` (byte[])

**Benutzerrechte-System (feingranular, JSON):**
```
UserRights:
  InvoiceRights: CanRead, CanEdit, CanSendInvoice, CanDeleteInvoice, CanCancelInvoice, CanDeletePayment, CanCloseInvoice
  GutspracheRights: CanRead, CanEdit
  PatientRights: CanRead, CanEdit
  EmployeeRights: CanRead, CanEdit, CanEditVacationAllotments, CanEditWorkSchedule, CanEditRoomPlan, OnlyPersonal, CanDeleteVacation, UseApp, CanChangeAppCalendar, CanEditUserGroups, CanAddVacation, CanEditVacationRequests, CanAccessVacationPlan
  StatisticRights: CanRead, CanEdit, AllowedCategories[]
  FitnessRights: CanRead, CanEdit, CanChangeAbo
  KpiRights: CanEdit, AllowedCategories[]
  + CalendarRights, ProductRights, ResourceRights, SettingRights, LicenseRights, DashboardRights, MailingRights, AddressRights, ArchiveRights, InvoiceValidationRights, PracticeRights
```

**Benutzergruppen:**
- Neue Tabelle `employee_groups`
- `title`, `description`, `user_rights` (JSON)
- Mitarbeiter koennen mehreren Gruppen angehoeren

**Urlaubsverwaltung (erweitert):**
- Urlaubsantraege mit Genehmigungsworkflow
- `VacationRequest`: `approved`, `declined`, `decline_reason`
- Urlaubs-Pensen pro Jahr/Template
- Ueberstunden-Tracking pro Monat
- 8 Abwesenheitstypen: Vacation, Training, Sick, Accident, Maternal, Military, Unpaid, Misc

**Arbeitsplaene:**
- `EmployeeWorkPlan`: `from_date`, `to_date`, `work_schedule` (JSON)
- Pro Wochentag definierbar
- Mehrere Plaene pro Mitarbeiter (zeitlich begrenzt)

---

## 6. KONTAKTE/ADRESSEN-MODUL

### Fehlend in OMNIA:

- `system_contact_type` - System-Kontakttyp
- `gln_receiver` - GLN Empfaenger
- `affiliate_id` - Affiliate-ID
- `law_code` - Fachgebiet
- `expertise` - Spezialisierung
- `supports_online` (bool)
- `accept_kostengutsprache` (bool)
- `email_gutsprache` - E-Mail fuer Kostengutsprachen
- `gutsprache_mails` (JSON)
- `tarif_code` (int)
- `reference_contact_id` (FK self) - Duplikat-Handling
- `addressing` - Anredeformel
- `logo` (byte[])
- `is_imported` (bool)

---

## 7. MAILING/SMS-MODUL

### Fehlend in OMNIA:

**E-Mail-System (komplett):**
- E-Mail-Konten-Verwaltung (EmailMapping)
- Inbox mit Ordnerverwaltung
- Entwuerfe
- Spam-Verwaltung
- Delivery/Open-Tracking (SendGrid)
- Bounce-Handling
- Auto-Responder (Abwesenheit)
- Patientenzuordnung von empfangenen E-Mails

**SMS-System:**
- SMS-Provider-Integration
- SMS-Templates (mehrsprachig)
- GSM-Zeichensatz-Validierung
- Termin-Erinnerungen per SMS
- SMS-Kosten-Tracking (Parts, Price)
- Delivery-Bestaetigung

**Template-System (mehrsprachig):**
- 4 Sprachen: DE, FR, IT, EN
- Template-Platzhalter:
  - %AppStart%, %AppEnd%, %AppZip%, %AppTown%, %AppStreet%
  - %AppResources%, %AppTherapistFirst%, %AppTherapistLast%
  - [PATIENT_FIRSTNAME], [PATIENT_LASTNAME], [APPOINTMENT_DATE]
- Template-Trigger (automatisch X Tage/Stunden vor Termin)
- Template pro Serienvorlage konfigurierbar

**Report/PDF-Generierung:**
- 20+ Report-Typen (Rechnung, Arztbericht, Terminkarte, etc.)
- Mehrsprachige Varianten (DE, FR, IT)
- HTML-basierte E-Mail-Templates

---

## 8. PRODUKTE/TARIFE

### Fehlend in OMNIA:

- `is_emr` (bool), `is_ergo` (bool)
- `ergo_taxpoint` (int) - Ergo-Tarifposition
- `default_bankaccount_id` (FK)
- `tags` (JSON) - Produkt-Tags/Kategorien
- `provider_id` (FK Contact) - Lieferant
- `location_info` - Standort-spezifisch

**Tarif-Katalog-System:**
- TaxPoint-Tabelle mit Gueltigkeitszeitraum
- Tarifcodes: "001" (Physio), "312" (Chiro), "313" (Kieferortho), "338" (Logopaedie), "590" (Diverses)
- TaxPointValue pro Kanton und Versicherungsverband
- Historische Versionierung

---

## 9. STATISTIKEN/KPIs

### Fehlend in OMNIA:

**Statistik-System:**
- 21 Filtertypen (Taxpunkt, Produkt, Standort, Therapeut, Versicherung, Datum, etc.)
- Speicherbare Statistik-Templates
- Kategorie-basierte Organisation

**KPI-Dashboard:**
- KPI-Boxen mit Diagrammen (Line, Bar, Pie, NumberBox)
- Grid-basiertes Layout (PositionX, PositionY, Width, Height)
- Fitness-KPIs (Besucher, Abos, Verkaeufe)
- Appointment-KPIs, Controlling, Sales

---

## 10. FITNESS/ABO-MODUL

### Fehlend in OMNIA (teilweise):

**Abo-System (erweitert):**
- `duration_type` (Day, Week, Month, Year, Visits)
- `payment_type` (Single, Monthly, Rates)
- `payment_rates` (int) - Anzahl Raten
- `price_break_penalty` (decimal) - Strafgebuehr
- `training_controls` (int) - Kontrollen pro Monat
- `start_time`, `end_time` - Gueltigkeitszeiten
- `contract_print_date`, `qualicert_print_date`
- `contract_received_date`
- `discount` (decimal)
- `message`, `message_valid_until`
- `stop_reminding` (bool)
- `no_sync_with_egym`, `no_sync_with_milon`, etc.

**Abo-Pausen:**
- Neue Tabelle `abo_breaks`
- `start_date`, `end_date`, `reason`, `price`

**Abo-Templates:**
- `price_once`, `price_month`, `price_rate`
- `price_batch_depot`

**Geraete-Integration:**
- EGYM, VALD, Dividat, MyWellness APIs
- Messdaten-Import
- Koerperregion-spezifische Daten

---

## 11. MESSAGING/MISSIONS

### Fehlend in OMNIA (teilweise):

**Mission/Todo-System (erweitert):**
- `force_response` (bool) - Antwort erzwingen
- `links` (JSON) - Verknuepfungen zu Entities
- `color` (int) - Farbkodierung
- `has_updates` (bool)
- `mission_notes` - Kommentare
- `mission_responses` - Antworten
- `mission_to_employees` - Mehrfachzuweisung
- `state` (MissionStatus Enum)

**RabbitMQ Real-Time Messaging:**
- Topic-basiert (z.B. EmailReceived, FitnessAbosChanged)
- Broadcast-Support
- Automatische Wiederverbindung

---

## 12. LEARNING/E-LEARNING

### Komplett fehlend in OMNIA:

- Trainings-Kurse mit Videos
- Video-Player mit Positionsspeicherung
- Notizen mit Timestamp (waehrend Video)
- Fortschritts-Tracking
- Multilingual (4 Sprachen)

---

## PRIORISIERTER UMBAUPLAN

### Phase 1: Datenmodell-Erweiterung (KRITISCH)
1. Patient: Versicherungsfelder, Premium-Zahler, externe IDs
2. Appointment: Warteliste, Online-Buchung, erweiterte SOAP-Felder
3. Invoice: 14 Typen, 8 BillingCases, MediData-Felder
4. InvoicePosition: Tarif-System (TaxPoint, TaxPointValue)
5. InvoicePayment: PaymentType, ReductionReason
6. Contact: Erweiterte Felder (GLN, Expertise, Kostengutsprache)
7. Employee: UserRights JSON, Benutzergruppen, erweiterte Felder

### Phase 2: Neue Tabellen
1. TreatmentPlan (eigenstaendig)
2. TreatmentPhase
3. Finding + FindingTemplate
4. Assessment + AssessmentResult
5. EmployeeGroup
6. VacationRequest
7. VacationAllotment + VacationAllotmentTemplate
8. OvertimeHistory
9. AboBreak
10. TaxPoint + TaxPointValue (Tarif-Katalog)

### Phase 3: Business-Logik
1. Billing: 14 Rechnungstypen + 8 BillingCases
2. Mahnwesen: 3-Stufen mit Texten/Gebuehren
3. Kostengutsprachen: Erweiterungsworkflow
4. Terminplanung: Scoring-Algorithmus
5. Warteliste
6. UserRights: Feingranulares Berechtigungssystem
7. Urlaubsantraege: Genehmigungsworkflow

### Phase 4: Templates & Reports
1. E-Mail-Template-System (4 Sprachen, Platzhalter)
2. SMS-Template-System
3. Finding-Templates (30 Felder)
4. Report-Generation (PDF)

### Phase 5: Integrationen
1. MediData-Schnittstelle
2. CAMT-Banking-Import
3. VESR-Parsing
4. Geraete-APIs (EGYM, VALD, Dividat)
