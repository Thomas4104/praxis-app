"""Phase1b: Cenplex Datenmodell-Abgleich - fehlende Felder und neue Models

Revision ID: phase1b_cenplex
Revises: phase1_cenplex
Create Date: 2026-03-29
"""
from alembic import op
import sqlalchemy as sa

revision = 'phase1b_cenplex'
down_revision = 'phase1_cenplex'
branch_labels = None
depends_on = None


def upgrade():
    # ---- Fehlende Felder auf bestehenden Tabellen ----

    # Appointment: Neue Felder
    with op.batch_alter_table('appointments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('flags', sa.Integer(), default=0))
        batch_op.add_column(sa.Column('pauschal_name', sa.String(200)))
        batch_op.add_column(sa.Column('ergo_positions_json', sa.Text()))
        batch_op.add_column(sa.Column('uvg_positions_json', sa.Text()))
        batch_op.add_column(sa.Column('treatment4', sa.Text()))
        batch_op.add_column(sa.Column('treatment5', sa.Text()))
        batch_op.add_column(sa.Column('is_hidden', sa.Boolean(), default=False))
        batch_op.add_column(sa.Column('no_sync', sa.Boolean(), default=False))
        batch_op.add_column(sa.Column('hangout_url', sa.String(500)))
        batch_op.add_column(sa.Column('calit_id', sa.BigInteger()))
        batch_op.add_column(sa.Column('last_patient_action', sa.Integer()))
        batch_op.add_column(sa.Column('last_patient_action_date', sa.DateTime()))
        batch_op.add_column(sa.Column('member_of_group_id', sa.Integer()))
        batch_op.add_column(sa.Column('therapy', sa.Text()))
        batch_op.add_column(sa.Column('is_private', sa.Boolean(), default=False))
        batch_op.add_column(sa.Column('is_deleted', sa.Boolean(), default=False))
        batch_op.add_column(sa.Column('position_in_series', sa.Integer()))
        batch_op.add_column(sa.Column('treatment_site_id', sa.Integer()))

    # Patient: Neue Felder
    with op.batch_alter_table('patients', schema=None) as batch_op:
        batch_op.add_column(sa.Column('treatment_site_id', sa.Integer()))
        batch_op.add_column(sa.Column('patient_service_query_datetime', sa.DateTime()))
        batch_op.add_column(sa.Column('preferred_timeschedule_valid_until', sa.Date()))
        batch_op.add_column(sa.Column('covid_cert_valid_until', sa.Date()))

    # Task/Mission: Neue Felder
    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.add_column(sa.Column('task_force_response', sa.Boolean(), default=False))
        batch_op.add_column(sa.Column('task_links_json', sa.Text()))
        batch_op.add_column(sa.Column('task_color', sa.Integer(), default=0))
        batch_op.add_column(sa.Column('has_updates', sa.Boolean(), default=False))
        batch_op.add_column(sa.Column('vacation_request_id', sa.Integer()))
        batch_op.add_column(sa.Column('treatment_plan_id', sa.Integer()))

    # Doctor: Neue Felder
    with op.batch_alter_table('doctors', schema=None) as batch_op:
        batch_op.add_column(sa.Column('kanton', sa.String(5)))
        batch_op.add_column(sa.Column('company', sa.String(200)))
        batch_op.add_column(sa.Column('department', sa.String(200)))
        batch_op.add_column(sa.Column('addressing', sa.String(200)))
        batch_op.add_column(sa.Column('description_de', sa.Text()))
        batch_op.add_column(sa.Column('description_fr', sa.Text()))
        batch_op.add_column(sa.Column('description_it', sa.Text()))
        batch_op.add_column(sa.Column('is_deleted', sa.Boolean(), default=False))

    # ---- Neue Tabellen ----

    op.create_table('employee_capacities',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('employee_id', sa.Integer(), sa.ForeignKey('employees.id'), nullable=False),
        sa.Column('capacity', sa.Integer(), default=100),
        sa.Column('valid_from', sa.Date(), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), default=False),
        sa.Column('created_at', sa.DateTime()),
    )

    op.create_table('employee_workplans',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('employee_id', sa.Integer(), sa.ForeignKey('employees.id'), nullable=False),
        sa.Column('name', sa.String(200)),
        sa.Column('from_date', sa.Date(), nullable=False),
        sa.Column('to_date', sa.Date(), nullable=False),
        sa.Column('planned_date', sa.Date()),
        sa.Column('work_schedule_json', sa.Text()),
        sa.Column('created_at', sa.DateTime()),
    )

    op.create_table('employee_license_breaks',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('employee_id', sa.Integer(), sa.ForeignKey('employees.id'), nullable=False),
        sa.Column('paused_during', sa.Date(), nullable=False),
        sa.Column('created_at', sa.DateTime()),
    )

    op.create_table('reserved_times',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id')),
        sa.Column('employee_id', sa.Integer(), sa.ForeignKey('employees.id')),
        sa.Column('patient_id', sa.Integer(), sa.ForeignKey('patients.id')),
        sa.Column('resource_id', sa.Integer(), sa.ForeignKey('resources.id')),
        sa.Column('room_id', sa.Integer()),
        sa.Column('location_id', sa.Integer(), sa.ForeignKey('locations.id')),
        sa.Column('workplan_id', sa.Integer(), sa.ForeignKey('employee_workplans.id')),
        sa.Column('treatment_site_id', sa.Integer()),
        sa.Column('start_time', sa.DateTime(), nullable=False),
        sa.Column('end_time', sa.DateTime(), nullable=False),
        sa.Column('title', sa.String(200)),
        sa.Column('reserved_type', sa.Integer(), default=0),
        sa.Column('is_vacation', sa.Boolean(), default=False),
        sa.Column('vacation_type', sa.Integer(), default=0),
        sa.Column('is_halfday', sa.Boolean(), default=False),
        sa.Column('is_global', sa.Boolean(), default=False),
        sa.Column('is_yearly', sa.Boolean(), default=False),
        sa.Column('applies_to_employee', sa.Boolean(), default=True),
        sa.Column('planned_location_id', sa.Integer()),
        sa.Column('planning_batch_id', sa.Integer()),
        sa.Column('receiver', sa.String(200)),
        sa.Column('created_at', sa.DateTime()),
    )
    op.create_index('ix_reserved_emp_time', 'reserved_times', ['employee_id', 'start_time', 'end_time'])

    op.create_table('patient_block_times',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('patient_id', sa.Integer(), sa.ForeignKey('patients.id'), nullable=False),
        sa.Column('start_date', sa.DateTime(), nullable=False),
        sa.Column('end_date', sa.DateTime(), nullable=False),
        sa.Column('reason', sa.Text()),
        sa.Column('created_at', sa.DateTime()),
    )

    op.create_table('doctor_reports',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('patient_id', sa.Integer(), sa.ForeignKey('patients.id'), nullable=False),
        sa.Column('therapist_id', sa.Integer(), sa.ForeignKey('employees.id')),
        sa.Column('doctor_id', sa.Integer()),
        sa.Column('cost_unit_id', sa.Integer()),
        sa.Column('headline', sa.String(300)),
        sa.Column('content_text', sa.Text()),
        sa.Column('last_sent', sa.DateTime()),
        sa.Column('last_sent_to', sa.String(200)),
        sa.Column('created_at', sa.DateTime()),
    )

    op.create_table('overtime_history',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('employee_id', sa.Integer(), sa.ForeignKey('employees.id'), nullable=False),
        sa.Column('allotment_id', sa.Integer()),
        sa.Column('month', sa.Date(), nullable=False),
        sa.Column('planned_worktime', sa.Numeric(10, 2), default=0),
        sa.Column('planned_admintime', sa.Numeric(10, 2), default=0),
        sa.Column('planned_overtime_buffer', sa.Numeric(10, 2), default=0),
        sa.Column('treatment_time', sa.Numeric(10, 2), default=0),
        sa.Column('admin_time', sa.Numeric(10, 2), default=0),
        sa.Column('general_time', sa.Numeric(10, 2), default=0),
        sa.Column('group_time', sa.Numeric(10, 2), default=0),
        sa.Column('overtime', sa.Numeric(10, 2), default=0),
        sa.Column('created_at', sa.DateTime()),
    )

    op.create_table('email_drafts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('created_by_id', sa.Integer(), sa.ForeignKey('employees.id')),
        sa.Column('location_id', sa.Integer()),
        sa.Column('patient_id', sa.Integer(), sa.ForeignKey('patients.id')),
        sa.Column('invoice_id', sa.Integer()),
        sa.Column('series_id', sa.Integer()),
        sa.Column('treatment_plan_id', sa.Integer()),
        sa.Column('doctor_report_id', sa.Integer()),
        sa.Column('abo_id', sa.Integer()),
        sa.Column('response_to_id', sa.BigInteger()),
        sa.Column('draft_type', sa.Integer(), default=0),
        sa.Column('language', sa.Integer()),
        sa.Column('template_identifier', sa.String(50)),
        sa.Column('text_template_id', sa.Integer()),
        sa.Column('receivers', sa.Text()),
        sa.Column('receivers_cc', sa.Text()),
        sa.Column('receivers_bcc', sa.Text()),
        sa.Column('subject', sa.String(500)),
        sa.Column('message', sa.Text()),
        sa.Column('attachments_json', sa.Text()),
        sa.Column('parameters_json', sa.Text()),
        sa.Column('created_at', sa.DateTime()),
    )

    op.create_table('email_inbox',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('sender', sa.String(300)),
        sa.Column('receiver', sa.String(300)),
        sa.Column('received', sa.DateTime(), nullable=False),
        sa.Column('subject', sa.String(500)),
        sa.Column('message_text', sa.Text()),
        sa.Column('message_html', sa.Text()),
        sa.Column('message_id', sa.String(300)),
        sa.Column('response_to_id', sa.String(300)),
        sa.Column('response_to_inbox_id', sa.BigInteger()),
        sa.Column('patient_id', sa.Integer(), sa.ForeignKey('patients.id')),
        sa.Column('handled_by_id', sa.Integer()),
        sa.Column('read_date', sa.DateTime()),
        sa.Column('handled_date', sa.DateTime()),
        sa.Column('is_deleted', sa.Boolean(), default=False),
        sa.Column('is_spam', sa.Boolean(), default=False),
        sa.Column('color_code', sa.Integer()),
        sa.Column('email_folder_id', sa.Integer()),
        sa.Column('html_file_key', sa.String(200)),
        sa.Column('created_at', sa.DateTime()),
    )

    op.create_table('email_triggers',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('patient_id', sa.Integer(), sa.ForeignKey('patients.id'), nullable=False),
        sa.Column('created_by_id', sa.Integer()),
        sa.Column('template_id', sa.Integer()),
        sa.Column('treatment_plan_id', sa.Integer()),
        sa.Column('action_date', sa.DateTime(), nullable=False),
        sa.Column('sent', sa.DateTime()),
        sa.Column('created_at', sa.DateTime()),
    )

    op.create_table('email_mappings',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('email', sa.String(200), nullable=False),
        sa.Column('employee_id', sa.Integer()),
        sa.Column('location_id', sa.Integer()),
        sa.Column('sent_email_bcc', sa.String(300)),
        sa.Column('received_email_bcc', sa.String(300)),
        sa.Column('users_json', sa.Text()),
        sa.Column('user_groups_json', sa.Text()),
        sa.Column('absence_subject', sa.String(200)),
        sa.Column('absence_note', sa.Text()),
        sa.Column('absence_note_active_from', sa.DateTime()),
        sa.Column('absence_note_active_till', sa.DateTime()),
        sa.Column('fetch_all', sa.Boolean(), default=False),
        sa.Column('is_default', sa.Boolean(), default=False),
        sa.Column('created_at', sa.DateTime()),
    )

    op.create_table('cancel_trigger_logs',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('patient_id', sa.Integer(), sa.ForeignKey('patients.id'), nullable=False),
        sa.Column('appointment_id', sa.Integer()),
        sa.Column('email_log_id', sa.BigInteger()),
        sa.Column('sms_log_id', sa.BigInteger()),
        sa.Column('cancelled', sa.DateTime()),
        sa.Column('sms_sent', sa.DateTime()),
        sa.Column('email_sent', sa.DateTime()),
        sa.Column('calit_sent', sa.DateTime()),
        sa.Column('was_manual', sa.Boolean(), default=False),
        sa.Column('created_at', sa.DateTime()),
    )

    op.create_table('external_apis',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('location_id', sa.Integer()),
        sa.Column('provider_key', sa.String(100), nullable=False),
        sa.Column('settings_json', sa.Text()),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime()),
    )

    op.create_table('fitness_configs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('location_id', sa.Integer(), nullable=False),
        sa.Column('bank_account_id', sa.Integer()),
        sa.Column('contract_text', sa.Text()),
        sa.Column('depot_price', sa.Numeric(10, 2)),
        sa.Column('nfc_writer', sa.String(200)),
        sa.Column('expiry_warning_json', sa.Text()),
        sa.Column('egym_id', sa.String(100)),
        sa.Column('egym_token', sa.String(500)),
        sa.Column('egym_settings_json', sa.Text()),
        sa.Column('milon_id', sa.String(100)),
        sa.Column('milon_token', sa.String(500)),
        sa.Column('milon_settings_json', sa.Text()),
        sa.Column('mywellness_api_key', sa.String(200)),
        sa.Column('mywellness_url', sa.String(300)),
        sa.Column('mywellness_token', sa.String(500)),
        sa.Column('mywellness_token_valid', sa.DateTime()),
        sa.Column('mywellness_facility_id', sa.String(100)),
        sa.Column('mywellness_settings_json', sa.Text()),
        sa.Column('gantner_config_json', sa.Text()),
        sa.Column('booking_configuration_json', sa.Text()),
        sa.Column('use_start_as_due_date', sa.Boolean(), default=False),
        sa.Column('abo_break_vat_type', sa.Integer(), default=0),
        sa.Column('hide_qualicert', sa.Boolean(), default=False),
        sa.Column('zsr', sa.String(20)),
        sa.Column('payment_due_days', sa.Integer()),
        sa.Column('mission_receiver_type', sa.Integer()),
        sa.Column('mission_receivers_json', sa.Text()),
        sa.Column('created_at', sa.DateTime()),
    )

    op.create_table('fitness_automations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('title', sa.String(200)),
        sa.Column('automation_type', sa.Integer(), default=0),
        sa.Column('text_templates_json', sa.Text()),
        sa.Column('document_templates_json', sa.Text()),
        sa.Column('rules_json', sa.Text()),
        sa.Column('email_template_id', sa.Integer()),
        sa.Column('extend_with_template_id', sa.Integer()),
        sa.Column('created_by_id', sa.Integer()),
        sa.Column('is_deleted', sa.Boolean(), default=False),
        sa.Column('created_at', sa.DateTime()),
    )

    op.create_table('gantner_traces',
        sa.Column('id', sa.BigInteger(), primary_key=True),
        sa.Column('patient_id', sa.Integer(), sa.ForeignKey('patients.id')),
        sa.Column('abo_id', sa.Integer()),
        sa.Column('batch_id', sa.String(50)),
        sa.Column('access_granted', sa.Boolean(), default=False),
        sa.Column('created_at', sa.DateTime()),
    )

    op.create_table('supplement_orders',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('patient_id', sa.Integer(), sa.ForeignKey('patients.id'), nullable=False),
        sa.Column('supplier_id', sa.Integer(), nullable=False),
        sa.Column('employee_id', sa.Integer()),
        sa.Column('print_date', sa.DateTime()),
        sa.Column('send_date', sa.DateTime()),
        sa.Column('created_at', sa.DateTime()),
    )

    op.create_table('supplement_order_items',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('order_id', sa.Integer(), sa.ForeignKey('supplement_orders.id'), nullable=False),
        sa.Column('product_id', sa.Integer()),
        sa.Column('quantity', sa.Integer(), default=1),
        sa.Column('note', sa.Text()),
        sa.Column('created_at', sa.DateTime()),
    )

    op.create_table('invoice_reminders',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('invoice_id', sa.Integer(), sa.ForeignKey('invoices.id'), nullable=False),
        sa.Column('reminder_try', sa.Integer(), nullable=False),
        sa.Column('creation_date', sa.DateTime(), nullable=False),
        sa.Column('send_date', sa.DateTime()),
        sa.Column('reminder_text', sa.Text()),
        sa.Column('original_document_path', sa.String(500)),
        sa.Column('md_id', sa.Integer()),
        sa.Column('due_days', sa.Integer()),
        sa.Column('reminder_fee', sa.Numeric(10, 2), default=0),
        sa.Column('is_xml45', sa.Boolean(), default=False),
        sa.Column('file_key', sa.String(200)),
        sa.Column('created_at', sa.DateTime()),
    )

    op.create_table('physiotec_training_plans',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('patient_id', sa.Integer(), sa.ForeignKey('patients.id'), nullable=False),
        sa.Column('program_id', sa.BigInteger()),
        sa.Column('user_id', sa.BigInteger()),
        sa.Column('exercises', sa.Integer()),
        sa.Column('title', sa.String(300)),
        sa.Column('start_date', sa.Date()),
        sa.Column('end_date', sa.Date()),
        sa.Column('physiotec_clm_id', sa.String(100)),
        sa.Column('created_at', sa.DateTime()),
    )

    op.create_table('kpi_dashboard_configs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('employee_id', sa.Integer(), sa.ForeignKey('employees.id'), nullable=False),
        sa.Column('kpi_type', sa.Integer(), default=0),
        sa.Column('columns', sa.Integer(), default=2),
        sa.Column('name', sa.String(200)),
        sa.Column('created_at', sa.DateTime()),
    )

    op.create_table('kpi_settings',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('employee_id', sa.Integer(), sa.ForeignKey('employees.id'), nullable=False),
        sa.Column('kpi_type', sa.Integer(), default=0),
        sa.Column('graph_type', sa.Integer(), default=0),
        sa.Column('data_grouping_type', sa.Integer(), default=0),
        sa.Column('name', sa.String(200)),
        sa.Column('data_lines_json', sa.Text()),
        sa.Column('time_filters_json', sa.Text()),
        sa.Column('budget_lines_json', sa.Text()),
        sa.Column('created_at', sa.DateTime()),
    )

    op.create_table('abo_actions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('subscription_id', sa.Integer(), sa.ForeignKey('subscriptions.id'), nullable=False),
        sa.Column('employee_id', sa.Integer(), sa.ForeignKey('employees.id'), nullable=False),
        sa.Column('action_date', sa.DateTime(), nullable=False),
        sa.Column('action_type', sa.Integer(), default=0),
        sa.Column('action_content', sa.Text()),
        sa.Column('created_at', sa.DateTime()),
    )

    op.create_table('abo_positions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('subscription_id', sa.Integer(), sa.ForeignKey('subscriptions.id'), nullable=False),
        sa.Column('product_id', sa.Integer()),
        sa.Column('name', sa.String(200)),
        sa.Column('quantity', sa.Integer(), default=1),
        sa.Column('unit_price_netto', sa.Numeric(10, 2)),
        sa.Column('vat_rate', sa.Numeric(5, 2), default=0),
        sa.Column('valuta_date', sa.Date()),
        sa.Column('created_by_id', sa.Integer()),
        sa.Column('was_billed', sa.Boolean(), default=False),
        sa.Column('created_at', sa.DateTime()),
    )

    op.create_table('abo_visits',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('subscription_id', sa.Integer(), sa.ForeignKey('subscriptions.id'), nullable=False),
        sa.Column('appointment_id', sa.Integer()),
        sa.Column('location_id', sa.Integer()),
        sa.Column('start_time', sa.DateTime(), nullable=False),
        sa.Column('end_time', sa.DateTime()),
        sa.Column('created_at', sa.DateTime()),
    )

    op.create_table('mission_notes',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('task_id', sa.Integer(), sa.ForeignKey('tasks.id'), nullable=False),
        sa.Column('employee_id', sa.Integer(), sa.ForeignKey('employees.id'), nullable=False),
        sa.Column('notes', sa.Text()),
        sa.Column('created_at', sa.DateTime()),
    )

    op.create_table('mission_responses',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('task_id', sa.Integer(), sa.ForeignKey('tasks.id'), nullable=False),
        sa.Column('sender_id', sa.Integer(), sa.ForeignKey('employees.id'), nullable=False),
        sa.Column('receiver_id', sa.Integer(), sa.ForeignKey('employees.id'), nullable=False),
        sa.Column('response', sa.Text()),
        sa.Column('read_date', sa.DateTime()),
        sa.Column('created_at', sa.DateTime()),
    )

    op.create_table('mission_to_employees',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('task_id', sa.Integer(), sa.ForeignKey('tasks.id'), nullable=False),
        sa.Column('employee_id', sa.Integer(), sa.ForeignKey('employees.id'), nullable=False),
        sa.Column('started', sa.DateTime()),
        sa.Column('finished', sa.DateTime()),
        sa.Column('read_date', sa.DateTime()),
        sa.Column('has_updates', sa.Boolean(), default=False),
        sa.Column('notes', sa.Text()),
        sa.Column('created_at', sa.DateTime()),
    )


def downgrade():
    tables = [
        'mission_to_employees', 'mission_responses', 'mission_notes',
        'abo_visits', 'abo_positions', 'abo_actions',
        'kpi_settings', 'kpi_dashboard_configs',
        'physiotec_training_plans', 'invoice_reminders',
        'supplement_order_items', 'supplement_orders',
        'gantner_traces', 'fitness_automations', 'fitness_configs',
        'external_apis', 'cancel_trigger_logs', 'email_mappings',
        'email_triggers', 'email_inbox', 'email_drafts',
        'overtime_history', 'doctor_reports', 'patient_block_times',
        'reserved_times', 'employee_license_breaks',
        'employee_workplans', 'employee_capacities',
    ]
    for t in tables:
        op.drop_table(t)
