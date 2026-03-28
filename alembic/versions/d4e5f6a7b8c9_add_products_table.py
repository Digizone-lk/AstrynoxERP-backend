"""add products table

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-03-17 02:00:00.000000

NOTE: This migration is a no-op. The products table was already created
by the initial migration 557407e76a9b. This stub exists only to preserve
the migration chain.
"""
from typing import Sequence, Union

revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
