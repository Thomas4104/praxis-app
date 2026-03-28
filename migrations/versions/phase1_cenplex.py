"""Phase1: Cenplex Datenmodell-Angleichung

Revision ID: phase1_cenplex
Revises: a48b228f0eec
Create Date: 2026-03-28

Fuegt fehlende Felder und neue Tabellen hinzu fuer Cenplex-Paritaet.
Nur ADD COLUMN und CREATE TABLE - keine destruktiven Aenderungen.
"""
from alembic import op
import sqlalchemy as sa

revision = 'phase1_cenplex'
down_revision = 'a48b228f0eec'
branch_labels = None
depends_on = None


def col_exists(table, column):
    """Prueft ob eine Spalte bereits existiert (SQLite-kompatibel)"""
    from alembic import context
    conn = op.get_bind()
    result = conn.execute(sa.text(f"PRAGMA table_info({table})"))
    columns = [row[1] for row in result]
    return column in columns


def table_exists(table_name):
    """Prueft ob eine Tabelle bereits existiert"""
    conn = op.get_bind()
    result = conn.execute(sa.text(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'"))
    return result.fetchone() is not None


def safe_add_column(table, column_name, column_type, **kwargs):
    """Fuegt Spalte nur hinzu wenn sie nicht existiert"""
    if not col_exists(table, column_name):
        op.add_column(table, sa.Column(column_name, column_type, **kwargs))


def upgrade():
    # ============================================================
    # PATIENT - Fehlende Felder
    # ============================================================
    patient_cols = [
        ('phone_office', sa.String(30)),
        ('special_notes', sa.Text()),
        ('is_special', sa.Boolean()),
        ('addressing', sa.String(200)),
        ('picture_path', sa.String(500)),
        ('insured_id', sa.String(30)),
        ('costunit_id', sa.Integer()),
        ('medical_service_coverage_restriction', sa.Integer()),
        ('milon_id', sa.String(50)),
        ('mywellness_device_type', sa.String(50)),
        ('sportsclub_id', sa.Integer()),
        ('send_copy_via', sa.Integer()),
        ('send_copy_after', sa.Integer()),
        ('blocked_mail_templates_json', sa.Text()),
        ('blocked_sms_templates_json', sa.Text()),
        ('verification_key', sa.String(100)),
        ('verification_key_valid_until', sa.DateTime()),
        ('batch_id', sa.String(50)),
        ('batch_activation_date', sa.Date()),
        ('batch_deactivation_date', sa.Date()),
        ('health_questionnaire_date', sa.Date()),
        ('premium_payer_email', sa.String(200)),
    ]
    for col_name, col_type in patient_cols:
        safe_add_column('patients', col_name, col_type)

    # ============================================================
    # EMPLOYEE - Fehlende Felder
    # ============================================================
    employee_cols = [
        ('salutation', sa.Integer()),
        ('sex', sa.Integer()),
        ('birthday', sa.Date()),
        ('street', sa.String(300)),
        ('zipcode', sa.String(10)),
        ('town', sa.String(100)),
        ('kanton', sa.String(5)),
        ('country', sa.String(5)),
        ('phone_private', sa.String(30)),
        ('phone_office', sa.String(30)),
        ('mobile', sa.String(30)),
        ('email', sa.String(200)),
        ('private_email', sa.String(200)),
        ('contract_type', sa.Integer()),
        ('active_from', sa.Date()),
        ('physiotec_id', sa.BigInteger()),
        ('medidata_client_id', sa.String(50)),
        ('picture_path', sa.String(500)),
        ('floorplan_path', sa.String(500)),
        ('must_change_password', sa.Boolean()),
        ('last_version_info', sa.String(100)),
    ]
    for col_name, col_type in employee_cols:
        safe_add_column('employees', col_name, col_type)

    # ============================================================
    # ORGANIZATION - Fehlende Felder
    # ============================================================
    org_cols = [
        ('suva_number', sa.String(50)),
        ('tax_number', sa.String(50)),
        ('medidata_client_id', sa.String(50)),
        ('temp_gln', sa.String(20)),
        ('gln_retired', sa.String(20)),
        ('ergo_zsr', sa.String(20)),
        ('department', sa.String(200)),
        ('postbox', sa.String(100)),
        ('kanton', sa.String(5)),
        ('fax', sa.String(30)),
        ('mobile', sa.String(30)),
        ('insurance_union', sa.Integer()),
        ('payment_due_days', sa.Integer()),
        ('invoice_buffer_time', sa.Integer()),
        ('cancellation_fee', sa.Numeric(10, 2)),
        ('cancelled_appointment_label', sa.String(200)),
        ('print_language', sa.Integer()),
        ('default_template_id', sa.Integer()),
        ('taxpoint_overwrite_json', sa.Text()),
        ('ofac_id', sa.Integer()),
        ('offline_password', sa.String(100)),
        ('reminder_text_1', sa.Text()),
        ('reminder_text_2', sa.Text()),
        ('reminder_text_3', sa.Text()),
        ('reminder_labels', sa.String(500)),
        ('reminder_days_1', sa.Integer()),
        ('reminder_days_2', sa.Integer()),
        ('reminder_days_3', sa.Integer()),
        ('reminder_fee_1', sa.Numeric(10, 2)),
        ('reminder_fee_2', sa.Numeric(10, 2)),
        ('reminder_fee_3', sa.Numeric(10, 2)),
    ]
    for col_name, col_type in org_cols:
        safe_add_column('organizations', col_name, col_type)

    # ============================================================
    # LOCATION - Fehlende Felder
    # ============================================================
    loc_cols = [
        ('gln_number', sa.String(20)),
        ('zsr_number', sa.String(20)),
        ('loc_kanton', sa.String(5)),
        ('loc_fax', sa.String(30)),
    ]
    for col_name, col_type in loc_cols:
        safe_add_column('locations', col_name, col_type)

    # ============================================================
    # CONTACT - Fehlende Felder
    # ============================================================
    contact_cols = [
        ('contact_type', sa.Integer()),
        ('system_contact_type', sa.Integer()),
        ('salutation', sa.Integer()),
        ('birthday', sa.Date()),
        ('sex', sa.Integer()),
        ('contact_mobile', sa.String(30)),
        ('fax', sa.String(30)),
        ('homepage', sa.String(300)),
        ('gln', sa.String(20)),
        ('zsr', sa.String(20)),
        ('description_text', sa.Text()),
        ('logo_path', sa.String(500)),
        ('gutsprache_mails', sa.Text()),
        ('is_deleted', sa.Boolean()),
        ('contact_kanton', sa.String(5)),
        ('contact_country', sa.String(5)),
    ]
    for col_name, col_type in contact_cols:
        safe_add_column('contacts', col_name, col_type)

    # ============================================================
    # TREATMENT_SERIES - Fehlende Felder
    # ============================================================
    series_cols = [
        ('title', sa.String(300)),
        ('accident_date', sa.Date()),
        ('is_emr_series', sa.Boolean()),
        ('is_group_series', sa.Boolean()),
        ('is_ergo_series', sa.Boolean()),
        ('case_date', sa.Date()),
        ('case_id', sa.String(50)),
        ('reason', sa.Integer()),
        ('cost_unit_id', sa.Integer()),
        ('use_credit', sa.Boolean()),
        ('towel_number', sa.Integer()),
        ('towel_info', sa.Text()),
        ('treatment_category_id', sa.Integer()),
        ('series_treatment_plan_id', sa.Integer()),
        ('treatment_history_template_id', sa.Integer()),
        ('doctor_report_id', sa.Integer()),
        ('series_finding_id', sa.Integer()),
        ('planning_info_json', sa.Text()),
    ]
    for col_name, col_type in series_cols:
        safe_add_column('treatment_series', col_name, col_type)

    # ============================================================
    # TREATMENT_SERIES_TEMPLATES - Fehlende Felder
    # ============================================================
    template_cols = [
        ('mtt_duration', sa.Integer()),
        ('is_pauschal', sa.Boolean()),
        ('is_remote', sa.Boolean()),
        ('allow_virtual_appointments', sa.Boolean()),
        ('position', sa.Integer()),
        ('is_group_series', sa.Boolean()),
        ('intermediate_bill_duration', sa.Integer()),
        ('bill_end_of_month', sa.Boolean()),
        ('apply_vat', sa.Boolean()),
        ('include_vat', sa.Boolean()),
        ('no_overbooking', sa.Boolean()),
        ('is_emr_series', sa.Boolean()),
        ('is_ergo', sa.Boolean()),
        ('treatment_history_template_id', sa.Integer()),
        ('tarif', sa.Integer()),
        ('therapist_role', sa.Integer()),
        ('cancel_fee', sa.Numeric(10, 2)),
        ('buffer_days', sa.Integer()),
        ('fixed_location_id', sa.Integer()),
        ('use_appointment_therapist', sa.Boolean()),
        ('selected_employees_json', sa.Text()),
        ('appointment_flags', sa.Integer()),
        ('validate_taxpoints', sa.Boolean()),
        ('product_tags', sa.String(500)),
        ('user_groups_json', sa.Text()),
        ('send_kogu_only', sa.Boolean()),
        ('allow_blanko_kogu', sa.Boolean()),
        ('bank_account_id', sa.Integer()),
        ('finding_template_id', sa.Integer()),
        ('is_default', sa.Boolean()),
        ('is_deleted', sa.Boolean()),
    ]
    for col_name, col_type in template_cols:
        safe_add_column('treatment_series_templates', col_name, col_type)

    # ============================================================
    # INVOICE - Fehlende Felder
    # ============================================================
    invoice_cols = [
        ('is_tiers_payant', sa.Boolean()),
        ('is_sent_by_employee', sa.Boolean()),
        ('contact_id', sa.Integer()),
        ('abo_id', sa.Integer()),
        ('tarif', sa.Integer()),
        ('inv_reason', sa.Integer()),
        ('therapist_role', sa.Integer()),
        ('reminder_stop', sa.Date()),
        ('is_inkasso', sa.Boolean()),
        ('is_voucher', sa.Boolean()),
        ('voucher_code', sa.String(50)),
        ('credit_amount', sa.Numeric(10, 2)),
        ('credit_receiver_id', sa.Integer()),
        ('internal_comment', sa.Text()),
        ('appointments_json', sa.Text()),
        ('invoice_document_path', sa.String(500)),
        ('file_key', sa.String(200)),
        ('inv_send_copy_via', sa.Integer()),
        ('inv_send_copy_after', sa.Integer()),
        ('copy_sent_date', sa.DateTime()),
        ('copy_sent_via', sa.Integer()),
        ('print_patient_copy', sa.Boolean()),
        ('send_bpost', sa.Boolean()),
        ('receiver_email', sa.String(200)),
        ('inv_verification_key', sa.String(100)),
        ('inv_verification_key_valid_until', sa.DateTime()),
        ('md_id', sa.Integer()),
    ]
    for col_name, col_type in invoice_cols:
        safe_add_column('invoices', col_name, col_type)

    # ============================================================
    # RESOURCE - Fehlende Felder
    # ============================================================
    resource_cols = [
        ('is_shared', sa.Boolean()),
        ('blocked_timeschedule_json', sa.Text()),
        ('blocked_timeschedule_valid_until', sa.Date()),
        ('picture_path', sa.String(500)),
    ]
    for col_name, col_type in resource_cols:
        safe_add_column('resources', col_name, col_type)

    # ============================================================
    # PRODUCT - Fehlende Felder
    # ============================================================
    product_cols = [
        ('order_number', sa.String(50)),
        ('provider_id', sa.Integer()),
        ('mige_number', sa.String(50)),
        ('product_tarif', sa.String(20)),
        ('is_ergo', sa.Boolean()),
        ('ergo_taxpoint', sa.Integer()),
        ('is_emr', sa.Boolean()),
        ('default_bank_account_id', sa.Integer()),
        ('tags', sa.String(500)),
        ('logo_path', sa.String(500)),
    ]
    for col_name, col_type in product_cols:
        safe_add_column('products', col_name, col_type)

    # ============================================================
    # BANK_ACCOUNT - Fehlende Felder
    # ============================================================
    bank_cols = [
        ('account_type', sa.Integer()),
        ('participant_number', sa.String(30)),
        ('employee_id', sa.Integer()),
        ('bank_contact_id', sa.Integer()),
        ('is_default_or_master', sa.Boolean()),
        ('display_name', sa.String(200)),
        ('display_street', sa.String(300)),
        ('display_zip', sa.String(10)),
        ('display_town', sa.String(100)),
        ('is_deleted', sa.Boolean()),
    ]
    for col_name, col_type in bank_cols:
        safe_add_column('bank_accounts', col_name, col_type)

    # ============================================================
    # INSURANCE_PROVIDER - Fehlende Felder
    # ============================================================
    ins_cols = [
        ('ins_department', sa.String(200)),
        ('ins_postbox', sa.String(100)),
        ('ins_kanton', sa.String(5)),
        ('website', sa.String(300)),
        ('recipient_gln', sa.String(20)),
        ('bag_number', sa.String(20)),
        ('law_code', sa.String(20)),
        ('xml_name', sa.String(200)),
        ('tarif_code', sa.Integer()),
        ('change_billing_type_desc', sa.Boolean()),
        ('accept_kostengutsprache', sa.Boolean()),
        ('email_gutsprache', sa.String(200)),
        ('gutsprache_mails', sa.Text()),
        ('is_deleted', sa.Boolean()),
    ]
    for col_name, col_type in ins_cols:
        safe_add_column('insurance_providers', col_name, col_type)

    # ============================================================
    # COST_APPROVAL - Fehlende Felder
    # ============================================================
    ca_cols = [
        ('cost_unit_id', sa.Integer()),
        ('treatment_title', sa.String(300)),
        ('measures', sa.Text()),
        ('treatment_reason', sa.Integer()),
        ('tarif', sa.Integer()),
        ('kogu_type', sa.Integer()),
        ('ca_billing_case', sa.Integer()),
        ('ca_receiver_email', sa.String(200)),
        ('use_appointments', sa.Boolean()),
        ('attach_kogu_only', sa.Boolean()),
    ]
    for col_name, col_type in ca_cols:
        safe_add_column('cost_approvals', col_name, col_type)

    # ============================================================
    # NEUE TABELLEN
    # ============================================================

    if not table_exists('treatment_categories'):
        op.create_table('treatment_categories',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
            sa.Column('name', sa.String(200), nullable=False),
            sa.Column('short_name', sa.String(20)),
            sa.Column('template_id', sa.Integer()),
            sa.Column('is_active', sa.Boolean(), default=True),
            sa.Column('is_deleted', sa.Boolean(), default=False),
            sa.Column('sort_order', sa.Integer(), default=0),
            sa.Column('created_at', sa.DateTime()),
        )

    if not table_exists('treatment_sites'):
        op.create_table('treatment_sites',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
            sa.Column('name', sa.String(200), nullable=False),
            sa.Column('address', sa.String(300)),
            sa.Column('zip_code', sa.String(10)),
            sa.Column('city', sa.String(100)),
            sa.Column('distance_km', sa.Numeric(10, 2)),
            sa.Column('is_active', sa.Boolean(), default=True),
            sa.Column('created_at', sa.DateTime()),
        )

    if not table_exists('appointment_blockers'):
        op.create_table('appointment_blockers',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
            sa.Column('employee_id', sa.Integer(), sa.ForeignKey('employees.id')),
            sa.Column('resource_id', sa.Integer(), sa.ForeignKey('resources.id')),
            sa.Column('location_id', sa.Integer(), sa.ForeignKey('locations.id')),
            sa.Column('start_time', sa.DateTime(), nullable=False),
            sa.Column('end_time', sa.DateTime(), nullable=False),
            sa.Column('title', sa.String(200)),
            sa.Column('blocker_type', sa.Integer(), default=0),
            sa.Column('is_recurring', sa.Boolean(), default=False),
            sa.Column('recurrence_json', sa.Text()),
            sa.Column('abo_id', sa.Integer()),
            sa.Column('notes', sa.Text()),
            sa.Column('is_deleted', sa.Boolean(), default=False),
            sa.Column('created_at', sa.DateTime()),
        )

    if not table_exists('appointment_groups'):
        op.create_table('appointment_groups',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
            sa.Column('employee_id', sa.Integer(), sa.ForeignKey('employees.id')),
            sa.Column('location_id', sa.Integer(), sa.ForeignKey('locations.id')),
            sa.Column('title', sa.String(200)),
            sa.Column('max_participants', sa.Integer(), default=10),
            sa.Column('start_time', sa.DateTime(), nullable=False),
            sa.Column('end_time', sa.DateTime(), nullable=False),
            sa.Column('is_recurring', sa.Boolean(), default=False),
            sa.Column('recurrence_json', sa.Text()),
            sa.Column('notes', sa.Text()),
            sa.Column('is_deleted', sa.Boolean(), default=False),
            sa.Column('created_at', sa.DateTime()),
        )

    if not table_exists('credits'):
        op.create_table('credits',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('patient_id', sa.Integer(), sa.ForeignKey('patients.id'), nullable=False),
            sa.Column('from_invoice_id', sa.Integer(), sa.ForeignKey('invoices.id')),
            sa.Column('original_amount', sa.Numeric(10, 2), nullable=False),
            sa.Column('remaining_amount', sa.Numeric(10, 2), nullable=False),
            sa.Column('is_deleted', sa.Boolean(), default=False),
            sa.Column('deleted_date', sa.DateTime()),
            sa.Column('created_at', sa.DateTime()),
        )

    if not table_exists('invoice_to_credits'):
        op.create_table('invoice_to_credits',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('invoice_id', sa.Integer(), sa.ForeignKey('invoices.id'), nullable=False),
            sa.Column('credit_id', sa.Integer(), sa.ForeignKey('credits.id'), nullable=False),
            sa.Column('amount', sa.Numeric(10, 2), nullable=False),
            sa.Column('created_at', sa.DateTime()),
        )

    if not table_exists('medidata_trackings'):
        op.create_table('medidata_trackings',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('invoice_id', sa.Integer(), sa.ForeignKey('invoices.id')),
            sa.Column('cost_approval_id', sa.Integer(), sa.ForeignKey('cost_approvals.id')),
            sa.Column('tracking_type', sa.Integer()),
            sa.Column('state', sa.Integer(), default=0),
            sa.Column('transmission_reference', sa.String(100)),
            sa.Column('request_id', sa.String(50)),
            sa.Column('error_message', sa.Text()),
            sa.Column('sent_at', sa.DateTime()),
            sa.Column('created_at', sa.DateTime()),
        )

    if not table_exists('medidata_responses'):
        op.create_table('medidata_responses',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('invoice_id', sa.Integer(), sa.ForeignKey('invoices.id')),
            sa.Column('cost_approval_id', sa.Integer(), sa.ForeignKey('cost_approvals.id')),
            sa.Column('response_type', sa.Integer()),
            sa.Column('response_code', sa.String(20)),
            sa.Column('response_text', sa.Text()),
            sa.Column('xml_content', sa.Text()),
            sa.Column('received_at', sa.DateTime()),
            sa.Column('created_at', sa.DateTime()),
        )

    if not table_exists('email_logs'):
        op.create_table('email_logs',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
            sa.Column('entity_type', sa.String(50)),
            sa.Column('entity_id', sa.Integer()),
            sa.Column('template_id', sa.Integer()),
            sa.Column('from_address', sa.String(200)),
            sa.Column('to_address', sa.String(200)),
            sa.Column('cc', sa.String(500)),
            sa.Column('subject', sa.String(500)),
            sa.Column('body_html', sa.Text()),
            sa.Column('status', sa.String(20)),
            sa.Column('error_message', sa.Text()),
            sa.Column('sent_at', sa.DateTime()),
            sa.Column('created_at', sa.DateTime()),
        )

    if not table_exists('sms_logs'):
        op.create_table('sms_logs',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
            sa.Column('entity_type', sa.String(50)),
            sa.Column('entity_id', sa.Integer()),
            sa.Column('phone_number', sa.String(30)),
            sa.Column('message', sa.Text()),
            sa.Column('status', sa.String(20)),
            sa.Column('error_message', sa.Text()),
            sa.Column('sent_at', sa.DateTime()),
            sa.Column('created_at', sa.DateTime()),
        )

    if not table_exists('treatment_reports'):
        op.create_table('treatment_reports',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
            sa.Column('series_id', sa.Integer(), sa.ForeignKey('treatment_series.id')),
            sa.Column('treatment_plan_id', sa.Integer(), sa.ForeignKey('treatment_plans.id')),
            sa.Column('patient_id', sa.Integer(), sa.ForeignKey('patients.id')),
            sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('employees.id')),
            sa.Column('report_type', sa.Integer(), default=0),
            sa.Column('title', sa.String(300)),
            sa.Column('content', sa.Text()),
            sa.Column('document_path', sa.String(500)),
            sa.Column('sent_date', sa.DateTime()),
            sa.Column('recipient_id', sa.Integer()),
            sa.Column('created_at', sa.DateTime()),
        )

    if not table_exists('appointment_to_products'):
        op.create_table('appointment_to_products',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('appointment_id', sa.Integer(), sa.ForeignKey('appointments.id'), nullable=False),
            sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id'), nullable=False),
            sa.Column('quantity', sa.Numeric(10, 2), default=1),
            sa.Column('price', sa.Numeric(10, 2)),
            sa.Column('created_at', sa.DateTime()),
        )

    if not table_exists('seriestemplate_items'):
        op.create_table('seriestemplate_items',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('template_id', sa.Integer(), sa.ForeignKey('treatment_series_templates.id'), nullable=False),
            sa.Column('position', sa.Integer(), default=0),
            sa.Column('duration_minutes', sa.Integer(), default=30),
            sa.Column('title', sa.String(200)),
            sa.Column('is_mtt', sa.Boolean(), default=False),
            sa.Column('treatment_type', sa.String(50)),
            sa.Column('created_at', sa.DateTime()),
        )

    if not table_exists('appointment_series'):
        op.create_table('appointment_series',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('template_id', sa.Integer(), sa.ForeignKey('treatment_series_templates.id')),
            sa.Column('resource_id', sa.Integer(), sa.ForeignKey('resources.id')),
            sa.Column('day_of_week', sa.Integer()),
            sa.Column('start_time', sa.Time()),
            sa.Column('end_time', sa.Time()),
            sa.Column('duration_minutes', sa.Integer(), default=30),
            sa.Column('employee_id', sa.Integer(), sa.ForeignKey('employees.id')),
            sa.Column('location_id', sa.Integer(), sa.ForeignKey('locations.id')),
            sa.Column('max_appointments', sa.Integer(), default=1),
            sa.Column('valid_from', sa.Date()),
            sa.Column('valid_to', sa.Date()),
            sa.Column('is_active', sa.Boolean(), default=True),
            sa.Column('created_at', sa.DateTime()),
        )

    if not table_exists('trusted_doctors'):
        op.create_table('trusted_doctors',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('insurance_provider_id', sa.Integer(), sa.ForeignKey('insurance_providers.id'), nullable=False),
            sa.Column('first_name', sa.String(100)),
            sa.Column('last_name', sa.String(100)),
            sa.Column('email', sa.String(200)),
            sa.Column('gln', sa.String(20)),
            sa.Column('created_at', sa.DateTime()),
        )

    if not table_exists('spam_list'):
        op.create_table('spam_list',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
            sa.Column('email', sa.String(200), nullable=False),
            sa.Column('reason', sa.Text()),
            sa.Column('created_at', sa.DateTime()),
        )

    if not table_exists('online_booking_mappings'):
        op.create_table('online_booking_mappings',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
            sa.Column('template_id', sa.Integer(), sa.ForeignKey('treatment_series_templates.id')),
            sa.Column('external_id', sa.String(100)),
            sa.Column('external_name', sa.String(200)),
            sa.Column('is_active', sa.Boolean(), default=True),
            sa.Column('created_at', sa.DateTime()),
        )

    if not table_exists('invoice_fixes'):
        op.create_table('invoice_fixes',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('invoice_id', sa.Integer(), sa.ForeignKey('invoices.id'), nullable=False),
            sa.Column('fix_type', sa.Integer()),
            sa.Column('description', sa.Text()),
            sa.Column('amount', sa.Numeric(10, 2)),
            sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('employees.id')),
            sa.Column('created_at', sa.DateTime()),
        )


def downgrade():
    # Neue Tabellen loeschen
    tables_to_drop = [
        'invoice_fixes', 'online_booking_mappings', 'spam_list',
        'trusted_doctors', 'appointment_series', 'seriestemplate_items',
        'appointment_to_products', 'treatment_reports', 'sms_logs',
        'email_logs', 'medidata_responses', 'medidata_trackings',
        'invoice_to_credits', 'credits', 'appointment_groups',
        'appointment_blockers', 'treatment_sites', 'treatment_categories',
    ]
    for table in tables_to_drop:
        if table_exists(table):
            op.drop_table(table)

    # Hinweis: Spalten-Entfernung bei SQLite nicht trivial moeglich
    # Bei Bedarf manuelle Migration erforderlich
    pass
