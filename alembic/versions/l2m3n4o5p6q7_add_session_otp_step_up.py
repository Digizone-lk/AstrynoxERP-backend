"""add session otp step up

Revision ID: l2m3n4o5p6q7
Revises: k1l2m3n4o5p6
Create Date: 2026-05-26 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'l2m3n4o5p6q7'
down_revision = 'k1l2m3n4o5p6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('user_sessions', sa.Column('otp_required', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('user_sessions', sa.Column('otp_verified_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('user_sessions', 'otp_verified_at')
    op.drop_column('user_sessions', 'otp_required')
