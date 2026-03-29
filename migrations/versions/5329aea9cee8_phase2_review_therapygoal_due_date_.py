"""Phase2 Review: TherapyGoal due_date finished_date parent_id

Revision ID: 5329aea9cee8
Revises: 29cad5884432
Create Date: 2026-03-29 16:50:45.507680

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5329aea9cee8'
down_revision = '29cad5884432'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('therapy_goals', schema=None) as batch_op:
        batch_op.add_column(sa.Column('due_date', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('finished_date', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('parent_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_therapy_goals_parent_id', 'therapy_goals', ['parent_id'], ['id'])


def downgrade():
    with op.batch_alter_table('therapy_goals', schema=None) as batch_op:
        batch_op.drop_constraint('fk_therapy_goals_parent_id', type_='foreignkey')
        batch_op.drop_column('parent_id')
        batch_op.drop_column('finished_date')
        batch_op.drop_column('due_date')
