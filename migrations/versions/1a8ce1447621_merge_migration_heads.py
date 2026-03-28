"""merge migration heads

Revision ID: 1a8ce1447621
Revises: 7b542d03df4f, cc5ad08af14e
Create Date: 2026-03-25 20:51:38.938578

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1a8ce1447621'
down_revision = ('7b542d03df4f', 'cc5ad08af14e')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
