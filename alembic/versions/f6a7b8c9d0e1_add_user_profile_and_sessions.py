"""add user profile fields and user_sessions table

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-03-28 00:00:00.000000
"""
from typing import Sequence, Union
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add profile columns to users table
    op.add_column('users', sa.Column('phone', sa.String(50), nullable=True))
    op.add_column('users', sa.Column('job_title', sa.String(100), nullable=True))
    op.add_column('users', sa.Column('timezone', sa.String(50), nullable=True, server_default='UTC'))
    op.add_column('users', sa.Column('language', sa.String(10), nullable=True, server_default='en'))
    op.add_column('users', sa.Column('avatar_url', sa.String(500), nullable=True))
    op.add_column('users', sa.Column('notification_prefs', postgresql.JSON(astext_type=sa.Text()), nullable=True))

    # Create user_sessions table
    op.create_table(
        'user_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('org_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('refresh_token_hash', sa.String(64), nullable=False),
        sa.Column('device_info', sa.String(500), nullable=True),
        sa.Column('ip_address', sa.String(50), nullable=True),
        sa.Column('last_active_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_user_sessions_user_id', 'user_sessions', ['user_id'])
    op.create_index('ix_user_sessions_org_id', 'user_sessions', ['org_id'])
    op.create_unique_constraint('uq_user_sessions_token_hash', 'user_sessions', ['refresh_token_hash'])
    op.create_index('ix_user_sessions_token_hash', 'user_sessions', ['refresh_token_hash'])


def downgrade() -> None:
    op.drop_index('ix_user_sessions_token_hash', table_name='user_sessions')
    op.drop_constraint('uq_user_sessions_token_hash', 'user_sessions', type_='unique')
    op.drop_index('ix_user_sessions_org_id', table_name='user_sessions')
    op.drop_index('ix_user_sessions_user_id', table_name='user_sessions')
    op.drop_table('user_sessions')

    op.drop_column('users', 'notification_prefs')
    op.drop_column('users', 'avatar_url')
    op.drop_column('users', 'language')
    op.drop_column('users', 'timezone')
    op.drop_column('users', 'job_title')
    op.drop_column('users', 'phone')
