"""Phase9: Doctor.last_name nullable fuer Firma-only Kontakte

Revision ID: 06f63d321445
Revises: 69f2f4864138
Create Date: 2026-03-29 19:13:45.426808

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '06f63d321445'
down_revision = '69f2f4864138'
branch_labels = None
depends_on = None


def upgrade():
    # SQLite: batch_alter_table noetig fuer nullable-Aenderung
    with op.batch_alter_table('doctors', schema=None) as batch_op:
        batch_op.alter_column('last_name',
               existing_type=sa.String(length=100),
               nullable=True)


def downgrade():
    with op.batch_alter_table('doctors', schema=None) as batch_op:
        batch_op.alter_column('last_name',
               existing_type=sa.String(length=100),
               nullable=False)
