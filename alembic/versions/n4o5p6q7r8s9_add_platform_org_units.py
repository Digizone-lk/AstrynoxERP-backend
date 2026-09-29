"""add platform org_units tree

Revision ID: n4o5p6q7r8s9
Revises: m3n4o5p6q7r8
Create Date: 2026-09-28 00:00:00.000000

Adds the platform module's effective-dated org tree:
  - org_units: one row per unit, free-text unit_type + parent_id (pure tree).
    The row with parent_id IS NULL is the tenant's root and represents the
    organization itself; at most one root is allowed per org_id.
  - org_unit_closures: materialized transitive closure of the current tree,
    for fast subtree/ancestor queries.
  - org_unit_assignments / org_unit_reporting_lines / org_unit_heads: effective-dated
    (valid_from/valid_to) tables, kept separate from tree position per docs/prd.md.

Every table carries org_id and gets a Postgres row-level security policy scoped to
current_setting('app.current_org_id'). RLS only restricts non-superuser, non-owner
roles (or owners under FORCE ROW LEVEL SECURITY) — the application's runtime DB role
must not be a superuser and must not bypass RLS for these policies to take effect.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'n4o5p6q7r8s9'
down_revision: Union[str, None] = 'm3n4o5p6q7r8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLES = [
    "org_unit_heads",
    "org_unit_reporting_lines",
    "org_unit_assignments",
    "org_unit_closures",
    "org_units",
]


def upgrade() -> None:
    op.create_table(
        'org_units',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('org_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('unit_type', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('parent_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('function_tag', sa.String(length=100), nullable=True),
        sa.Column('valid_from', sa.DateTime(timezone=True), nullable=False),
        sa.Column('valid_to', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['parent_id'], ['org_units.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_org_units_org_id'), 'org_units', ['org_id'], unique=False)
    op.create_index(op.f('ix_org_units_parent_id'), 'org_units', ['parent_id'], unique=False)
    op.create_index('ix_org_units_org_id_unit_type', 'org_units', ['org_id', 'unit_type'], unique=False)
    # At most one root (parent_id IS NULL) per tenant.
    op.create_index(
        'uq_org_units_single_root',
        'org_units',
        ['org_id'],
        unique=True,
        postgresql_where=sa.text('parent_id IS NULL'),
    )

    op.create_table(
        'org_unit_closures',
        sa.Column('ancestor_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('descendant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('depth', sa.Integer(), nullable=False),
        sa.Column('org_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(['ancestor_id'], ['org_units.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['descendant_id'], ['org_units.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('ancestor_id', 'descendant_id'),
    )
    op.create_index(op.f('ix_org_unit_closures_org_id'), 'org_unit_closures', ['org_id'], unique=False)
    op.create_index('ix_org_unit_closures_descendant_id', 'org_unit_closures', ['descendant_id'], unique=False)

    op.create_table(
        'org_unit_assignments',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('org_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('unit_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('person_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('position_title', sa.String(length=255), nullable=True),
        sa.Column('valid_from', sa.DateTime(timezone=True), nullable=False),
        sa.Column('valid_to', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['unit_id'], ['org_units.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_org_unit_assignments_org_id'), 'org_unit_assignments', ['org_id'], unique=False)
    op.create_index(op.f('ix_org_unit_assignments_unit_id'), 'org_unit_assignments', ['unit_id'], unique=False)
    op.create_index(op.f('ix_org_unit_assignments_person_id'), 'org_unit_assignments', ['person_id'], unique=False)
    op.create_index('ix_org_unit_assignments_org_person', 'org_unit_assignments', ['org_id', 'person_id'], unique=False)
    op.create_index('ix_org_unit_assignments_org_unit', 'org_unit_assignments', ['org_id', 'unit_id'], unique=False)

    op.create_table(
        'org_unit_reporting_lines',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('org_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('person_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('manager_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('valid_from', sa.DateTime(timezone=True), nullable=False),
        sa.Column('valid_to', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint('person_id <> manager_id', name='ck_reporting_line_no_self_management'),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_org_unit_reporting_lines_org_id'), 'org_unit_reporting_lines', ['org_id'], unique=False)
    op.create_index(op.f('ix_org_unit_reporting_lines_person_id'), 'org_unit_reporting_lines', ['person_id'], unique=False)
    op.create_index(op.f('ix_org_unit_reporting_lines_manager_id'), 'org_unit_reporting_lines', ['manager_id'], unique=False)
    op.create_index('ix_org_unit_reporting_lines_org_person', 'org_unit_reporting_lines', ['org_id', 'person_id'], unique=False)
    op.create_index('ix_org_unit_reporting_lines_org_manager', 'org_unit_reporting_lines', ['org_id', 'manager_id'], unique=False)

    op.create_table(
        'org_unit_heads',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('org_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('unit_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('person_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('valid_from', sa.DateTime(timezone=True), nullable=False),
        sa.Column('valid_to', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['unit_id'], ['org_units.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_org_unit_heads_org_id'), 'org_unit_heads', ['org_id'], unique=False)
    op.create_index(op.f('ix_org_unit_heads_unit_id'), 'org_unit_heads', ['unit_id'], unique=False)
    op.create_index(op.f('ix_org_unit_heads_person_id'), 'org_unit_heads', ['person_id'], unique=False)
    op.create_index('ix_org_unit_heads_org_unit', 'org_unit_heads', ['org_id', 'unit_id'], unique=False)

    # Row-level security: every platform table is scoped to the tenant set via
    # `SET LOCAL app.current_org_id = '<uuid>'` for the current transaction
    # (app.modules.platform.db.set_tenant_context). `current_setting(..., true)`
    # returns NULL when unset, so an unset context yields zero visible rows.
    for table in TABLES:
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
        # NULLIF guards against custom GUCs that read back as '' (rather than NULL)
        # once referenced in a pooled backend that never actually SET a value —
        # '' would otherwise fail the ::uuid cast instead of failing closed.
        op.execute(
            f"""
            CREATE POLICY {table}_tenant_isolation ON {table}
            USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)
            WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)
            """
        )


def downgrade() -> None:
    for table in TABLES:
        op.execute(f'DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}')
        op.execute(f'ALTER TABLE {table} DISABLE ROW LEVEL SECURITY')

    op.drop_index('ix_org_unit_heads_org_unit', table_name='org_unit_heads')
    op.drop_index(op.f('ix_org_unit_heads_person_id'), table_name='org_unit_heads')
    op.drop_index(op.f('ix_org_unit_heads_unit_id'), table_name='org_unit_heads')
    op.drop_index(op.f('ix_org_unit_heads_org_id'), table_name='org_unit_heads')
    op.drop_table('org_unit_heads')

    op.drop_index('ix_org_unit_reporting_lines_org_manager', table_name='org_unit_reporting_lines')
    op.drop_index('ix_org_unit_reporting_lines_org_person', table_name='org_unit_reporting_lines')
    op.drop_index(op.f('ix_org_unit_reporting_lines_manager_id'), table_name='org_unit_reporting_lines')
    op.drop_index(op.f('ix_org_unit_reporting_lines_person_id'), table_name='org_unit_reporting_lines')
    op.drop_index(op.f('ix_org_unit_reporting_lines_org_id'), table_name='org_unit_reporting_lines')
    op.drop_table('org_unit_reporting_lines')

    op.drop_index('ix_org_unit_assignments_org_unit', table_name='org_unit_assignments')
    op.drop_index('ix_org_unit_assignments_org_person', table_name='org_unit_assignments')
    op.drop_index(op.f('ix_org_unit_assignments_person_id'), table_name='org_unit_assignments')
    op.drop_index(op.f('ix_org_unit_assignments_unit_id'), table_name='org_unit_assignments')
    op.drop_index(op.f('ix_org_unit_assignments_org_id'), table_name='org_unit_assignments')
    op.drop_table('org_unit_assignments')

    op.drop_index('ix_org_unit_closures_descendant_id', table_name='org_unit_closures')
    op.drop_index(op.f('ix_org_unit_closures_org_id'), table_name='org_unit_closures')
    op.drop_table('org_unit_closures')

    op.drop_index('uq_org_units_single_root', table_name='org_units')
    op.drop_index('ix_org_units_org_id_unit_type', table_name='org_units')
    op.drop_index(op.f('ix_org_units_parent_id'), table_name='org_units')
    op.drop_index(op.f('ix_org_units_org_id'), table_name='org_units')
    op.drop_table('org_units')
