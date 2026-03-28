"""add clients tables

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-03-17 01:00:00.000000

NOTE: This migration is a no-op. clients and client_products tables were
already created by the initial migration 557407e76a9b. This stub exists
only to preserve the migration chain.
"""
from typing import Sequence, Union

revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
