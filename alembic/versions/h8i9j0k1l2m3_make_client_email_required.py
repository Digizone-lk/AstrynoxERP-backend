"""make client email required

Revision ID: h8i9j0k1l2m3
Revises: g7h8i9j0k1l2
Create Date: 2026-04-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'h8i9j0k1l2m3'
down_revision = 'g7h8i9j0k1l2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Step 1: Backfill existing rows that have NULL email with a placeholder.
    # Uses the first 8 chars of the UUID so each placeholder is unique and
    # identifiable. Admins can update these after the migration.
    op.execute("""
        UPDATE clients
        SET email = 'noemail-' || SUBSTRING(CAST(id AS TEXT), 1, 8) || '@placeholder.invalid'
        WHERE email IS NULL
    """)

    # Step 2: Now it is safe to add the NOT NULL constraint.
    op.alter_column('clients', 'email', nullable=False)


def downgrade() -> None:
    op.alter_column('clients', 'email', nullable=True)
