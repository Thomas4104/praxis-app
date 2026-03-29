"""Phase9: Doctor erweitert - mobile, homepage, country, expertise, birthday, sex, postbox, description_text

Revision ID: 69f2f4864138
Revises: 2e0c68d5ed7a
Create Date: 2026-03-29 19:05:53.188749

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '69f2f4864138'
down_revision = '2e0c68d5ed7a'
branch_labels = None
depends_on = None


def upgrade():
    # Nur neue Doctor-Felder hinzufuegen (Phase 9)
    with op.batch_alter_table('doctors', schema=None) as batch_op:
        batch_op.add_column(sa.Column('mobile', sa.String(length=30), nullable=True))
        batch_op.add_column(sa.Column('homepage', sa.String(length=300), nullable=True))
        batch_op.add_column(sa.Column('country', sa.String(length=5), server_default='CH', nullable=True))
        batch_op.add_column(sa.Column('expertise', sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column('birthday', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('sex', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('postbox', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('description_text', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('doctors', schema=None) as batch_op:
        batch_op.drop_column('description_text')
        batch_op.drop_column('postbox')
        batch_op.drop_column('sex')
        batch_op.drop_column('birthday')
        batch_op.drop_column('expertise')
        batch_op.drop_column('country')
        batch_op.drop_column('homepage')
        batch_op.drop_column('mobile')
