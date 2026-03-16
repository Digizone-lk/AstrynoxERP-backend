"""add currency to products

Revision ID: a1b2c3d4e5f6
Revises: 557407e76a9b
Create Date: 2026-03-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '557407e76a9b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('products', sa.Column('currency', sa.String(length=10), nullable=True, server_default='USD'))


def downgrade() -> None:
    op.drop_column('products', 'currency')
