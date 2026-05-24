"""add trials invites and onboarding

Revision ID: j0k1l2m3n4o5
Revises: i9j0k1l2m3n4
Create Date: 2026-05-24 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'j0k1l2m3n4o5'
down_revision = 'i9j0k1l2m3n4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('organizations', sa.Column('subscription_status', sa.String(20), nullable=False, server_default='trial'))
    op.add_column('organizations', sa.Column('plan', sa.String(20), nullable=True))
    op.add_column('organizations', sa.Column('trial_start_date', sa.DateTime(timezone=True), nullable=True))
    op.add_column('organizations', sa.Column('trial_end_date', sa.DateTime(timezone=True), nullable=True))
    op.add_column('organizations', sa.Column('paid_activated_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('organizations', sa.Column('paid_activated_by', sa.String(255), nullable=True))
    op.add_column('organizations', sa.Column('onboarding_status', sa.String(30), nullable=False, server_default='completed'))

    op.execute("UPDATE organizations SET subscription_status = 'trial', trial_start_date = NOW(), trial_end_date = NOW() + INTERVAL '14 days', onboarding_status = 'completed'")

    op.add_column('users', sa.Column('username', sa.String(100), nullable=True))
    op.add_column('users', sa.Column('must_change_password', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('users', sa.Column('email_verified', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)

    op.create_table(
        'organization_invites',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('org_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('username', sa.String(100), nullable=False),
        sa.Column('token_hash', sa.String(64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('opened_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('device_fingerprint', sa.String(64), nullable=True),
        sa.Column('created_by', sa.String(255), nullable=False),
        sa.Column('invalidated', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_organization_invites_email'), 'organization_invites', ['email'], unique=False)
    op.create_index(op.f('ix_organization_invites_org_id'), 'organization_invites', ['org_id'], unique=False)
    op.create_index(op.f('ix_organization_invites_token_hash'), 'organization_invites', ['token_hash'], unique=True)
    op.create_index(op.f('ix_organization_invites_user_id'), 'organization_invites', ['user_id'], unique=False)
    op.create_index(op.f('ix_organization_invites_username'), 'organization_invites', ['username'], unique=False)

    op.create_table(
        'onboarding_otps',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('otp_hash', sa.String(64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_onboarding_otps_otp_hash'), 'onboarding_otps', ['otp_hash'], unique=False)
    op.create_index(op.f('ix_onboarding_otps_user_id'), 'onboarding_otps', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_onboarding_otps_user_id'), table_name='onboarding_otps')
    op.drop_index(op.f('ix_onboarding_otps_otp_hash'), table_name='onboarding_otps')
    op.drop_table('onboarding_otps')

    op.drop_index(op.f('ix_organization_invites_username'), table_name='organization_invites')
    op.drop_index(op.f('ix_organization_invites_user_id'), table_name='organization_invites')
    op.drop_index(op.f('ix_organization_invites_token_hash'), table_name='organization_invites')
    op.drop_index(op.f('ix_organization_invites_org_id'), table_name='organization_invites')
    op.drop_index(op.f('ix_organization_invites_email'), table_name='organization_invites')
    op.drop_table('organization_invites')

    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_column('users', 'email_verified')
    op.drop_column('users', 'must_change_password')
    op.drop_column('users', 'username')

    op.drop_column('organizations', 'onboarding_status')
    op.drop_column('organizations', 'paid_activated_by')
    op.drop_column('organizations', 'paid_activated_at')
    op.drop_column('organizations', 'trial_end_date')
    op.drop_column('organizations', 'trial_start_date')
    op.drop_column('organizations', 'plan')
    op.drop_column('organizations', 'subscription_status')
