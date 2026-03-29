"""Add updated_at to BankImport and BankImportLine

Revision ID: 70c24f3d2f6a
Revises: 86c92c4331d1
Create Date: 2026-03-29 21:15:16.335282

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '70c24f3d2f6a'
down_revision = '86c92c4331d1'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('bank_imports', sa.Column('updated_at', sa.DateTime(), nullable=True))
    op.add_column('bank_import_lines', sa.Column('updated_at', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('bank_import_lines', 'updated_at')
    op.drop_column('bank_imports', 'updated_at')
