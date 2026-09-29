"""Row-level security isolation between two orgs on every platform table.

Queries run as a non-superuser role (RLS is bypassed by superusers and, without
FORCE ROW LEVEL SECURITY, by table owners — see conftest.py's platform_rls_test_role)
scoped via app.modules.platform.db.set_tenant_context, the same mechanism the app
uses. Requires Postgres — see conftest.py.
"""
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.modules.platform.models.org_unit import OrgUnit, OrgUnitType
from app.modules.platform.models.org_unit_closure import OrgUnitClosure
from app.modules.platform.models.org_unit_assignment import OrgUnitAssignment
from app.modules.platform.models.org_unit_reporting_line import OrgUnitReportingLine
from app.modules.platform.models.org_unit_head import OrgUnitHead
from app.modules.platform.services import org_tree

pytestmark = pytest.mark.postgres


@pytest.fixture()
def two_orgs_with_units(pg_session, make_org):
    """Seed full org trees + assignments/reporting lines/heads for two tenants,
    as the elevated (table-owner/superuser) connection — before RLS is engaged."""
    org_a = make_org(slug="org-a")
    org_b = make_org(slug="org-b")

    root_a = org_tree.create_unit(pg_session, org_a, OrgUnitType.ORGANIZATION, "Org A")
    dept_a = org_tree.create_unit(pg_session, org_a, OrgUnitType.DEPARTMENT, "Org A Dept", parent_id=root_a.id)
    person_a = uuid.uuid4()
    manager_a = uuid.uuid4()
    org_tree.assign_person(pg_session, org_a, dept_a.id, person_a)
    org_tree.add_reporting_line(pg_session, org_a, person_a, manager_a)
    org_tree.set_unit_head(pg_session, org_a, dept_a.id, manager_a)

    root_b = org_tree.create_unit(pg_session, org_b, OrgUnitType.ORGANIZATION, "Org B")
    dept_b = org_tree.create_unit(pg_session, org_b, OrgUnitType.DEPARTMENT, "Org B Dept", parent_id=root_b.id)
    person_b = uuid.uuid4()
    manager_b = uuid.uuid4()
    org_tree.assign_person(pg_session, org_b, dept_b.id, person_b)
    org_tree.add_reporting_line(pg_session, org_b, person_b, manager_b)
    org_tree.set_unit_head(pg_session, org_b, dept_b.id, manager_b)

    pg_session.flush()
    return {
        "org_a": org_a, "root_a": root_a, "dept_a": dept_a, "person_a": person_a, "manager_a": manager_a,
        "org_b": org_b, "root_b": root_b, "dept_b": dept_b, "person_b": person_b, "manager_b": manager_b,
    }


def test_org_units_isolated_by_tenant(pg_session, as_tenant, two_orgs_with_units):
    ctx = two_orgs_with_units
    as_tenant(ctx["org_a"])

    rows = pg_session.execute(select(OrgUnit)).scalars().all()
    seen_ids = {row.id for row in rows}
    assert ctx["root_a"].id in seen_ids and ctx["dept_a"].id in seen_ids
    assert ctx["root_b"].id not in seen_ids and ctx["dept_b"].id not in seen_ids
    assert all(row.org_id == ctx["org_a"] for row in rows)


def test_org_unit_closures_isolated_by_tenant(pg_session, as_tenant, two_orgs_with_units):
    ctx = two_orgs_with_units
    as_tenant(ctx["org_a"])

    rows = pg_session.execute(select(OrgUnitClosure)).scalars().all()
    descendants = {row.descendant_id for row in rows}
    assert ctx["dept_a"].id in descendants
    assert ctx["dept_b"].id not in descendants


def test_org_unit_assignments_isolated_by_tenant(pg_session, as_tenant, two_orgs_with_units):
    ctx = two_orgs_with_units
    as_tenant(ctx["org_a"])

    rows = pg_session.execute(select(OrgUnitAssignment)).scalars().all()
    person_ids = {row.person_id for row in rows}
    assert ctx["person_a"] in person_ids
    assert ctx["person_b"] not in person_ids


def test_org_unit_reporting_lines_isolated_by_tenant(pg_session, as_tenant, two_orgs_with_units):
    ctx = two_orgs_with_units
    as_tenant(ctx["org_a"])

    rows = pg_session.execute(select(OrgUnitReportingLine)).scalars().all()
    person_ids = {row.person_id for row in rows}
    assert ctx["person_a"] in person_ids
    assert ctx["person_b"] not in person_ids


def test_org_unit_heads_isolated_by_tenant(pg_session, as_tenant, two_orgs_with_units):
    ctx = two_orgs_with_units
    as_tenant(ctx["org_a"])

    rows = pg_session.execute(select(OrgUnitHead)).scalars().all()
    unit_ids = {row.unit_id for row in rows}
    assert ctx["dept_a"].id in unit_ids
    assert ctx["dept_b"].id not in unit_ids


def test_switching_tenant_context_flips_visibility(pg_session, as_tenant, two_orgs_with_units):
    ctx = two_orgs_with_units

    as_tenant(ctx["org_a"])
    ids_as_a = {row.id for row in pg_session.execute(select(OrgUnit)).scalars().all()}
    assert ids_as_a == {ctx["root_a"].id, ctx["dept_a"].id}

    as_tenant(ctx["org_b"])
    ids_as_b = {row.id for row in pg_session.execute(select(OrgUnit)).scalars().all()}
    assert ids_as_b == {ctx["root_b"].id, ctx["dept_b"].id}


def test_no_tenant_context_set_sees_nothing(pg_session, two_orgs_with_units):
    """Fail closed: without SET LOCAL app.current_org_id, current_setting(...) is
    NULL and the policy `org_id = NULL` matches no rows."""
    pg_session.execute(text("SET LOCAL ROLE platform_rls_test_role"))
    rows = pg_session.execute(select(OrgUnit)).scalars().all()
    assert rows == []


def test_cross_tenant_insert_is_rejected(pg_session, as_tenant, two_orgs_with_units):
    """WITH CHECK blocks writing a row tagged with a different org_id than the
    session's current tenant context, even from a legitimate write path."""
    ctx = two_orgs_with_units
    as_tenant(ctx["org_a"])

    with pytest.raises(DBAPIError):
        pg_session.execute(
            text("INSERT INTO org_units (id, org_id, unit_type, name, valid_from) "
                 "VALUES (:id, :org_id, 'branch', 'Sneaky Branch', :valid_from)"),
            {"id": uuid.uuid4(), "org_id": ctx["org_b"], "valid_from": datetime.now(timezone.utc)},
        )
        pg_session.flush()


def test_cross_tenant_update_affects_no_rows(pg_session, as_tenant, two_orgs_with_units):
    """USING blocks even seeing/updating another tenant's row by id."""
    ctx = two_orgs_with_units
    as_tenant(ctx["org_a"])

    result = pg_session.execute(
        text("UPDATE org_units SET name = 'hijacked' WHERE id = :id"),
        {"id": ctx["dept_b"].id},
    )
    assert result.rowcount == 0
