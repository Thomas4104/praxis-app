"""Phase10: Email color_code, handled_at, handled_by_id

Revision ID: 22d61d00afe6
Revises: 06f63d321445
Create Date: 2026-03-29 19:34:36.344474

"""
from alembic import op
import sqlalchemy as sa


revision = "22d61d00afe6"
down_revision = "06f63d321445"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("emails", schema=None) as batch_op:
        batch_op.add_column(sa.Column("color_code", sa.Integer(), default=0))
        batch_op.add_column(sa.Column("handled_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("handled_by_id", sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table("emails", schema=None) as batch_op:
        batch_op.drop_column("handled_by_id")
        batch_op.drop_column("handled_at")
        batch_op.drop_column("color_code")
