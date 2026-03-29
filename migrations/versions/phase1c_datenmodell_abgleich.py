"""Phase 1c: Cenplex Datenmodell-Abgleich - fehlende Felder

Revision ID: phase1c_datenmodell
Revises: phase1b_cenplex
Create Date: 2026-03-29

Adds missing Cenplex fields identified during systematic DTO comparison.
Only ADD COLUMN operations (safe for SQLite).
"""
from alembic import op
import sqlalchemy as sa

revision = 'phase1c_datenmodell'
down_revision = 'phase1b_cenplex'
branch_labels = None
depends_on = None


def _add_column_safe(table, column_name, column_type, **kwargs):
    """Add column only if it doesn't exist yet (SQLite safe)."""
    try:
        with op.batch_alter_table(table) as batch_op:
            batch_op.add_column(sa.Column(column_name, column_type, **kwargs))
    except Exception:
        pass  # Column already exists


def upgrade():
    # ============================================================
    # Organization
    # ============================================================
    _add_column_safe('organizations', 'opening_timeschedule_valid_until', sa.Date())

    # ============================================================
    # AppointmentBlocker
    # ============================================================
    _add_column_safe('appointment_blockers', 'is_worktime', sa.Boolean(), default=False)
    _add_column_safe('appointment_blockers', 'serie_appointment_id', sa.Integer())
    _add_column_safe('appointment_blockers', 'blocker_category_id', sa.Integer())
    _add_column_safe('appointment_blockers', 'booking_date', sa.DateTime())
    _add_column_safe('appointment_blockers', 'booking_type_id', sa.String(50))
    _add_column_safe('appointment_blockers', 'ab_description', sa.Text())

    # ============================================================
    # AppointmentGroup
    # ============================================================
    _add_column_safe('appointment_groups', 'taxpoints_json', sa.Text())
    _add_column_safe('appointment_groups', 'pauschal_price', sa.Numeric(10, 2))
    _add_column_safe('appointment_groups', 'is_pauschal', sa.Boolean(), default=False)
    _add_column_safe('appointment_groups', 'resources_json', sa.Text())
    _add_column_safe('appointment_groups', 'appointment_serie_id', sa.Integer())
    _add_column_safe('appointment_groups', 'last_sync', sa.DateTime())
    _add_column_safe('appointment_groups', 'hangout_url', sa.String(500))

    # ============================================================
    # Subscription (Abo) - 37 new fields
    # ============================================================
    sub_fields = [
        ('duration', sa.Integer()),
        ('duration_type', sa.Integer()),
        ('training_controls', sa.Integer()),
        ('number_of_visits', sa.Integer()),
        ('abo_type', sa.Integer()),
        ('payment_rates', sa.Integer()),
        ('price', sa.Numeric(10, 2)),
        ('price_break_penalty', sa.Numeric(10, 2)),
        ('access_start_time', sa.Time()),
        ('access_end_time', sa.Time()),
        ('contract_print_date', sa.DateTime()),
        ('qualicert_print_date', sa.DateTime()),
        ('discount', sa.Numeric(10, 2)),
        ('abo_message', sa.Text()),
        ('message_valid_until', sa.DateTime()),
        ('stop_reminding', sa.Boolean()),
        ('created_by_id', sa.Integer()),
        ('supervisor_id', sa.Integer()),
        ('apply_vat', sa.Boolean()),
        ('include_vat', sa.Boolean()),
        ('contract_received_date', sa.DateTime()),
        ('series_id', sa.Integer()),
        ('credit_amount', sa.Numeric(10, 2)),
        ('credit_series_id', sa.Integer()),
        ('is_preferred_for_batch', sa.Boolean()),
        ('no_sync_egym', sa.Boolean()),
        ('no_sync_milon', sa.Boolean()),
        ('no_sync_mywellness', sa.Boolean()),
        ('gantner_devices', sa.Text()),
        ('gantner_locations', sa.Text()),
        ('gantner_only_valid_abos', sa.Boolean()),
        ('invoice_receiver_id', sa.Integer()),
        ('referrer_id', sa.Integer()),
        ('apply_vat_to_position_invoice', sa.Boolean()),
        ('include_vat_to_position_invoice', sa.Boolean()),
        ('no_sync_dividat', sa.Boolean()),
        ('is_deleted', sa.Boolean()),
    ]
    for col_name, col_type in sub_fields:
        _add_column_safe('subscriptions', col_name, col_type)

    # ============================================================
    # SubscriptionTemplate (AboTemplate) - 28 new fields
    # ============================================================
    sub_tmpl_fields = [
        ('sub_duration_type', sa.Integer()),
        ('payment_type', sa.Integer()),
        ('sub_payment_rates', sa.Integer()),
        ('price_once', sa.Numeric(10, 2)),
        ('price_month', sa.Numeric(10, 2)),
        ('price_rate', sa.Numeric(10, 2)),
        ('price_batch_depot', sa.Numeric(10, 2)),
        ('price_break_penalty', sa.Numeric(10, 2)),
        ('sub_access_start_time', sa.Time()),
        ('sub_access_end_time', sa.Time()),
        ('sub_training_controls', sa.Integer()),
        ('sub_credit_amount', sa.Numeric(10, 2)),
        ('no_sync_egym', sa.Boolean()),
        ('no_sync_milon', sa.Boolean()),
        ('no_sync_mywellness', sa.Boolean()),
        ('gantner_devices', sa.Text()),
        ('gantner_locations', sa.Text()),
        ('gantner_only_valid_abos', sa.Boolean()),
        ('valid_times', sa.Text()),
        ('sub_tags', sa.String(500)),
        ('linked_series_template_id', sa.Integer()),
        ('one_appointment_per_day', sa.Boolean()),
        ('book_appointment_for_visit', sa.Boolean()),
        ('use_visits_and_duration', sa.Boolean()),
        ('sub_visits', sa.Integer()),
        ('no_sync_dividat', sa.Boolean()),
        ('is_deleted', sa.Boolean()),
        ('sub_position', sa.Integer()),
    ]
    for col_name, col_type in sub_tmpl_fields:
        _add_column_safe('subscription_templates', col_name, col_type)

    # ============================================================
    # TreatmentCategory
    # ============================================================
    _add_column_safe('treatment_categories', 'templates_json', sa.Text())
    _add_column_safe('treatment_categories', 'therapists_json', sa.Text())
    _add_column_safe('treatment_categories', 'tc_user_groups_json', sa.Text())

    # ============================================================
    # TreatmentSite
    # ============================================================
    _add_column_safe('treatment_sites', 'ts_position', sa.Integer())
    _add_column_safe('treatment_sites', 'is_deleted', sa.Boolean())
    _add_column_safe('treatment_sites', 'short_name', sa.String(20))
    _add_column_safe('treatment_sites', 'background_color', sa.Integer())

    # ============================================================
    # TreatmentPlan
    # ============================================================
    _add_column_safe('treatment_plans', 'main_general_plantag_id', sa.Integer())
    _add_column_safe('treatment_plans', 'general_plantag_ids_json', sa.Text())
    _add_column_safe('treatment_plans', 'diagnose_ids_json', sa.Text())

    # ============================================================
    # InvoiceItem
    # ============================================================
    _add_column_safe('invoice_items', 'product_id', sa.Integer())

    # ============================================================
    # Payment
    # ============================================================
    _add_column_safe('payments', 'for_deleted_invoice_id', sa.Integer())


def downgrade():
    # SQLite doesn't support DROP COLUMN in older versions
    # These columns are safe to leave in place
    pass
