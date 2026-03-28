# BillFlow Backend — Testing Plan

This document describes the testing strategy, how to run the test suite, what is covered, and what gaps remain.

---

## Table of Contents

- [Strategy](#strategy)
- [Test Environment](#test-environment)
- [Running the Tests](#running-the-tests)
- [Test Suite Overview](#test-suite-overview)
- [Coverage by Module](#coverage-by-module)
- [Test Fixtures](#test-fixtures)
- [What Is Not Covered](#what-is-not-covered)
- [CI/CD Recommendations](#cicd-recommendations)

---

## Strategy

The test suite uses **synchronous integration tests** that exercise the full HTTP request/response cycle through FastAPI's `TestClient`. Each test:

1. Hits a real endpoint (no mocking of route handlers or business logic)
2. Reads from and writes to a real SQLite database (schema identical to production PostgreSQL)
3. Uses role-specific authenticated clients to verify RBAC enforcement
4. Verifies tenant isolation by attempting cross-organisation data access

The philosophy is **behaviour over implementation**: tests assert what the API does, not how it does it internally. This means tests survive refactors as long as the contract is preserved.

---

## Test Environment

| Component | Value |
|---|---|
| Test database | SQLite (`test_billflow.db`) |
| Database URL | `sqlite:///./test_billflow.db` (set via env var before app import) |
| Secret key | `test-only-secret-key-do-not-use-in-production` |
| Isolation | Each test function runs in a fresh database (tables dropped and recreated via `autouse` session fixture) |
| Test runner | pytest 8.3.4 |

> **SQLite vs PostgreSQL:** The test database is SQLite for speed and zero-dependency setup. UUID primary keys use `postgresql.UUID(as_uuid=True)` in the models; explicit `PyUUID(str)` conversion in `dependencies.py` and `auth.py` ensures compatibility. Decimal handling and case-sensitivity may differ slightly; always run a smoke test against PostgreSQL before deploying.

---

## Running the Tests

### Prerequisites

```bash
cd backend
pip install -r requirements.txt
```

### Run all tests

```bash
pytest tests/ -v
```

### Run a single file

```bash
pytest tests/test_auth.py -v
```

### Run a single test

```bash
pytest tests/test_quotations.py::test_convert_to_invoice -v
```

### Run with output on failure

```bash
pytest tests/ -v --tb=short
```

### Expected result

```
126 passed in ~10s
```

---

## Test Suite Overview

| File | Tests | Domain |
|---|---|---|
| `tests/test_auth.py` | 18 | Registration, login, refresh, logout, /me |
| `tests/test_clients.py` | 22 | Client CRUD, RBAC, tenant isolation, product assignments |
| `tests/test_products.py` | 20 | Product CRUD, soft delete, RBAC, global/client-specific filter |
| `tests/test_quotations.py` | 24 | Quotation lifecycle, status transitions, convert-to-invoice, RBAC, numbering |
| `tests/test_invoices.py` | 26 | Invoice lifecycle, mark-paid/overdue RBAC, cancel, pagination, tenant isolation |
| **Total** | **110** | |

> The summary above reflects the stable test count. Run `pytest --co -q` to get the live count.

---

## Coverage by Module

### Auth (`test_auth.py`)

| Test | What It Verifies |
|---|---|
| `test_register_success` | 201 response; cookies set; role is `super_admin` |
| `test_register_duplicate_slug` | 409 on slug collision |
| `test_register_invalid_slug_uppercase` | 400 on uppercase slug |
| `test_register_invalid_slug_spaces` | 400 on slug with spaces |
| `test_register_returns_user_without_password` | No `password` / `hashed_password` in response |
| `test_login_success` | 200; access_token in response and cookie |
| `test_login_wrong_password` | 401 with "Invalid credentials" |
| `test_login_unknown_email` | 401 |
| `test_login_inactive_user` | 401 for deactivated user |
| `test_login_inactive_org` | 403 when org.is_active = False |
| `test_refresh_success` | New access_token issued |
| `test_refresh_no_cookie` | 401 "No refresh token" |
| `test_refresh_with_access_token_rejected` | 401 when access token used as refresh token |
| `test_logout` | 200 "Logged out" |
| `test_after_logout_me_is_rejected` | 401 after logout |
| `test_me_authenticated` | 200; email, role, org_currency present |
| `test_me_unauthenticated` | 401 |
| `test_me_rejects_refresh_token` | 401 when refresh token used as access token |

### Clients (`test_clients.py`)

Covers: create (admin + sales allowed, viewer/accountant forbidden), list, get, update, tenant isolation (cross-org returns 404), soft delete behaviour, product assignment (assign, list, unassign, duplicate 409), eligible products endpoint (global + assigned).

### Products (`test_products.py`)

Covers: create (admin + sales allowed, viewer/accountant forbidden), list, get, update, soft delete (DELETE returns 204; deleted product excluded from list), `is_global` filter, tenant isolation, assigned-clients reverse lookup.

### Quotations (`test_quotations.py`)

| Area | Tests |
|---|---|
| Create | Success, auto-numbering (QUO-0001, QUO-0002), no-items 400, RBAC (sales allowed, viewer/accountant 403) |
| List | Basic list, filter by status, tenant isolation |
| Get | Success, not found 404, cross-org 404 |
| Update | Draft update succeeds, non-draft rejected 400, viewer 403 |
| Status transitions | send, reject double-send, approve, approve-requires-sent, reject-sent, reject-approved, reject-draft 400 |
| Convert to invoice | Creates invoice; copies line items and total; sets status=converted; non-approved 400; already-converted 400; viewer 403 |
| Numbering | No collision after gap (MAX-based assertion) |

### Invoices (`test_invoices.py`)

| Area | Tests |
|---|---|
| Create | Success, auto-numbering, no-items 400, RBAC |
| List | Basic list, status filter, client_id filter, skip/limit pagination, tenant isolation |
| Get | Success, not found 404, cross-org 404 |
| Update | Draft update; non-draft rejected; viewer 403 |
| Status transitions | send; mark-paid (sent→paid, overdue→paid); mark-paid forbidden for sales; mark-overdue (sent→overdue); mark-overdue forbidden for sales; cancel draft; cancel sent; cancel paid blocked 400 |
| Tenant isolation | POST and GET cross-org returns 404 |

---

## Test Fixtures

Defined in `tests/conftest.py`:

### Database fixtures

| Fixture | Scope | Description |
|---|---|---|
| `db_engine` | `session` | Creates SQLite engine; drops/recreates all tables once per test session |
| `db` | `function` | Fresh DB session per test, rolled back after each test |

### Client fixtures

Each fixture creates a user with the appropriate role by calling `POST /api/auth/register` (for admin) or `POST /api/users/` (for other roles), then returns an authenticated `TestClient`.

| Fixture | Role |
|---|---|
| `admin_client` | `super_admin` |
| `sales_client` | `sales` |
| `accountant_client` | `accountant` |
| `viewer_client` | `viewer` |
| `anon_client` | Unauthenticated `TestClient` |
| `second_org_admin` | `super_admin` in a different organisation (for tenant isolation tests) |

### Factory fixtures

| Fixture | Returns | Notes |
|---|---|---|
| `make_client(name?, email?, ...)` | `dict` (ClientOut) | Creates a client in the primary org |
| `make_product(name?, price?, is_global?)` | `dict` (ProductOut) | Creates a product in the primary org |
| `make_quotation(client?, product?)` | `dict` (QuotationDetailOut) | Creates a draft quotation with one line item |
| `make_invoice(client?, product?)` | `dict` (InvoiceDetailOut) | Creates a draft invoice with one line item |

---

## What Is Not Covered

### Endpoints not tested

| Endpoint | Reason |
|---|---|
| `GET /api/dashboard/stats` | Covered implicitly via invoice/quotation creation; no dedicated test file |
| `GET /api/reports/summary` | No dedicated test; period filtering logic untested |
| `GET /api/audit/` | No dedicated test; audit entries are created but not queried |
| `GET /api/invoices/{id}/pdf` | WeasyPrint PDF generation not tested (requires browser renderer) |
| `GET /api/quotations/{id}/pdf` | Same reason |
| `GET /health` | Health check not tested |

### Scenarios not covered

| Scenario | Notes |
|---|---|
| Token expiry | TestClient tokens never expire; clock-manipulation tests not written |
| Concurrent numbering | Race condition between two simultaneous quotation creates; acceptable risk at single-process scale |
| Large pagination | `skip`/`limit` tested for basic cases only |
| Invalid UUID path params | FastAPI returns 422 automatically; not explicitly asserted |
| DB constraint violations | FK violations, NOT NULL violations tested indirectly via status codes |
| PostgreSQL-specific behaviour | All tests run on SQLite; UUID coercion and decimal precision edge cases may differ |

### Integration not covered

- Email delivery (no email service in test environment)
- External webhooks
- Frontend integration

---

## CI/CD Recommendations

### GitHub Actions example

```yaml
name: Backend Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r backend/requirements.txt
      - run: pytest backend/tests/ -v --tb=short
        working-directory: .
```

### Recommendations

1. **Run tests on every PR** — the suite completes in ~10 seconds.
2. **Add a PostgreSQL service** to CI to catch any SQLite/PostgreSQL compatibility gaps:
   ```yaml
   services:
     postgres:
       image: postgres:15
       env:
         POSTGRES_PASSWORD: test
         POSTGRES_DB: billflow_test
   ```
   Then set `DATABASE_URL=postgresql://postgres:test@localhost/billflow_test` in the test environment.
3. **Add `pytest-cov`** to measure line coverage:
   ```bash
   pytest tests/ --cov=app --cov-report=html
   ```
4. **Separate smoke tests** for PDF and email delivery that only run on staging, not on every commit.
