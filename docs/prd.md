# Astrynox HR Module — PRD & Decision Log

Sep 28, 2026 · @Brayan Jay

## Overview

The HR module is Astrynox's second module: an AI-powered HR system that automates routine HR administration while keeping humans in control of decisions that significantly affect people.

It is built on a shared platform core (identity, access, org structure, workflow engine, audit) that every Astrynox module will use. HR is the first heavy consumer of that core, and invoicing can adopt the workflow engine later.

Guiding principle: the AI proposes, deterministic code disposes. The AI drafts, checks and routes; policy and approvals decide.

Everything is built fresh for Astrynox. No code, designs, documents or specs from previous employers are reused.

## Target customers and pilot

The first market is mid-size companies (50–500 employees). The design must support enterprise scale from day one, while the UI initially exposes only what mid-size companies need.

Enterprise readiness is mainly a design concern, not an infrastructure one. It depends on:

- Multi-level org structure and multiple legal entities
- Per-tenant configurable rules and approval chains
- Fine-grained, scope-based access control
- SSO, full audit trails, bulk operations, imports and integrations

The pilot is a company with 20–50 employees. It will validate real workflows, letters, leave rules and quick setup. It will not stress-test deep hierarchies, complex approval chains or performance, so a second pilot in the 100–300 range is a goal before marketing to mid-size companies.

## Scope and roadmap

The full scope is employee records and self-service, attendance and leave, payroll (EPF/ETF/APIT), recruitment and onboarding, document requests, and lifecycle workflows. It ships in five phases, ordered by dependency.

&#91;embedded content: phased roadmap · 5 phases\]

Employee records feed everything else. Leave, document requests and lifecycle changes all run on one workflow engine. Payroll waits until attendance and leave data is trusted. Recruitment is independent and comes last.

## AI autonomy model

AI autonomy is set by action risk. Tenants can make any action stricter, but tier 3 actions can never be automated.

| Tier | AI role | Human role | Examples |
| --- | --- | --- | --- |
| 0 | Fully automatic | None | Policy Q&A, balance lookups, status checks |
| 1 | Automatic within policy, audited | Reviews audit trail | Leave within balance and rules, employment confirmation letters, salary confirmations (requester-only access) |
| 2 | Prepares the action | One approver | Attendance corrections, policy exceptions, finalizing a payroll run |
| 3 | Assists only: drafts, checks, flags | Multi-level approval | Promotions, salary changes, transfers, terminations, hiring decisions |

The tier 3 floor keeps solely automated decisions with significant effects on people out of the system, in line with GDPR Article 22. Every AI-proposed action passes a deterministic policy check before it executes.

## Workflow engine

One engine runs every request type: leave, document requests, promotions, transfers, resignations and terminations. Each becomes configuration, not a separate feature.

&#91;embedded content: workflow template lifecycle · 4 stages, 1 loop\]

The dev team authors templates with an internal no-code builder (structured JSON/YAML with schema validation and a visual preview in v1). Tenant superadmins can only tweak templates:

- Add approval steps and route them to a person or level
- Change approvers and assignees
- Add conditional rules: a field the template exposes, an operator, a value, then an added approver or step (e.g. leave over 5 days also needs the department head)

Templates mark each part locked or editable. Locked parts include step types, the final data change, mandatory steps and the risk tier. Conditional rules can only add approvals and are evaluated deterministically, never by the AI.

Tenant tweaks are stored as overlays on a specific template version, so template upgrades re-apply them. Requests in progress stay on the version they started with.

Approvers are resolved at runtime, never stored as fixed user IDs:

| Approver type | Example |
| --- | --- |
| Specific person | A named finance head |
| Role | HR Officer |
| Level or position | Grade 5 and above |
| Relationship | Reporting manager, manager's manager, department head |

Required edge cases: self-approval prevention, vacant approver roles, delegation while an approver is on leave, escalation on timeout, rejection and resubmission, and a full audit trail (who, when, which version, why).

Implementation: a state machine in Postgres (definitions, instances, step instances, actions) plus a job queue for timers and escalations. No heavy orchestrator is needed.

Enterprise clients who need fully custom workflows can have them built by the dev team as a paid service.

## Identity and access

Keycloak handles identity; authorization lives in the app, split between OpenFGA for relationships and OPA for policy rules. The current in-app auth is replaced outright, since the invoicing module has no users to migrate.

&#91;embedded content: identity and access architecture · 5 components\]

### Keycloak (self-hosted)

- Keycloak 26.x in production mode, hosted on the Oracle Cloud Always Free ARM tier for the pilot; move to a paid instance once there are paying tenants
- Dedicated Postgres with nightly off-machine backups; reverse proxy with TLS on its own subdomain; admin console not public
- Realms, clients and roles managed as code (keycloak-config-cli or Terraform) in git
- Brute-force detection, short-lived access tokens, MFA on the admin account; version pinned and upgraded deliberately
- Login theme built with Keycloakify
- One `astrynox` realm with Organizations; each customer company is one organization, with its own SSO connection
- Clients: Next.js web app (authorization code + PKCE), FastAPI (token audience), and a backend service account limited to creating and disabling users
- Tokens carry user identity, organization ID and coarse roles only

### OpenFGA (relationships)

OpenFGA answers who is related to whom across the org tree. It covers RBAC (roles as relationships), ReBAC (inheritance down the tree) and ABAC (conditions such as grade limits). The tenant admin UI presents this as role + scope, e.g. "HR Officer for the Kandy branch".

### OPA / Rego (policy rules)

OPA validates tenant template tweaks, enforces workflow invariants such as no self-approval, and checks every AI-proposed action before it executes. Rego is written only by the dev team, versioned in git and unit-tested; tenant configuration is data that policies evaluate. OPA is added once the workflow engine and AI layer are live.

### Guardrails and pitfalls

- No privilege escalation: tenant admins grant only access they hold
- Salary visibility and the audit log need explicit grants and never inherit by accident
- An explain view shows why a person can see a record
- Permission changes are audited and access is reviewed periodically, feeding SOC 2 controls
- Org data and OpenFGA relationships update together through an outbox pattern, so transfers never leave stale access
- List views filter by precomputed scope in SQL; OpenFGA handles individual checks
- Account lifecycle follows HR workflows: termination and resignation disable the account and revoke sessions on the effective date
- A user is not an employee: some employees never log in, and records exist before accounts during onboarding

## Org structure

The hierarchy is Organization > Branch > Department > Team > Sub Team, and it is a pure tree: each branch has its own departments.

&#91;embedded content: org hierarchy · 5 levels, pure tree\]

- **One flexible tree:** a single `org_units` table where each unit has a type and a parent. Small tenants can skip levels, and new level types (Region, Division) need no schema change.
- **Fast subtree queries:** a closure table or Postgres `ltree` paths, used for SQL scope filtering.
- **Head office is a branch:** central functions get their own branch, and company-wide roles are assigned at the Organization level.
- **Function tags:** departments carry an optional tenant-defined function (Sales, Finance, Operations) so reports roll up across branches.
- **Reporting lines are separate** from tree position, so "my manager" and "head of my department" both resolve correctly.
- **Effective dating everywhere:** org units, assignments, reporting lines and unit heads carry `valid_from` / `valid_to` instead of being overwritten.
- **Restructures run as workflows** with an effective date, so the tree, OpenFGA relationships and approval routing switch together.

The tree maps to one recursive OpenFGA type:

```
type org_unit
  relations
    define parent: [org_unit]
    define head: [user]
    define hr_officer: [user] or hr_officer from parent
    define viewer: [user] or viewer from parent or hr_officer
```

## Phase 0 outline

Phase 0 builds the shared platform core that every Astrynox module uses. HR work starts only once it is in place.

- [ ] Stand up self-hosted Keycloak on Oracle Cloud with Postgres, TLS proxy, backups and health monitoring
- [ ] Define the `astrynox` realm, Organizations, clients and token mappers as code
- [ ] Build the Keycloakify login theme
- [ ] Replace in-app auth in FastAPI and Next.js with OIDC; add `idp_subject` to the users table
- [ ] Map tenants to Keycloak organizations
- [ ] Stand up OpenFGA and write the `org_unit` and `employee` authorization model
- [ ] Build the effective-dated `org_units` tree with closure table or `ltree`, reporting lines and function tags
- [ ] Build the outbox sync between org data and OpenFGA
- [ ] Build the access-management UI (role + scope, explain view, audited changes)
- [ ] Build the workflow engine: definitions, overlays, instances, step instances, actions, job queue
- [ ] Build the internal template builder (JSON/YAML, schema validation, visual preview)
- [ ] Build the platform audit log

## Risks and open questions

### Risks

- **Operational load:** Keycloak, OpenFGA and OPA are a lot of authorization infrastructure for a solo developer. A Keycloak outage locks out every tenant.
- **Free-tier hosting:** Oracle Always Free has no uptime guarantee, and idle resources can be reclaimed.
- **Pilot size:** a 20–50 employee pilot will not exercise deep hierarchies, complex approvals or performance.
- **Payroll accuracy:** calculation errors mean real money and statutory problems.
- **IP and employment terms:** the module must be built fresh, and the employment contract should be checked for IP assignment or non-compete clauses before launch.

### Open questions

- [ ] AI layer design: where the agent sits, which tools it gets, how proposals flow through OPA
- [ ] Compliance scope: Sri Lanka EPF/ETF/APIT and PDPA, GDPR
- [ ] Pilot company details: industry and current HR process (spreadsheets, paper, another system)
- [ ] Tenancy model: shared schema with tenant ID and row-level security, schema per tenant, or database per tenant
- [ ] Second pilot in the 100–300 employee range

## Decision log

All decisions below were made on 28 Sep 2026.

| Area | Decision | Why |
| --- | --- | --- |
| Policy rules | OPA/Rego alongside OpenFGA, platform-authored only | Strong for invariants and AI guardrails; tenants configure data, never code |
| Org structure | Pure tree: Organization > Branch > Department > Team > Sub Team | Each branch has its own departments |
| Authorization | OpenFGA for relationships, role + scope admin UI | HR permissions follow the org tree |
| Access management | Tenant-facing UI covering RBAC, ABAC and ReBAC at org, department and team level | Tenants manage their own access |
| Identity | Self-hosted Keycloak, one realm with Organizations | Full control, no per-user fees, enterprise SSO |
| Auth migration | Replace in-app auth outright in Phase 0 | Invoicing module has 0 users |
| Platform core | Identity, org tree, workflow engine and audit are shared services | Every module will use them |
| Conditional rules | Tenant admins can add conditions that only add approvals | Flexibility without weakening locked rules |
| Workflows | Dev team builds templates; tenants tweak steps, approvers and conditions | Customers own routing, the platform owns logic |
| AI autonomy | Mixed by risk tier, tier 3 never automated | Safety, GDPR Article 22, buyer trust |
| Roadmap | Five phases, payroll after attendance and leave | Dependency order |
| Target market | Mid-size first, designed for enterprise scale | Scalability is a design concern |
