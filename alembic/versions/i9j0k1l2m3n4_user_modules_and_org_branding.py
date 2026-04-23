"""add user allowed_modules and org branding fields

Revision ID: i9j0k1l2m3n4
Revises: h8i9j0k1l2m3
Create Date: 2026-04-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'i9j0k1l2m3n4'
down_revision = 'h8i9j0k1l2m3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- users: module access control ---
    op.add_column('users', sa.Column('allowed_modules', sa.JSON(), nullable=True))

    # --- organizations: PDF branding ---
    op.add_column('organizations', sa.Column('address', sa.Text(), nullable=True))
    op.add_column('organizations', sa.Column('phone', sa.String(50), nullable=True))
    op.add_column('organizations', sa.Column('email', sa.String(255), nullable=True))
    op.add_column('organizations', sa.Column('website', sa.String(255), nullable=True))
    op.add_column('organizations', sa.Column('logo_url', sa.String(500), nullable=True))
    op.add_column('organizations', sa.Column(
        'pdf_template', sa.String(20), nullable=False, server_default='classic'
    ))


def downgrade() -> None:
    op.drop_column('users', 'allowed_modules')
    op.drop_column('organizations', 'address')
    op.drop_column('organizations', 'phone')
    op.drop_column('organizations', 'email')
    op.drop_column('organizations', 'website')
    op.drop_column('organizations', 'logo_url')
    op.drop_column('organizations', 'pdf_template')
