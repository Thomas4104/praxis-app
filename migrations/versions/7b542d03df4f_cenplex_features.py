"""cenplex features - neue Tabellen und Spalten

Revision ID: 7b542d03df4f
Revises: 495b7876aa86
Create Date: 2026-03-25 14:31:30.375180

"""
from alembic import op
import sqlalchemy as sa


revision = '7b542d03df4f'
down_revision = '495b7876aa86'
branch_labels = None
depends_on = None


def upgrade():
    # Neue Tabellen erstellen
    op.create_table('appointment_tariff_positions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('appointment_id', sa.Integer(), nullable=False),
        sa.Column('tariff_type', sa.String(length=20), nullable=False),
        sa.Column('tariff_code', sa.String(length=20), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('quantity', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('tax_points', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('tax_point_value', sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('vat_rate', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('vat_amount', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('position', sa.Integer(), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['appointment_id'], ['appointments.id']),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_atp_appointment', 'appointment_tariff_positions', ['appointment_id'])

    op.create_table('finding_templates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('template_type', sa.String(length=30), nullable=True),
        sa.Column('location_id', sa.Integer(), nullable=True),
        sa.Column('fields_json', sa.Text(), nullable=False),
        sa.Column('is_default', sa.Boolean(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.ForeignKeyConstraint(['location_id'], ['locations.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table('clinical_findings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('patient_id', sa.Integer(), nullable=False),
        sa.Column('series_id', sa.Integer(), nullable=True),
        sa.Column('appointment_id', sa.Integer(), nullable=True),
        sa.Column('template_id', sa.Integer(), nullable=True),
        sa.Column('finding_type', sa.String(length=30), nullable=True),
        sa.Column('data_json', sa.Text(), nullable=False),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.id']),
        sa.ForeignKeyConstraint(['series_id'], ['treatment_series.id']),
        sa.ForeignKeyConstraint(['appointment_id'], ['appointments.id']),
        sa.ForeignKeyConstraint(['template_id'], ['finding_templates.id']),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_finding_patient', 'clinical_findings', ['patient_id'])
    op.create_index('ix_finding_series', 'clinical_findings', ['series_id'])

    op.create_table('treatment_plan_templates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('goals_json', sa.Text(), nullable=True),
        sa.Column('measures_json', sa.Text(), nullable=True),
        sa.Column('frequency_json', sa.Text(), nullable=True),
        sa.Column('insurance_type', sa.String(length=20), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table('invoice_copy_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('send_channel', sa.String(length=20), nullable=True),
        sa.Column('send_timing', sa.String(length=30), nullable=True),
        sa.Column('email_template_id', sa.Integer(), nullable=True),
        sa.Column('sender_email', sa.String(length=200), nullable=True),
        sa.Column('create_task_on_failure', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.ForeignKeyConstraint(['email_template_id'], ['email_templates.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table('invoice_copies',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('invoice_id', sa.Integer(), nullable=False),
        sa.Column('recipient_type', sa.String(length=20), nullable=True),
        sa.Column('recipient_email', sa.String(length=200), nullable=True),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.Column('sent_via', sa.String(length=20), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('pdf_path', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_invoice_copy_invoice', 'invoice_copies', ['invoice_id'])
    op.create_index('ix_invoice_copy_status', 'invoice_copies', ['status'])

    op.create_table('questionnaires',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('questions_json', sa.Text(), nullable=False),
        sa.Column('scoring_json', sa.Text(), nullable=True),
        sa.Column('is_portal_visible', sa.Boolean(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table('questionnaire_responses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('questionnaire_id', sa.Integer(), nullable=False),
        sa.Column('patient_id', sa.Integer(), nullable=False),
        sa.Column('series_id', sa.Integer(), nullable=True),
        sa.Column('answers_json', sa.Text(), nullable=False),
        sa.Column('score', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('completed_via', sa.String(length=20), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['questionnaire_id'], ['questionnaires.id']),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.id']),
        sa.ForeignKeyConstraint(['series_id'], ['treatment_series.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_qr_patient', 'questionnaire_responses', ['patient_id'])
    op.create_index('ix_qr_questionnaire', 'questionnaire_responses', ['questionnaire_id'])

    op.create_table('group_appointment_participants',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('appointment_id', sa.Integer(), nullable=False),
        sa.Column('patient_id', sa.Integer(), nullable=False),
        sa.Column('series_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['appointment_id'], ['appointments.id']),
        sa.ForeignKeyConstraint(['patient_id'], ['patients.id']),
        sa.ForeignKeyConstraint(['series_id'], ['treatment_series.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_gap_appointment', 'group_appointment_participants', ['appointment_id'])
    op.create_index('ix_gap_patient', 'group_appointment_participants', ['patient_id'])

    # Neue Spalten auf bestehende Tabellen (SQLite-kompatibel mit add_column)
    op.add_column('appointments', sa.Column('series_number', sa.Integer(), nullable=True))
    op.add_column('appointments', sa.Column('is_termin_0', sa.Boolean(), nullable=True))
    op.add_column('appointments', sa.Column('charge_despite_cancel', sa.Boolean(), nullable=True))
    op.add_column('appointments', sa.Column('is_group', sa.Boolean(), nullable=True))
    op.add_column('appointments', sa.Column('max_participants', sa.Integer(), nullable=True))
    op.add_column('appointments', sa.Column('color_category', sa.String(length=30), nullable=True))

    op.add_column('treatment_series', sa.Column('iv_valid_until', sa.Date(), nullable=True))
    op.add_column('treatment_series', sa.Column('iv_decision_number', sa.String(length=50), nullable=True))
    op.add_column('treatment_series', sa.Column('iv_decision_date', sa.Date(), nullable=True))

    op.add_column('audit_logs', sa.Column('integrity_hash', sa.String(length=64), nullable=True))

    op.add_column('users', sa.Column('failed_login_attempts', sa.Integer(), nullable=True))
    op.add_column('users', sa.Column('locked_until', sa.DateTime(), nullable=True))
    op.add_column('users', sa.Column('totp_secret', sa.String(length=32), nullable=True))
    op.add_column('users', sa.Column('totp_enabled', sa.Boolean(), nullable=True))
    op.add_column('users', sa.Column('totp_backup_codes', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('users', 'totp_backup_codes')
    op.drop_column('users', 'totp_enabled')
    op.drop_column('users', 'totp_secret')
    op.drop_column('users', 'locked_until')
    op.drop_column('users', 'failed_login_attempts')
    op.drop_column('audit_logs', 'integrity_hash')
    op.drop_column('treatment_series', 'iv_decision_date')
    op.drop_column('treatment_series', 'iv_decision_number')
    op.drop_column('treatment_series', 'iv_valid_until')
    op.drop_column('appointments', 'color_category')
    op.drop_column('appointments', 'max_participants')
    op.drop_column('appointments', 'is_group')
    op.drop_column('appointments', 'charge_despite_cancel')
    op.drop_column('appointments', 'is_termin_0')
    op.drop_column('appointments', 'series_number')
    op.drop_table('group_appointment_participants')
    op.drop_table('questionnaire_responses')
    op.drop_table('questionnaires')
    op.drop_table('invoice_copies')
    op.drop_table('invoice_copy_configs')
    op.drop_table('treatment_plan_templates')
    op.drop_table('clinical_findings')
    op.drop_table('finding_templates')
    op.drop_table('appointment_tariff_positions')
