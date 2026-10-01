# Platform org tree (org_units)

**Date:** 2026-09-29
**Phase/item:** Phase 0 — 0.1
**Branch:** `feat/platform-org-units`
**PR:** #35 (merged)

## What changed

Added the platform module (`app/modules/platform/`) with the effective-dated org
tree from `docs/prd.md`:

- `org_units` — one table, free-text `unit_type` + self-referential `parent_id`
  (pure tree). The root row (`parent_id IS NULL`) represents the organization
  itself; a partial unique index enforces exactly one root per tenant.
- `org_unit_closures` — transitive-closure table for fast subtree/ancestor
  queries, maintained via a standard detach/reattach algorithm on move.
- `org_unit_assignments`, `org_unit_reporting_lines`, `org_unit_heads` — all
  effective-dated (`valid_from`/`valid_to`), reporting lines kept separate from
  tree position. `person_id` columns are deliberately not FK'd (a user is not an
  employee, per `docs/prd.md`).
- `app/modules/platform/services/org_tree.py` — unit create/move, subtree/ancestor
  queries, as-of-date lookups for assignments/reporting lines/unit heads.
- `app/modules/platform/db.py::set_tenant_context()` — the `SET LOCAL
  app.current_org_id` helper every platform table's RLS policy relies on.
- Migration `n4o5p6q7r8s9`: creates all 5 tables, enables + forces RLS, adds a
  tenant-isolation policy per table.
- CI: added a `postgres:16-alpine` service so Postgres-marked tests actually run
  there instead of skipping forever.

## Why

First piece of the platform core (`docs/prd.md` Phase 0 outline) — every later
HR/platform milestone (OpenFGA, workflow engine) builds on this tree.

## Verification

20 Postgres-marked tests (subtree queries, tree moves, as-of-date lookups, RLS
isolation between two orgs, cross-tenant insert/update rejection) passing against
real Postgres. Full suite (260 tests at the time) passing. Migration
upgrade/downgrade/upgrade round-trip verified.
