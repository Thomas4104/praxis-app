"""Add BankImport and BankImportLine models for CAMT/VESR import

Revision ID: 86c92c4331d1
Revises: 703a72a927db
Create Date: 2026-03-29 21:08:27.392783

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '86c92c4331d1'
down_revision = '703a72a927db'
branch_labels = None
depends_on = None


def upgrade():
    # Tabelle bank_imports
    op.create_table('bank_imports',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('import_date', sa.DateTime(), nullable=True),
        sa.Column('file_name', sa.String(length=300), nullable=False),
        sa.Column('file_type', sa.String(length=10), nullable=True),
        sa.Column('camt_version', sa.String(length=20), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('total_transactions', sa.Integer(), nullable=True),
        sa.Column('matched_count', sa.Integer(), nullable=True),
        sa.Column('unmatched_count', sa.Integer(), nullable=True),
        sa.Column('total_amount', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('bank_account_id', sa.Integer(), nullable=True),
        sa.Column('imported_by_id', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['bank_account_id'], ['bank_accounts.id'], name='fk_bankimport_bankaccount'),
        sa.ForeignKeyConstraint(['imported_by_id'], ['users.id'], name='fk_bankimport_user'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], name='fk_bankimport_org'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_bankimport_org_date', 'bank_imports', ['organization_id', 'import_date'])

    # Tabelle bank_import_lines
    op.create_table('bank_import_lines',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bank_import_id', sa.Integer(), nullable=False),
        sa.Column('transaction_date', sa.Date(), nullable=True),
        sa.Column('valuta_date', sa.Date(), nullable=True),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('credit_debit', sa.String(length=4), nullable=True),
        sa.Column('reference_number', sa.String(length=50), nullable=True),
        sa.Column('remittance_info', sa.String(length=500), nullable=True),
        sa.Column('debtor_name', sa.String(length=200), nullable=True),
        sa.Column('debtor_iban', sa.String(length=34), nullable=True),
        sa.Column('creditor_name', sa.String(length=200), nullable=True),
        sa.Column('creditor_iban', sa.String(length=34), nullable=True),
        sa.Column('entry_reference', sa.String(length=100), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('invoice_id', sa.Integer(), nullable=True),
        sa.Column('payment_id', sa.Integer(), nullable=True),
        sa.Column('journal_entry_id', sa.Integer(), nullable=True),
        sa.Column('match_type', sa.String(length=20), nullable=True),
        sa.Column('match_confidence', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('is_fully_paid', sa.Boolean(), nullable=True),
        sa.Column('overpayment', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['bank_import_id'], ['bank_imports.id'], name='fk_bankimportline_import'),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], name='fk_bankimportline_invoice'),
        sa.ForeignKeyConstraint(['journal_entry_id'], ['journal_entries.id'], name='fk_bankimportline_journal'),
        sa.ForeignKeyConstraint(['payment_id'], ['payments.id'], name='fk_bankimportline_payment'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_bankimportline_import', 'bank_import_lines', ['bank_import_id'])
    op.create_index('ix_bankimportline_ref', 'bank_import_lines', ['reference_number'])


def downgrade():
    op.drop_index('ix_bankimportline_ref', table_name='bank_import_lines')
    op.drop_index('ix_bankimportline_import', table_name='bank_import_lines')
    op.drop_table('bank_import_lines')
    op.drop_index('ix_bankimport_org_date', table_name='bank_imports')
    op.drop_table('bank_imports')
