"""Subtree queries (closure table) and as-of-date lookups (assignments, reporting
lines, unit heads) for the platform org tree. Requires Postgres — see conftest.py.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.modules.platform.models.org_unit import OrgUnitType
from app.modules.platform.services import org_tree

pytestmark = pytest.mark.postgres


def _build_branch_tree(pg_session, org_id):
    """Organization -> Branch -> Department -> Team, plus a sibling Branch."""
    root = org_tree.create_unit(pg_session, org_id, OrgUnitType.ORGANIZATION, "Acme")
    branch = org_tree.create_unit(pg_session, org_id, OrgUnitType.BRANCH, "Colombo Branch", parent_id=root.id)
    dept = org_tree.create_unit(
        pg_session, org_id, OrgUnitType.DEPARTMENT, "Engineering", parent_id=branch.id, function_tag="Engineering"
    )
    team = org_tree.create_unit(pg_session, org_id, OrgUnitType.TEAM, "Platform Team", parent_id=dept.id)
    other_branch = org_tree.create_unit(pg_session, org_id, OrgUnitType.BRANCH, "Kandy Branch", parent_id=root.id)
    return root, branch, dept, team, other_branch


class TestSubtreeQueries:
    def test_subtree_includes_all_descendants(self, pg_session, make_org):
        org_id = make_org()
        root, branch, dept, team, other_branch = _build_branch_tree(pg_session, org_id)

        subtree = set(org_tree.get_subtree_ids(pg_session, org_id, root.id))
        assert subtree == {root.id, branch.id, dept.id, team.id, other_branch.id}

        branch_subtree = set(org_tree.get_subtree_ids(pg_session, org_id, branch.id))
        assert branch_subtree == {branch.id, dept.id, team.id}
        assert other_branch.id not in branch_subtree

    def test_subtree_of_leaf_is_itself(self, pg_session, make_org):
        org_id = make_org()
        _, _, _, team, _ = _build_branch_tree(pg_session, org_id)
        assert org_tree.get_subtree_ids(pg_session, org_id, team.id) == [team.id]

    def test_ancestors_ordered_nearest_first(self, pg_session, make_org):
        org_id = make_org()
        root, branch, dept, team, _ = _build_branch_tree(pg_session, org_id)
        ancestors = org_tree.get_ancestor_ids(pg_session, org_id, team.id)
        assert ancestors == [team.id, dept.id, branch.id, root.id]

    def test_move_unit_updates_subtree(self, pg_session, make_org):
        org_id = make_org()
        root, branch, dept, team, other_branch = _build_branch_tree(pg_session, org_id)

        org_tree.move_unit(pg_session, org_id, dept.id, other_branch.id)

        assert set(org_tree.get_subtree_ids(pg_session, org_id, branch.id)) == {branch.id}
        assert set(org_tree.get_subtree_ids(pg_session, org_id, other_branch.id)) == {other_branch.id, dept.id, team.id}
        assert org_tree.get_ancestor_ids(pg_session, org_id, team.id) == [team.id, dept.id, other_branch.id, root.id]

    def test_move_unit_rejects_move_into_own_subtree(self, pg_session, make_org):
        org_id = make_org()
        _, branch, dept, _, _ = _build_branch_tree(pg_session, org_id)
        with pytest.raises(ValueError):
            org_tree.move_unit(pg_session, org_id, branch.id, dept.id)

    def test_subtree_is_scoped_to_org(self, pg_session, make_org):
        org_a = make_org(slug="org-a")
        org_b = make_org(slug="org-b")
        root_a = org_tree.create_unit(pg_session, org_a, OrgUnitType.ORGANIZATION, "Org A")
        root_b = org_tree.create_unit(pg_session, org_b, OrgUnitType.ORGANIZATION, "Org B")

        assert org_tree.get_subtree_ids(pg_session, org_a, root_a.id) == [root_a.id]
        # Querying org B's unit under org A's scope finds nothing — org_id is part
        # of the closure lookup, not just the unit id.
        assert org_tree.get_subtree_ids(pg_session, org_a, root_b.id) == []


class TestAsOfDateLookups:
    def test_subtree_as_of_excludes_units_not_yet_created(self, pg_session, make_org):
        org_id = make_org()
        root = org_tree.create_unit(pg_session, org_id, OrgUnitType.ORGANIZATION, "Acme")
        before = datetime.now(timezone.utc)
        branch = org_tree.create_unit(
            pg_session, org_id, OrgUnitType.BRANCH, "New Branch", parent_id=root.id,
            valid_from=datetime.now(timezone.utc) + timedelta(days=1),
        )

        as_of_before = set(org_tree.get_subtree_ids(pg_session, org_id, root.id, as_of=before))
        assert branch.id not in as_of_before

        as_of_after = set(org_tree.get_subtree_ids(pg_session, org_id, root.id, as_of=datetime.now(timezone.utc) + timedelta(days=2)))
        assert branch.id in as_of_after

    def test_assignment_as_of_date(self, pg_session, make_org):
        org_id = make_org()
        root = org_tree.create_unit(pg_session, org_id, OrgUnitType.ORGANIZATION, "Acme")
        branch = org_tree.create_unit(pg_session, org_id, OrgUnitType.BRANCH, "Branch", parent_id=root.id)
        person_id = uuid.uuid4()

        t0 = datetime.now(timezone.utc) - timedelta(days=10)
        t1 = datetime.now(timezone.utc) - timedelta(days=5)

        old_unit = org_tree.create_unit(pg_session, org_id, OrgUnitType.DEPARTMENT, "Old Dept", parent_id=root.id, valid_from=t0)
        assignment = org_tree.assign_person(pg_session, org_id, old_unit.id, person_id, valid_from=t0)
        assignment.valid_to = t1
        org_tree.assign_person(pg_session, org_id, branch.id, person_id, valid_from=t1)
        pg_session.flush()

        before_switch = org_tree.get_assignment_as_of(pg_session, org_id, person_id, as_of=t0 + timedelta(days=1))
        assert before_switch.unit_id == old_unit.id

        after_switch = org_tree.get_assignment_as_of(pg_session, org_id, person_id, as_of=t1 + timedelta(days=1))
        assert after_switch.unit_id == branch.id

    def test_manager_as_of_date(self, pg_session, make_org):
        org_id = make_org()
        person_id, manager_a, manager_b = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

        t0 = datetime.now(timezone.utc) - timedelta(days=10)
        t1 = datetime.now(timezone.utc) - timedelta(days=5)

        line_a = org_tree.add_reporting_line(pg_session, org_id, person_id, manager_a, valid_from=t0)
        line_a.valid_to = t1
        org_tree.add_reporting_line(pg_session, org_id, person_id, manager_b, valid_from=t1)
        pg_session.flush()

        assert org_tree.get_manager_as_of(pg_session, org_id, person_id, as_of=t0 + timedelta(days=1)) == manager_a
        assert org_tree.get_manager_as_of(pg_session, org_id, person_id, as_of=t1 + timedelta(days=1)) == manager_b

    def test_reporting_line_rejects_self_management(self, pg_session, make_org):
        org_id = make_org()
        person_id = uuid.uuid4()
        with pytest.raises(ValueError):
            org_tree.add_reporting_line(pg_session, org_id, person_id, person_id)

    def test_unit_head_as_of_date_and_single_open_head(self, pg_session, make_org):
        org_id = make_org()
        root = org_tree.create_unit(pg_session, org_id, OrgUnitType.ORGANIZATION, "Acme")
        dept = org_tree.create_unit(pg_session, org_id, OrgUnitType.DEPARTMENT, "Finance", parent_id=root.id)
        head_a, head_b = uuid.uuid4(), uuid.uuid4()

        t0 = datetime.now(timezone.utc) - timedelta(days=30)
        t1 = datetime.now(timezone.utc) - timedelta(days=1)

        org_tree.set_unit_head(pg_session, org_id, dept.id, head_a, valid_from=t0)
        org_tree.set_unit_head(pg_session, org_id, dept.id, head_b, valid_from=t1)
        pg_session.flush()

        assert org_tree.get_unit_head_as_of(pg_session, org_id, dept.id, as_of=t0 + timedelta(days=1)) == head_a
        assert org_tree.get_unit_head_as_of(pg_session, org_id, dept.id, as_of=t1 + timedelta(hours=1)) == head_b

        # exactly one open-ended head record at a time
        from sqlalchemy import select, func
        from app.modules.platform.models.org_unit_head import OrgUnitHead
        open_count = pg_session.execute(
            select(func.count()).select_from(OrgUnitHead).where(
                OrgUnitHead.org_id == org_id, OrgUnitHead.unit_id == dept.id, OrgUnitHead.valid_to.is_(None)
            )
        ).scalar()
        assert open_count == 1
