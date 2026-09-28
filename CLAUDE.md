# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

**Astrynox ERP** — a multi-tenant SaaS ERP built as a modular monolith. The first module is **BillFlow**, the Invoice Management System (IMS). The HR module and a shared platform core are being added next (see `docs/prd.md`).

## Read First

- Before any architectural work, read `docs/prd.md`. It is the source of truth for the HR module and the platform core.
- Never modify `docs/prd.md`. It is maintained outside the repo and re-exported when decisions change.
- All work branches from `dev` and PRs target `dev`. Never open PRs against `main`; `main` is updated manually after local verification.

## Direction (from docs/prd.md)

- **Auth is being replaced.** In-app JWT auth will be replaced by self-hosted Keycloak (OIDC). Do not extend the current auth system; new auth code targets Keycloak token validation.
- **Roles:** the four roles in `app/models/user.py` are invoicing-only. HR permissions use Keycloak coarse roles + OpenFGA scopes. Do not add HR roles to this enum.
- **Architecture:** modular monolith. One FastAPI app, one database, modules `platform/` (identity, org tree, workflow engine, authz, audit), `invoice/`, `hrms/`. Modules talk through each other's service interfaces, never each other's tables directly.
- **Tenancy:** `Organization` = tenant, `org_id` on every table. New tables also get Postgres row-level security policies. The org tree (`org_units`) root links to `organizations.id`.
- **Tests:** new platform/HR code that uses Postgres-only features (RLS, ltree) is tested against Postgres, not SQLite.

## Commands

### Local Development

```bash
# Copy and fill in environment variables
cp .env.example .env

# Start PostgreSQL + backend (with hot reload)
docker compose up --build

# Run without Docker (requires a running Postgres)
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

### Database Migrations

```bash
# Apply all pending migrations
alembic upgrade head

# Create a new migration (auto-generate from model changes)
alembic revision --autogenerate -m "describe_change"

# Rollback one migration
alembic downgrade -1
```

**Important:** All models must be imported in `alembic/env.py` via `import app.models` (the `__init__.py` re-exports them) for Alembic to detect schema changes.

### Tests

```bash
# Run full suite
pytest tests/ -q --tb=short

# Run a single test file
pytest tests/test_invoices.py -q

# Run a single test by name
pytest tests/test_invoices.py::test_create_invoice -q
```

Tests use SQLite (file `test_billflow.db`, auto-deleted after session). No Postgres or real Cloudinary needed — both are mocked in `tests/conftest.py`.

## Architecture

### Multi-Tenancy

Every resource is scoped to an `Organization`. The `org_id` is on every model and every DB query must filter by it. The JWT payload embeds `sub` (user_id), `org_id`, and `role` — these are available in every request via `get_current_user()` in `app/dependencies.py`.

### Auth Flow

- Tokens are issued as **HttpOnly cookies** (`access_token`, `refresh_token`) and also accepted as `Authorization: Bearer` headers.
- Refresh tokens are **hashed with SHA-256** before storage in `user_sessions`. Never store the raw token.
- On refresh, the old session is revoked before a new one is issued (rotation).
- `app/dependencies.py` contains the role guard helpers: `get_current_user`, `require_roles`, and shorthand guards (`get_super_admin`, `get_sales_or_admin`, etc.).

### Request Lifecycle

```
Router (app/routers/) → Dependency injection (app/dependencies.py) → Service (app/services/) → Model (app/models/)
```

Routers handle HTTP concerns. Business logic that spans multiple models lives in `app/services/`. Audit logging (`app/services/audit.py`) is called **after** the main commit — always call `log_action()` as the last step.

### Role System

Four roles defined in `app/models/user.py`: `SUPER_ADMIN`, `ACCOUNTANT`, `SALES`, `VIEWER`. Use the shorthand guards in routers; don't call `require_roles()` directly in most cases.

### Document Numbering

`app/services/numbering.py` generates `QUO-XXXX` and `INV-XXXX` numbers by counting existing records per org. This is not gap-safe under high concurrency — acceptable for current scale.

### InvoiceItem / QuotationItem Price Snapshots

`product_name` and `unit_price` on line items are **snapshots at creation time**, not live references. This is intentional so historical documents don't change when products are edited.

### PDF Generation

`app/services/pdf.py` uses WeasyPrint. The Dockerfile installs the required system libs (`libcairo2`, `libpango`, etc.). PDF routes are split into a separate router (`app/routers/quotations_pdf.py`) to keep the main quotation router clean.

### Testing Patterns

- `tests/conftest.py` defines fixtures at three scopes: session (`create_tables`), function (`clean_db` — truncates all tables), and role (`admin_client`, `sales_client`, etc.).
- Domain factories (`make_client`, `make_product`, `make_quotation`, `make_invoice`) return the created JSON. Compose them in tests.
- Cloudinary is mocked at session scope — no special setup needed.
- SQLite UUID columns degrade to `CHAR(32)` — queries still work but comparisons must use string UUIDs in SQLite-only paths.

## Deployment

- **Production backend:** Render, deployed via GitHub push. Render auto-detects the `Dockerfile` at the repo root.
- **Production frontend:** Vercel (Next.js). Frontend never calls the backend directly — all API requests go through a Next.js proxy route at `app/api/[...path]/route.ts`, which forwards them to the Render backend.
- **CI:** `.github/workflows/ci.yml` runs `pytest` on every push using SQLite. No external services needed.
- The `docker-compose.yml` is for local development only (includes `--reload` and a volume mount). Production uses the plain Dockerfile CMD.
- `ENVIRONMENT=production` enables `secure=True` on cookies. Never deploy with the default `SECRET_KEY`.

### Required Render Environment Variables

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `SECRET_KEY` | JWT signing secret |
| `ALLOWED_ORIGINS` | Comma-separated list of allowed frontend URLs (e.g. `https://your-app.vercel.app`) |
| `CLOUDINARY_CLOUD_NAME` | Cloudinary credentials |
| `CLOUDINARY_API_KEY` | Cloudinary credentials |
| `CLOUDINARY_API_SECRET` | Cloudinary credentials |
| `ENVIRONMENT` | Set to `production` |

### Frontend Proxy (Vercel → Render)

The frontend proxy (`app/api/[...path]/route.ts`) sets `Accept-Encoding: identity` on all upstream requests. **Do not remove this.** Without it, Render compresses the response body, the proxy forwards the compressed bytes + `Content-Encoding` header, and Vercel's runtime corrupts the body → `ERR_CONTENT_DECODING_FAILED` in the browser.

After changing `NEXT_PUBLIC_API_URL` in Vercel, **a redeploy is required** for the new URL to take effect in the proxy (the value is read at module load time).

## Planned: Chat Feature — LLM Backend Migration

### Azure OpenAI (future upgrade)

The chat service currently uses OpenAI's standard API (`app/chat/service.py`). A planned upgrade is to migrate to **Azure OpenAI Service** for enterprise data compliance (DPA, no training on org data, data residency).

**What changes:**
- Replace `openai.OpenAI(...)` with `openai.AzureOpenAI(...)` in `service.py`
- Add env vars: `AZURE_OPENAI_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT`
- No changes needed to `tools.py` — the OpenAI SDK interface is identical

**New env vars to add to Render:**

| Variable | Description |
|---|---|
| `AZURE_OPENAI_KEY` | Azure OpenAI resource API key |
| `AZURE_OPENAI_ENDPOINT` | e.g. `https://YOUR-RESOURCE.openai.azure.com` |
| `AZURE_OPENAI_DEPLOYMENT` | Deployment name (e.g. `gpt-4o-mini`) |

**Current workaround:** OpenAI Zero Data Retention is enabled on the API account — inputs/outputs are not logged or stored by OpenAI.

---

## Planned: Chat Feature — Remaining Work

### Tools to Add (`app/chat/chat_tools.py`)

For each tool: add the definition to `TOOL_DEFINITIONS`, write the executor function, register it in `execute_tool()`.

| Tool | Description | Key parameters |
|---|---|---|
| `get_outstanding_amount` | Total unpaid invoice amount (sent + overdue) | none |
| `get_overdue_invoices` | List overdue invoices | `limit` (optional) |
| `get_quotations` | List quotations by status/date/client | `status[]`, `client_names[]`, `start_date`, `end_date` |
| `get_quotation_summary` | Count/total of quotations by status | `status[]`, `start_date`, `end_date` |
| `get_client_summary` | Total invoiced, paid, outstanding for a client | `client_name` |
| `get_top_clients` | Clients ranked by total paid amount | `limit` (optional) |
| `get_clients` | List clients | `search` (optional), `is_active` (optional) |
| `get_products` | List products | `search` (optional) |

**Rules for every executor:**
- Always filter by `org_id` — never accept it as a tool parameter
- Always return a `dict`, never raise — on bad input return `{"error": "..."}`
- Always use `func.coalesce(func.sum(...), 0)` for aggregations
- Always add `LIMIT` to list queries (use `MAX_RESULTS = 50`)

### Tests to Write (`tests/test_chat.py`)

Use the existing `admin_client` fixture and domain factories from `conftest.py`. Mock the OpenAI API — do not make real API calls in tests.

**Test cases:**

```
test_chat_requires_auth                  — unauthenticated request returns 401
test_chat_simple_question                — question with no tool calls returns a text response
test_chat_get_invoices_by_status         — "overdue invoices" triggers get_invoices with status=["overdue"]
test_chat_get_invoice_summary            — "total income this month" triggers get_invoice_summary
test_chat_get_outstanding_amount         — "what's outstanding" triggers get_outstanding_amount
test_chat_history_preserved              — response history contains all turns in correct order
test_chat_multi_tool_call                — question requiring two tools triggers both executors
test_chat_invalid_date_returns_error     — executor handles bad date input gracefully (no 500)
test_chat_org_isolation                  — two orgs, chat only returns data for the authenticated org
```

**Mocking pattern:**
```python
from unittest.mock import patch, MagicMock

@patch("app.chat.chat_service.client")
def test_chat_simple_question(mock_openai, admin_client, clean_db):
    mock_response = MagicMock()
    mock_response.choices[0].message.tool_calls = None
    mock_response.choices[0].message.content = "Hello!"
    mock_openai.chat.completions.create.return_value = mock_response
    ...
```