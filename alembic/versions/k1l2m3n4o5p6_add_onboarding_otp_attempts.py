"""add onboarding otp attempts

Revision ID: k1l2m3n4o5p6
Revises: j0k1l2m3n4o5
Create Date: 2026-05-26 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'k1l2m3n4o5p6'
down_revision = 'j0k1l2m3n4o5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'onboarding_otp_attempts',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_onboarding_otp_attempts_created_at'), 'onboarding_otp_attempts', ['created_at'], unique=False)
    op.create_index(op.f('ix_onboarding_otp_attempts_user_id'), 'onboarding_otp_attempts', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_onboarding_otp_attempts_user_id'), table_name='onboarding_otp_attempts')
    op.drop_index(op.f('ix_onboarding_otp_attempts_created_at'), table_name='onboarding_otp_attempts')
    op.drop_table('onboarding_otp_attempts')
