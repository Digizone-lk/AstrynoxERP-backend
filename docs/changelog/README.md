# Changelog

One file per finished task, not a single running log — easier to scan, link to,
and reference from a PR description. Dated so `ls` sorts them chronologically.

## Filename

```
YYYY-MM-DD-<short-slug>.md
```

Date is when the work was finished (PR opened/merged), not when it started.

## Template

```markdown
# <Title>

**Date:** YYYY-MM-DD
**Phase/item:** <e.g. Phase 0 — 0.2, or "—" if it doesn't map to one>
**Branch:** <branch name>
**PR:** <#NN link, or "pending" if not yet opened>

## What changed

Short, concrete list of what landed.

## Why

One or two sentences of motivation/context — link to docs/prd.md or
docs/implementation-plan.md where relevant instead of re-explaining them.

## Verification

How it was tested/verified (e.g. "267/267 tests passing against real Postgres,
migration upgrade/downgrade/upgrade round-trip verified").
```

## When to write one

As the last step of finishing a task, alongside (same branch/PR) the work it
documents — not batched up later. See `docs/implementation-plan.md` for the
task list this changelog tracks progress against.
