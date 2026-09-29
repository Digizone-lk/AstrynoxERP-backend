"""Tests for the shared platform audit log (app.modules.platform.services.audit).

Requires Postgres — see conftest.py. Uses pg_committing_session (not the usual
rollback-based pg_session) because log_action() commits its own transaction, the
same way it will be called in production — see the module docstring in
app/modules/platform/services/audit.py.
"""
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.modules.platform.db import set_tenant_context
from app.modules.platform.models.audit_log import PlatformAuditLog, AuditActorType
from app.modules.platform.services import audit as audit_service

pytestmark = pytest.mark.postgres

RLS_TEST_ROLE = "platform_rls_test_role"


def test_log_action_persists_expected_fields(pg_committing_session, make_org_committing):
    org_id = make_org_committing()
    actor_id = uuid.uuid4()

    entry = audit_service.log_action(
        pg_committing_session,
        org_id=org_id,
        action="UPDATE",
        resource_type="org_unit",
        resource_id="some-unit-id",
        actor_type=AuditActorType.USER,
        actor_id=actor_id,
        actor_label="jane@acme.com",
        before_data={"name": "Old Name"},
        after_data={"name": "New Name"},
        extra_data={"reason": "rebrand"},
        ip_address="203.0.113.5",
    )

    fetched = pg_committing_session.get(PlatformAuditLog, entry.id)
    assert fetched.org_id == org_id
    assert fetched.action == "UPDATE"
    assert fetched.resource_type == "org_unit"
    assert fetched.resource_id == "some-unit-id"
    assert fetched.actor_type == AuditActorType.USER
    assert fetched.actor_id == actor_id
    assert fetched.actor_label == "jane@acme.com"
    assert fetched.before_data == {"name": "Old Name"}
    assert fetched.after_data == {"name": "New Name"}
    assert fetched.extra_data == {"reason": "rebrand"}
    assert fetched.ip_address == "203.0.113.5"
    assert fetched.created_at is not None


def test_log_action_defaults_support_ai_and_system_actors(pg_committing_session, make_org_committing):
    org_id = make_org_committing()

    ai_entry = audit_service.log_action(
        pg_committing_session, org_id=org_id, action="PROPOSE", resource_type="leave_request",
        actor_type=AuditActorType.AI, actor_label="leave-assistant-v1",
    )
    assert ai_entry.actor_type == AuditActorType.AI
    assert ai_entry.actor_id is None  # AI has no user row to reference

    system_entry = audit_service.log_action(
        pg_committing_session, org_id=org_id, action="ESCALATE", resource_type="workflow_instance",
        actor_type=AuditActorType.SYSTEM, actor_label="escalation-job",
    )
    assert system_entry.actor_type == AuditActorType.SYSTEM


def test_log_action_ordering_reflects_call_sequence(pg_committing_session, make_org_committing):
    org_id = make_org_committing()
    resource_id = str(uuid.uuid4())

    audit_service.log_action(pg_committing_session, org_id, "CREATE", "org_unit", resource_id)
    audit_service.log_action(pg_committing_session, org_id, "UPDATE", "org_unit", resource_id)
    audit_service.log_action(pg_committing_session, org_id, "DELETE", "org_unit", resource_id)

    rows = pg_committing_session.execute(
        select(PlatformAuditLog)
        .where(PlatformAuditLog.org_id == org_id, PlatformAuditLog.resource_id == resource_id)
        .order_by(PlatformAuditLog.created_at, PlatformAuditLog.id)
    ).scalars().all()

    assert [r.action for r in rows] == ["CREATE", "UPDATE", "DELETE"]


def test_no_audit_row_when_main_action_fails_before_logging(pg_committing_session, make_org_committing):
    """Convention: log_action() is only ever called after the main action already
    succeeded. If the main action fails first, log_action() is never reached, and
    no audit row should exist for a resource that was never actually created."""
    org_id = make_org_committing()
    resource_id = str(uuid.uuid4())

    try:
        raise RuntimeError("simulated failure in the main action")
        audit_service.log_action(pg_committing_session, org_id, "CREATE", "org_unit", resource_id)  # unreachable
    except RuntimeError:
        pg_committing_session.rollback()

    rows = pg_committing_session.execute(
        select(PlatformAuditLog).where(PlatformAuditLog.resource_id == resource_id)
    ).scalars().all()
    assert rows == []


def test_audit_log_write_isolation_between_two_orgs(pg_committing_session, make_org_committing):
    org_a = make_org_committing(slug="org-a")
    org_b = make_org_committing(slug="org-b")

    pg_committing_session.execute(text(f"SET LOCAL ROLE {RLS_TEST_ROLE}"))
    audit_service.log_action(pg_committing_session, org_a, "CREATE", "org_unit", "unit-a")

    pg_committing_session.execute(text(f"SET LOCAL ROLE {RLS_TEST_ROLE}"))
    audit_service.log_action(pg_committing_session, org_b, "CREATE", "org_unit", "unit-b")

    pg_committing_session.execute(text(f"SET LOCAL ROLE {RLS_TEST_ROLE}"))
    set_tenant_context(pg_committing_session, org_a)
    rows = pg_committing_session.execute(select(PlatformAuditLog)).scalars().all()
    assert len(rows) == 1
    assert rows[0].org_id == org_a
    assert rows[0].resource_id == "unit-a"


def test_audit_log_no_tenant_context_sees_nothing(pg_session, make_org):
    """Fail closed, same as the org_units RLS tests."""
    make_org()
    pg_session.execute(text(f"SET LOCAL ROLE {RLS_TEST_ROLE}"))
    rows = pg_session.execute(select(PlatformAuditLog)).scalars().all()
    assert rows == []


def test_audit_log_cross_tenant_insert_rejected_by_rls(pg_session, as_tenant, make_org):
    """RLS policy check, independent of the service layer: even a raw SQL insert
    tagged with a different org_id than the session's tenant context is blocked."""
    org_a = make_org(slug="org-a")
    org_b = make_org(slug="org-b")
    as_tenant(org_a)

    with pytest.raises(DBAPIError):
        pg_session.execute(
            text(
                "INSERT INTO platform_audit_logs (id, org_id, actor_type, action, resource_type, created_at) "
                "VALUES (:id, :org_id, 'user', 'CREATE', 'org_unit', now())"
            ),
            {"id": uuid.uuid4(), "org_id": org_b},
        )
        pg_session.flush()
