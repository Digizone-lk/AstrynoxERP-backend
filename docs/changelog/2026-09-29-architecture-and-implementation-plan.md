# Architecture overview & phased implementation plan

**Date:** 2026-09-29
**Phase/item:** — (planning/docs, not a numbered Phase 0 item)
**Branch:** `docs/architecture-and-implementation-plan`
**PR:** #36 (merged)

## What changed

- Added `docs/architecture.md`: current + target system architecture with Mermaid
  diagrams — system overview, module boundaries, the multi-tenancy/RLS mechanism,
  the org tree ER diagram, the planned Keycloak OIDC flow, the OpenFGA/OPA
  authorization model, the workflow engine state machine, the request lifecycle,
  deployment, testing strategy, and a "known debt" section (e.g. `organizations`/
  `users` still living in `ims/` instead of `platform/`, closure-table-vs-`ltree`
  rationale).
- Added `docs/implementation-plan.md`: turns `docs/prd.md`'s Phase 0 outline into
  a sequenced, trackable plan — status per item, a dependency graph, and a
  suggested order of work.

## Why

`docs/prd.md` is the source of truth for *what* and *why*, but is never edited in
this repo. These two docs give the repo its own living record of *how* the system
is built and *what order* remaining work happens in, kept in sync as work lands
(unlike `prd.md`).

## Verification

Docs only — no code changes. Reviewed for Mermaid diagram syntax correctness.
