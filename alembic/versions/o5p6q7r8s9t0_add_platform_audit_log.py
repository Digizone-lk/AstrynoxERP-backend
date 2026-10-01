"""add platform audit log

Revision ID: o5p6q7r8s9t0
Revises: n4o5p6q7r8s9
Create Date: 2026-09-29 00:00:00.000000

Adds the shared platform audit log (platform_audit_logs), used across modules —
distinct from ims's existing `audit_logs` table, which stays as-is for BillFlow.

actor_id is not FK'd to `users` (platform doesn't own that table; see the model
docstring). org_id FK's to organizations.id and gets the same RLS treatment as
every other platform table (see n4o5p6q7r8s9_add_platform_org_units.py).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'o5p6q7r8s9t0'
down_revision: Union[str, None] = 'n4o5p6q7r8s9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "platform_audit_logs"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('org_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('actor_type', sa.String(length=20), nullable=False),
        sa.Column('actor_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('actor_label', sa.String(length=255), nullable=True),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('resource_type', sa.String(length=100), nullable=False),
        sa.Column('resource_id', sa.String(length=255), nullable=True),
        sa.Column('before_data', sa.JSON(), nullable=True),
        sa.Column('after_data', sa.JSON(), nullable=True),
        sa.Column('extra_data', sa.JSON(), nullable=True),
        sa.Column('ip_address', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f(f'ix_{TABLE}_org_id'), TABLE, ['org_id'], unique=False)
    op.create_index(op.f(f'ix_{TABLE}_actor_id'), TABLE, ['actor_id'], unique=False)
    op.create_index(op.f(f'ix_{TABLE}_created_at'), TABLE, ['created_at'], unique=False)
    op.create_index(f'ix_{TABLE}_org_resource', TABLE, ['org_id', 'resource_type', 'resource_id'], unique=False)
    op.create_index(f'ix_{TABLE}_org_created_at', TABLE, ['org_id', 'created_at'], unique=False)

    # Same RLS pattern as every other platform table — see
    # n4o5p6q7r8s9_add_platform_org_units.py for the NULLIF rationale.
    op.execute(f'ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY')
    op.execute(
        f"""
        CREATE POLICY {TABLE}_tenant_isolation ON {TABLE}
        USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)
        WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)
        """
    )


def downgrade() -> None:
    op.execute(f'DROP POLICY IF EXISTS {TABLE}_tenant_isolation ON {TABLE}')
    op.execute(f'ALTER TABLE {TABLE} DISABLE ROW LEVEL SECURITY')

    op.drop_index(f'ix_{TABLE}_org_created_at', table_name=TABLE)
    op.drop_index(f'ix_{TABLE}_org_resource', table_name=TABLE)
    op.drop_index(op.f(f'ix_{TABLE}_created_at'), table_name=TABLE)
    op.drop_index(op.f(f'ix_{TABLE}_actor_id'), table_name=TABLE)
    op.drop_index(op.f(f'ix_{TABLE}_org_id'), table_name=TABLE)
    op.drop_table(TABLE)
