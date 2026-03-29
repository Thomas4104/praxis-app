"""Review Phase8: org_id und updated_at fuer MedidataResponse/Tracking

Revision ID: 2e0c68d5ed7a
Revises: 5329aea9cee8
Create Date: 2026-03-29 18:50:39.600715
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "2e0c68d5ed7a"
down_revision = "5329aea9cee8"
branch_labels = None
depends_on = None


def _has_column(table, column):
    """Prueft ob Spalte bereits existiert (SQLite-kompatibel)"""
    conn = op.get_bind()
    insp = inspect(conn)
    cols = [c["name"] for c in insp.get_columns(table)]
    return column in cols


def _has_index(table, index_name):
    """Prueft ob Index bereits existiert"""
    conn = op.get_bind()
    insp = inspect(conn)
    indexes = [i["name"] for i in insp.get_indexes(table)]
    return index_name in indexes


def upgrade():
    # MedidataResponse
    if not _has_column("medidata_responses", "organization_id"):
        op.add_column("medidata_responses", sa.Column("organization_id", sa.Integer(), nullable=True))
    if not _has_column("medidata_responses", "updated_at"):
        op.add_column("medidata_responses", sa.Column("updated_at", sa.DateTime(), nullable=True))
    op.execute("""
        UPDATE medidata_responses SET organization_id = COALESCE(
            (SELECT organization_id FROM invoices WHERE invoices.id = medidata_responses.invoice_id),
            (SELECT organization_id FROM cost_approvals WHERE cost_approvals.id = medidata_responses.cost_approval_id),
            1
        ) WHERE organization_id IS NULL
    """)
    if not _has_index("medidata_responses", "ix_medresp_org"):
        op.create_index("ix_medresp_org", "medidata_responses", ["organization_id"])
    if not _has_index("medidata_responses", "ix_medresp_invoice"):
        op.create_index("ix_medresp_invoice", "medidata_responses", ["invoice_id"])

    # MedidataTracking
    if not _has_column("medidata_trackings", "organization_id"):
        op.add_column("medidata_trackings", sa.Column("organization_id", sa.Integer(), nullable=True))
    if not _has_column("medidata_trackings", "updated_at"):
        op.add_column("medidata_trackings", sa.Column("updated_at", sa.DateTime(), nullable=True))
    op.execute("""
        UPDATE medidata_trackings SET organization_id = COALESCE(
            (SELECT organization_id FROM invoices WHERE invoices.id = medidata_trackings.invoice_id),
            (SELECT organization_id FROM cost_approvals WHERE cost_approvals.id = medidata_trackings.cost_approval_id),
            1
        ) WHERE organization_id IS NULL
    """)
    if not _has_index("medidata_trackings", "ix_medtrack_org"):
        op.create_index("ix_medtrack_org", "medidata_trackings", ["organization_id"])
    if not _has_index("medidata_trackings", "ix_medtrack_invoice"):
        op.create_index("ix_medtrack_invoice", "medidata_trackings", ["invoice_id"])


def downgrade():
    op.drop_index("ix_medtrack_invoice", "medidata_trackings")
    op.drop_index("ix_medtrack_org", "medidata_trackings")
    op.drop_column("medidata_trackings", "updated_at")
    op.drop_column("medidata_trackings", "organization_id")
    op.drop_index("ix_medresp_invoice", "medidata_responses")
    op.drop_index("ix_medresp_org", "medidata_responses")
    op.drop_column("medidata_responses", "updated_at")
    op.drop_column("medidata_responses", "organization_id")
