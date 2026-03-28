"""add quotations tables

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-03-17 03:00:00.000000

NOTE: This migration is a no-op. The quotations and quotation_items tables
were already created by the initial migration 557407e76a9b. This stub exists
only to preserve the migration chain.
"""
from typing import Sequence, Union

revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
