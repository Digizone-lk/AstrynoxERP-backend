"""add product admin otp sessions

Revision ID: m3n4o5p6q7r8
Revises: l2m3n4o5p6q7
Create Date: 2026-05-26 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'm3n4o5p6q7r8'
down_revision = 'l2m3n4o5p6q7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'product_admin_otps',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('challenge_hash', sa.String(64), nullable=False),
        sa.Column('otp_hash', sa.String(64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_product_admin_otps_challenge_hash'), 'product_admin_otps', ['challenge_hash'], unique=True)
    op.create_index(op.f('ix_product_admin_otps_created_at'), 'product_admin_otps', ['created_at'], unique=False)
    op.create_index(op.f('ix_product_admin_otps_email'), 'product_admin_otps', ['email'], unique=False)
    op.create_index(op.f('ix_product_admin_otps_otp_hash'), 'product_admin_otps', ['otp_hash'], unique=False)

    op.create_table(
        'product_admin_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('refresh_token_hash', sa.String(64), nullable=False),
        sa.Column('device_info', sa.String(500), nullable=True),
        sa.Column('ip_address', sa.String(50), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_product_admin_sessions_email'), 'product_admin_sessions', ['email'], unique=False)
    op.create_index(op.f('ix_product_admin_sessions_refresh_token_hash'), 'product_admin_sessions', ['refresh_token_hash'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_product_admin_sessions_refresh_token_hash'), table_name='product_admin_sessions')
    op.drop_index(op.f('ix_product_admin_sessions_email'), table_name='product_admin_sessions')
    op.drop_table('product_admin_sessions')

    op.drop_index(op.f('ix_product_admin_otps_otp_hash'), table_name='product_admin_otps')
    op.drop_index(op.f('ix_product_admin_otps_email'), table_name='product_admin_otps')
    op.drop_index(op.f('ix_product_admin_otps_created_at'), table_name='product_admin_otps')
    op.drop_index(op.f('ix_product_admin_otps_challenge_hash'), table_name='product_admin_otps')
    op.drop_table('product_admin_otps')
