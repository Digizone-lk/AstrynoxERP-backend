# BillFlow API — Documentation

BillFlow is a multi-tenant SaaS billing platform. This directory contains the complete API reference for the backend.

---

## Contents

| File | Description |
|---|---|
| [`README.md`](./README.md) | Overview, conventions, error codes (you are here) |
| [`api-reference.md`](./api-reference.md) | Full endpoint reference for all modules |
| [`roles-and-permissions.md`](./roles-and-permissions.md) | Role-based access control matrix |

---

## Base URL

```
http://localhost:8000
```

All endpoints are prefixed with `/api`. The interactive Swagger UI is available at `/docs` and the ReDoc UI at `/redoc` when the server is running.

---

## Authentication

The API uses **httpOnly cookie-based JWT authentication**. No `Authorization` header is required.

### Flow

1. Call `POST /api/auth/login` — the server sets two httpOnly cookies:
   - `access_token` — short-lived JWT (default: 30 minutes)
   - `refresh_token` — long-lived JWT (default: 7 days)
2. All subsequent requests automatically include these cookies (browser/axios `withCredentials: true`).
3. When the access token expires, call `POST /api/auth/refresh` to silently issue new tokens.
4. Call `POST /api/auth/logout` to clear both cookies.

### Token cookies

| Cookie | Type | Expiry | Scope |
|---|---|---|---|
| `access_token` | httpOnly, SameSite=Lax | 30 min | All authenticated endpoints |
| `refresh_token` | httpOnly, SameSite=Lax | 7 days | `/api/auth/refresh` only |

> **Note:** Cookies are set with `Secure=True` in production environments only.

---

## Multi-tenancy

Every resource is scoped to an **organisation** (`org_id`). Users can only read and write data belonging to their own organisation. The `org_id` is extracted from the JWT — clients never need to pass it explicitly.

---

## Request & Response Format

- All request bodies use `Content-Type: application/json`.
- All responses are JSON.
- Decimal/monetary fields (prices, totals) are returned as strings with 2 decimal places (e.g. `"1500.00"`).
- Dates use `YYYY-MM-DD` format. Timestamps use ISO 8601 with UTC timezone.
- UUIDs are returned as lowercase hyphenated strings.

---

## Standard Error Responses

All errors follow this shape:

```json
{
  "detail": "Human-readable error message"
}
```

| HTTP Status | Meaning |
|---|---|
| `400 Bad Request` | Validation error or business rule violation |
| `401 Unauthorized` | Missing or expired access token |
| `403 Forbidden` | Authenticated but insufficient role |
| `404 Not Found` | Resource does not exist in this organisation |
| `409 Conflict` | Duplicate resource (slug, email, assignment) |
| `422 Unprocessable Entity` | Request body failed Pydantic validation |

---

## Pagination

Endpoints that return lists support `skip` and `limit` query parameters:

| Parameter | Default | Description |
|---|---|---|
| `skip` | `0` | Number of records to skip |
| `limit` | `50` or `100` | Maximum records to return |

---

## Roles

There are four user roles. See [`roles-and-permissions.md`](./roles-and-permissions.md) for the full matrix.

| Role | Value |
|---|---|
| Super Admin | `super_admin` |
| Accountant | `accountant` |
| Sales | `sales` |
| Viewer | `viewer` |
