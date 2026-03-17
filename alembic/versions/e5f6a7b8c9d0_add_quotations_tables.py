"""add quotations tables

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-03-17 03:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create quotationstatus enum
    quotationstatus = postgresql.ENUM(
        'draft', 'sent', 'approved', 'rejected', 'converted',
        name='quotationstatus'
    )
    quotationstatus.create(op.get_bind())

    # Create quotations table
    op.create_table(
        'quotations',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('org_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('client_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('quote_number', sa.String(20), nullable=False),
        sa.Column('status', sa.Enum('draft', 'sent', 'approved', 'rejected', 'converted', name='quotationstatus'), nullable=False),
        sa.Column('issue_date', sa.Date(), nullable=False),
        sa.Column('valid_until', sa.Date(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('subtotal', sa.Numeric(14, 2), nullable=True, server_default='0'),
        sa.Column('total', sa.Numeric(14, 2), nullable=True, server_default='0'),
        sa.Column('currency', sa.String(10), nullable=True, server_default='USD'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_quotations_org_id'), 'quotations', ['org_id'], unique=False)
    op.create_index(op.f('ix_quotations_client_id'), 'quotations', ['client_id'], unique=False)

    # Create quotation_items table
    op.create_table(
        'quotation_items',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('quotation_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('product_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('product_name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('qty', sa.Numeric(10, 2), nullable=False),
        sa.Column('unit_price', sa.Numeric(12, 2), nullable=False),
        sa.Column('subtotal', sa.Numeric(14, 2), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=True, server_default='0'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['quotation_id'], ['quotations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_quotation_items_quotation_id'), 'quotation_items', ['quotation_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_quotation_items_quotation_id'), table_name='quotation_items')
    op.drop_table('quotation_items')

    op.drop_index(op.f('ix_quotations_client_id'), table_name='quotations')
    op.drop_index(op.f('ix_quotations_org_id'), table_name='quotations')
    op.drop_table('quotations')

    postgresql.ENUM(name='quotationstatus').drop(op.get_bind())
