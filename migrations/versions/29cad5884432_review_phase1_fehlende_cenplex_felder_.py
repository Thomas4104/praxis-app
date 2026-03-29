"""Review Phase1: Fehlende Cenplex-Felder ergaenzt

Revision ID: 29cad5884432
Revises: phase1c_datenmodell
Create Date: 2026-03-29 16:31:44.169778

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "29cad5884432"
down_revision = "phase1c_datenmodell"
branch_labels = None
depends_on = None


def upgrade():
    # Patient: premium_payer_address2
    with op.batch_alter_table("patients", schema=None) as batch_op:
        batch_op.add_column(sa.Column("premium_payer_address2", sa.String(length=300), nullable=True))

    # TreatmentSeries: billing_case
    with op.batch_alter_table("treatment_series", schema=None) as batch_op:
        batch_op.add_column(sa.Column("billing_case", sa.Integer(), nullable=True))

    # Invoice: fehlende Felder
    with op.batch_alter_table("invoices", schema=None) as batch_op:
        batch_op.add_column(sa.Column("inv_template_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("inv_template_name", sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column("credit_is_being_used", sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column("send_copy_time", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("attach_kogu_only", sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column("assigned_credit", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("inv_comment", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("has_taxpoint_issues", sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column("abo_break_id", sa.Integer(), nullable=True))

    # Appointment: fehlende Felder
    with op.batch_alter_table("appointments", schema=None) as batch_op:
        batch_op.add_column(sa.Column("taxpoints_json", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("emr_positions_json", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("is_urgent", sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column("abo_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("treatment_template_id", sa.Integer(), nullable=True))

    # AppointmentSerie: fehlende Felder
    with op.batch_alter_table("appointment_series", schema=None) as batch_op:
        batch_op.add_column(sa.Column("series_type", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("title", sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column("description", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("category", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("series_template_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("discount_series_template_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("planned_participants", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("planned_interval", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("planned_interval_type", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("online_available", sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column("price", sa.Numeric(precision=10, scale=2), nullable=True))
        batch_op.add_column(sa.Column("discount_price", sa.Numeric(precision=10, scale=2), nullable=True))
        batch_op.add_column(sa.Column("last_sync", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("blocker_category_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("series_templates_json", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("discount_series_templates_json", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("is_deleted", sa.Boolean(), nullable=True))


def downgrade():
    with op.batch_alter_table("appointment_series", schema=None) as batch_op:
        batch_op.drop_column("is_deleted")
        batch_op.drop_column("discount_series_templates_json")
        batch_op.drop_column("series_templates_json")
        batch_op.drop_column("blocker_category_id")
        batch_op.drop_column("last_sync")
        batch_op.drop_column("discount_price")
        batch_op.drop_column("price")
        batch_op.drop_column("online_available")
        batch_op.drop_column("planned_interval_type")
        batch_op.drop_column("planned_interval")
        batch_op.drop_column("planned_participants")
        batch_op.drop_column("discount_series_template_id")
        batch_op.drop_column("series_template_id")
        batch_op.drop_column("category")
        batch_op.drop_column("description")
        batch_op.drop_column("title")
        batch_op.drop_column("series_type")

    with op.batch_alter_table("appointments", schema=None) as batch_op:
        batch_op.drop_column("treatment_template_id")
        batch_op.drop_column("abo_id")
        batch_op.drop_column("is_urgent")
        batch_op.drop_column("emr_positions_json")
        batch_op.drop_column("taxpoints_json")

    with op.batch_alter_table("invoices", schema=None) as batch_op:
        batch_op.drop_column("abo_break_id")
        batch_op.drop_column("has_taxpoint_issues")
        batch_op.drop_column("inv_comment")
        batch_op.drop_column("assigned_credit")
        batch_op.drop_column("attach_kogu_only")
        batch_op.drop_column("send_copy_time")
        batch_op.drop_column("credit_is_being_used")
        batch_op.drop_column("inv_template_name")
        batch_op.drop_column("inv_template_id")

    with op.batch_alter_table("treatment_series", schema=None) as batch_op:
        batch_op.drop_column("billing_case")

    with op.batch_alter_table("patients", schema=None) as batch_op:
        batch_op.drop_column("premium_payer_address2")
