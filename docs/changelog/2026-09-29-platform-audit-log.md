# Platform audit log

**Date:** 2026-09-29
**Phase/item:** Phase 0 — 0.2
**Branch:** `feat/platform-audit-log`
**PR:** pending

## What changed

- `app/modules/platform/models/audit_log.py` — `PlatformAuditLog`
  (`platform_audit_logs`), a shared audit trail any module can write through.
  Named `PlatformAuditLog` rather than `AuditLog` to avoid colliding with `ims`'s
  existing `AuditLog` class in SQLAlchemy's shared declarative registry (see the
  "bugs caught" note below). Records `actor_type`/`actor_id`/`actor_label` (user,
  AI, or system — `actor_id` not FK'd, same rationale as
  `org_unit_assignments.person_id`), action, resource type/id, and
  `before_data`/`after_data`/`extra_data` JSON. RLS enabled + forced, same policy
  pattern as the org tree tables.
- `app/modules/platform/services/audit.py::log_action()` — sets its own RLS
  tenant context and commits independently, matching the "call it last, after
  the main commit" convention in `CLAUDE.md`.
- Migration `o5p6q7r8s9t0`.
- `tests/platform/test_audit_log.py` — 7 Postgres-marked tests: field
  persistence, AI/system actors, ordering, no orphaned row when the main action
  fails before logging, write isolation between two orgs, RLS fail-closed with no
  context, raw-SQL cross-tenant insert rejection.
- `tests/platform/conftest.py` — added `pg_committing_session`/
  `make_org_committing`, for testing code that calls `db.commit()` itself
  (the existing `pg_session` fixture only supports flush-then-rollback).
- `docs/implementation-plan.md` — 0.2 marked done; next-step note updated to
  point at 0.3 (Keycloak).

## Why

Smallest, fully self-contained remaining Phase 0 item (see
`docs/implementation-plan.md`) — every later milestone (workflow engine,
access-management UI, AI actions) needs an audit trail to exist already rather
than being bolted on retroactively.

## Bugs caught

Initially named the model `AuditLog`. `ims`'s `Organization`/`User` models
reference their own audit log via the string form `relationship("AuditLog", ...)`,
which SQLAlchemy resolves by class name across its *entire* shared declarative
registry, not by module path. Two classes named `AuditLog` made that lookup
ambiguous and silently broke mapper configuration for `Organization`/`User` —
213 test errors across the whole suite, not just the new tests. Caught by running
the full suite rather than only the new test file; fixed by renaming to
`PlatformAuditLog`.

## Verification

267/267 tests passing against real Postgres (240 SQLite + 27 Postgres-marked, all
genuinely executed, none skipped). Migration upgrade/downgrade/upgrade round-trip
verified.
