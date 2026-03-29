"""Add room_availability to Resource

Revision ID: 703a72a927db
Revises: 22d61d00afe6
Create Date: 2026-03-29 20:23:13.440137

"""
from alembic import op
import sqlalchemy as sa

revision = '703a72a927db'
down_revision = '22d61d00afe6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('resources', schema=None) as batch_op:
        batch_op.add_column(sa.Column('room_availability', sa.String(length=20), server_default='available'))


def downgrade():
    with op.batch_alter_table('resources', schema=None) as batch_op:
        batch_op.drop_column('room_availability')
