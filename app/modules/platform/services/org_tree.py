"""Org tree operations: unit CRUD with closure-table maintenance, subtree/ancestor
queries, and effective-dated lookups for assignments, reporting lines and unit heads.

All functions take an explicit org_id and filter every query by it, even though RLS
also enforces isolation at the database level — defense in depth, and it keeps the
service usable against a session that hasn't had set_tenant_context() called on it.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, insert, delete
from sqlalchemy.orm import Session

from app.modules.platform.models.org_unit import OrgUnit
from app.modules.platform.models.org_unit_closure import OrgUnitClosure
from app.modules.platform.models.org_unit_assignment import OrgUnitAssignment
from app.modules.platform.models.org_unit_reporting_line import OrgUnitReportingLine
from app.modules.platform.models.org_unit_head import OrgUnitHead


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ─── Unit tree ────────────────────────────────────────────────────────────────

def create_unit(
    db: Session,
    org_id: uuid.UUID,
    unit_type: str,
    name: str,
    parent_id: Optional[uuid.UUID] = None,
    function_tag: Optional[str] = None,
    valid_from: Optional[datetime] = None,
) -> OrgUnit:
    """Create a unit and seed its closure-table rows (self row, plus one row per
    ancestor of parent_id, at ancestor_depth + 1)."""
    unit = OrgUnit(
        org_id=org_id,
        unit_type=unit_type,
        name=name,
        parent_id=parent_id,
        function_tag=function_tag,
        valid_from=valid_from or _now(),
    )
    db.add(unit)
    db.flush()  # assigns unit.id

    db.execute(
        insert(OrgUnitClosure).values(ancestor_id=unit.id, descendant_id=unit.id, depth=0, org_id=org_id)
    )

    if parent_id is not None:
        parent_ancestors = db.execute(
            select(OrgUnitClosure.ancestor_id, OrgUnitClosure.depth)
            .where(OrgUnitClosure.descendant_id == parent_id, OrgUnitClosure.org_id == org_id)
        ).all()
        for ancestor_id, depth in parent_ancestors:
            db.execute(
                insert(OrgUnitClosure).values(
                    ancestor_id=ancestor_id, descendant_id=unit.id, depth=depth + 1, org_id=org_id
                )
            )

    db.flush()
    return unit


def move_unit(db: Session, org_id: uuid.UUID, unit_id: uuid.UUID, new_parent_id: Optional[uuid.UUID]) -> None:
    """Reparent a unit (and its whole subtree) under new_parent_id, keeping the
    closure table consistent. Standard closure-table "move subtree" algorithm:
    detach the subtree from its old ancestors, then reattach it under the new ones.
    """
    unit = db.get(OrgUnit, unit_id)
    if unit is None or unit.org_id != org_id:
        raise ValueError("unit not found")
    if new_parent_id == unit_id:
        raise ValueError("a unit cannot be its own parent")

    subtree_ids = [
        row[0]
        for row in db.execute(
            select(OrgUnitClosure.descendant_id)
            .where(OrgUnitClosure.ancestor_id == unit_id, OrgUnitClosure.org_id == org_id)
        ).all()
    ]
    if new_parent_id in subtree_ids:
        raise ValueError("cannot move a unit into its own subtree")

    # Detach: remove closure rows linking any strict ancestor of `unit` to any node
    # in `unit`'s subtree (but keep the subtree's internal closure rows intact).
    db.execute(
        delete(OrgUnitClosure).where(
            OrgUnitClosure.descendant_id.in_(
                select(OrgUnitClosure.descendant_id).where(
                    OrgUnitClosure.ancestor_id == unit_id, OrgUnitClosure.org_id == org_id
                )
            ),
            OrgUnitClosure.ancestor_id.in_(
                select(OrgUnitClosure.ancestor_id).where(
                    OrgUnitClosure.descendant_id == unit_id,
                    OrgUnitClosure.ancestor_id != unit_id,
                    OrgUnitClosure.org_id == org_id,
                )
            ),
        )
    )

    unit.parent_id = new_parent_id
    db.flush()

    # Reattach: cross join new ancestors (incl. new parent itself) x subtree nodes.
    if new_parent_id is not None:
        new_ancestors = db.execute(
            select(OrgUnitClosure.ancestor_id, OrgUnitClosure.depth)
            .where(OrgUnitClosure.descendant_id == new_parent_id, OrgUnitClosure.org_id == org_id)
        ).all()
        subtree_rows = db.execute(
            select(OrgUnitClosure.descendant_id, OrgUnitClosure.depth)
            .where(OrgUnitClosure.ancestor_id == unit_id, OrgUnitClosure.org_id == org_id)
        ).all()
        for ancestor_id, ancestor_depth in new_ancestors:
            for descendant_id, sub_depth in subtree_rows:
                db.execute(
                    insert(OrgUnitClosure).values(
                        ancestor_id=ancestor_id,
                        descendant_id=descendant_id,
                        depth=ancestor_depth + 1 + sub_depth,
                        org_id=org_id,
                    )
                )
    db.flush()


def get_subtree_ids(
    db: Session, org_id: uuid.UUID, unit_id: uuid.UUID, as_of: Optional[datetime] = None
) -> list[uuid.UUID]:
    """All descendant unit ids (including unit_id itself), via the closure table.

    When `as_of` is given, only units whose own [valid_from, valid_to) window covers
    that instant are included — i.e. units that existed at that point in time.
    """
    query = (
        select(OrgUnitClosure.descendant_id)
        .join(OrgUnit, OrgUnit.id == OrgUnitClosure.descendant_id)
        .where(OrgUnitClosure.ancestor_id == unit_id, OrgUnitClosure.org_id == org_id)
    )
    if as_of is not None:
        query = query.where(
            OrgUnit.valid_from <= as_of,
            (OrgUnit.valid_to.is_(None)) | (OrgUnit.valid_to > as_of),
        )
    return [row[0] for row in db.execute(query).all()]


def get_ancestor_ids(db: Session, org_id: uuid.UUID, unit_id: uuid.UUID) -> list[uuid.UUID]:
    """All ancestor unit ids (including unit_id itself), ordered nearest-first."""
    query = (
        select(OrgUnitClosure.ancestor_id)
        .where(OrgUnitClosure.descendant_id == unit_id, OrgUnitClosure.org_id == org_id)
        .order_by(OrgUnitClosure.depth)
    )
    return [row[0] for row in db.execute(query).all()]


# ─── Assignments (person -> unit) ──────────────────────────────────────────────

def assign_person(
    db: Session,
    org_id: uuid.UUID,
    unit_id: uuid.UUID,
    person_id: uuid.UUID,
    position_title: Optional[str] = None,
    valid_from: Optional[datetime] = None,
) -> OrgUnitAssignment:
    assignment = OrgUnitAssignment(
        org_id=org_id,
        unit_id=unit_id,
        person_id=person_id,
        position_title=position_title,
        valid_from=valid_from or _now(),
    )
    db.add(assignment)
    db.flush()
    return assignment


def get_assignment_as_of(
    db: Session, org_id: uuid.UUID, person_id: uuid.UUID, as_of: Optional[datetime] = None
) -> Optional[OrgUnitAssignment]:
    as_of = as_of or _now()
    query = (
        select(OrgUnitAssignment)
        .where(
            OrgUnitAssignment.org_id == org_id,
            OrgUnitAssignment.person_id == person_id,
            OrgUnitAssignment.valid_from <= as_of,
            (OrgUnitAssignment.valid_to.is_(None)) | (OrgUnitAssignment.valid_to > as_of),
        )
        .order_by(OrgUnitAssignment.valid_from.desc())
        .limit(1)
    )
    return db.execute(query).scalars().first()


# ─── Reporting lines (person -> manager) ───────────────────────────────────────

def add_reporting_line(
    db: Session,
    org_id: uuid.UUID,
    person_id: uuid.UUID,
    manager_id: uuid.UUID,
    valid_from: Optional[datetime] = None,
) -> OrgUnitReportingLine:
    if person_id == manager_id:
        raise ValueError("a person cannot report to themselves")
    line = OrgUnitReportingLine(
        org_id=org_id, person_id=person_id, manager_id=manager_id, valid_from=valid_from or _now()
    )
    db.add(line)
    db.flush()
    return line


def get_manager_as_of(
    db: Session, org_id: uuid.UUID, person_id: uuid.UUID, as_of: Optional[datetime] = None
) -> Optional[uuid.UUID]:
    as_of = as_of or _now()
    query = (
        select(OrgUnitReportingLine.manager_id)
        .where(
            OrgUnitReportingLine.org_id == org_id,
            OrgUnitReportingLine.person_id == person_id,
            OrgUnitReportingLine.valid_from <= as_of,
            (OrgUnitReportingLine.valid_to.is_(None)) | (OrgUnitReportingLine.valid_to > as_of),
        )
        .order_by(OrgUnitReportingLine.valid_from.desc())
        .limit(1)
    )
    row = db.execute(query).first()
    return row[0] if row else None


# ─── Unit heads ─────────────────────────────────────────────────────────────

def set_unit_head(
    db: Session,
    org_id: uuid.UUID,
    unit_id: uuid.UUID,
    person_id: uuid.UUID,
    valid_from: Optional[datetime] = None,
) -> OrgUnitHead:
    """Close out the current head record (if any) and start a new one, so at most
    one head is open (valid_to IS NULL) per unit at a time."""
    effective_from = valid_from or _now()

    current = db.execute(
        select(OrgUnitHead)
        .where(OrgUnitHead.org_id == org_id, OrgUnitHead.unit_id == unit_id, OrgUnitHead.valid_to.is_(None))
    ).scalars().first()
    if current is not None:
        current.valid_to = effective_from

    head = OrgUnitHead(org_id=org_id, unit_id=unit_id, person_id=person_id, valid_from=effective_from)
    db.add(head)
    db.flush()
    return head


def get_unit_head_as_of(
    db: Session, org_id: uuid.UUID, unit_id: uuid.UUID, as_of: Optional[datetime] = None
) -> Optional[uuid.UUID]:
    as_of = as_of or _now()
    query = (
        select(OrgUnitHead.person_id)
        .where(
            OrgUnitHead.org_id == org_id,
            OrgUnitHead.unit_id == unit_id,
            OrgUnitHead.valid_from <= as_of,
            (OrgUnitHead.valid_to.is_(None)) | (OrgUnitHead.valid_to > as_of),
        )
        .order_by(OrgUnitHead.valid_from.desc())
        .limit(1)
    )
    row = db.execute(query).first()
    return row[0] if row else None
