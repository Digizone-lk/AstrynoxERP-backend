# API Reference

Complete reference for all BillFlow API endpoints.

**Base URL:** `http://localhost:8000`
**Auth:** httpOnly cookie (`access_token`). See [README](./README.md) for the full auth flow.

---

## Table of Contents

- [Auth](#auth)
- [Users](#users)
- [Clients](#clients)
- [Products](#products)
- [Quotations](#quotations)
- [Invoices](#invoices)
- [Dashboard](#dashboard)
- [Reports](#reports)
- [Audit Log](#audit-log)

---

## Auth

### POST `/api/auth/register`

Register a new organisation and create its first Super Admin user. Sets `access_token` and `refresh_token` cookies.

**Access:** Public

**Request body:**

| Field | Type | Required | Description |
|---|---|:---:|---|
| `org_name` | string | ✅ | Display name of the organisation |
| `org_slug` | string | ✅ | Unique URL-safe identifier (lowercase, alphanumeric, hyphens only) |
| `currency` | string | — | Default currency code (default: `"USD"`) |
| `full_name` | string | ✅ | Admin user's full name |
| `email` | string (email) | ✅ | Admin user's email address |
| `password` | string | ✅ | Admin user's password (min 8 characters) |

**Response:** `201 Created` — [UserOut](#userout-object)

**Errors:**
- `400` — Invalid slug format
- `409` — Organisation slug already taken

---

### POST `/api/auth/login`

Authenticate and set session cookies.

**Access:** Public

**Request body:**

| Field | Type | Required | Description |
|---|---|:---:|---|
| `email` | string (email) | ✅ | User's email |
| `password` | string | ✅ | User's password |

**Response:** `200 OK`

```json
{
  "access_token": "<jwt>",
  "token_type": "bearer"
}
```

**Errors:**
- `401` — Invalid credentials
- `403` — Organisation is inactive

---

### POST `/api/auth/refresh`

Issue new access and refresh tokens using the existing refresh cookie.

**Access:** Public (requires valid `refresh_token` cookie)

**Response:** `200 OK` — same shape as login response.

**Errors:**
- `401` — Missing or invalid refresh token

---

### POST `/api/auth/logout`

Clear both auth cookies.

**Access:** Public

**Response:** `200 OK`

```json
{ "message": "Logged out" }
```

---

### GET `/api/auth/me`

Return the currently authenticated user's profile, including the organisation's default currency.

**Access:** Any authenticated user

**Response:** `200 OK` — [UserOut](#userout-object) with an additional `org_currency` field.

---

## Users

> All user endpoints require the `super_admin` role.

### GET `/api/users/`

List all users in the organisation.

**Access:** `super_admin`

**Response:** `200 OK` — array of [UserOut](#userout-object)

---

### POST `/api/users/`

Create a new user in the organisation.

**Access:** `super_admin`

**Request body:**

| Field | Type | Required | Description |
|---|---|:---:|---|
| `email` | string (email) | ✅ | User's email address |
| `full_name` | string | ✅ | Display name |
| `password` | string | ✅ | Initial password |
| `role` | [UserRole](#userrole) | — | Default: `"viewer"` |

**Response:** `201 Created` — [UserOut](#userout-object)

**Errors:**
- `409` — Email already exists in this organisation

---

### GET `/api/users/{user_id}`

Get a single user by ID.

**Access:** `super_admin`

**Response:** `200 OK` — [UserOut](#userout-object)

**Errors:**
- `404` — User not found

---

### PATCH `/api/users/{user_id}`

Update a user's name, role, or active status.

**Access:** `super_admin`

**Request body (all fields optional):**

| Field | Type | Description |
|---|---|---|
| `full_name` | string | New display name |
| `role` | [UserRole](#userrole) | New role |
| `is_active` | boolean | Activate or deactivate the user |

**Response:** `200 OK` — [UserOut](#userout-object)

**Errors:**
- `404` — User not found

---

## Clients

### GET `/api/clients/`

List all active clients in the organisation, ordered by name.

**Access:** Any authenticated user

**Response:** `200 OK` — array of [ClientOut](#clientout-object)

---

### POST `/api/clients/`

Create a new client.

**Access:** `super_admin`, `sales`

**Request body:**

| Field | Type | Required | Description |
|---|---|:---:|---|
| `name` | string | ✅ | Client / company name |
| `email` | string (email) | — | Contact email |
| `phone` | string | — | Phone number |
| `address` | string | — | Billing address |
| `contact_person` | string | — | Primary contact name |

**Response:** `201 Created` — [ClientOut](#clientout-object)

---

### GET `/api/clients/{client_id}`

Get a single client by ID.

**Access:** Any authenticated user

**Response:** `200 OK` — [ClientOut](#clientout-object)

**Errors:**
- `404` — Client not found

---

### PATCH `/api/clients/{client_id}`

Update a client's details.

**Access:** `super_admin`, `sales`

**Request body (all fields optional):** Same fields as create.

**Response:** `200 OK` — [ClientOut](#clientout-object)

**Errors:**
- `404` — Client not found

---

### GET `/api/clients/{client_id}/products`

Return all products eligible for this client — global products plus any explicitly assigned client-specific products.

**Access:** Any authenticated user

**Response:** `200 OK` — array of [ProductOut](#productout-object)

**Errors:**
- `404` — Client not found

---

### GET `/api/clients/{client_id}/assigned-products`

List only the explicitly assigned (client-specific) products for a client.

**Access:** Any authenticated user

**Response:** `200 OK` — array of [ClientProductOut](#clientproductout-object)

**Errors:**
- `404` — Client not found

---

### POST `/api/clients/{client_id}/assigned-products`

Assign a client-specific product to a client.

**Access:** `super_admin`, `sales`

**Request body:**

| Field | Type | Required | Description |
|---|---|:---:|---|
| `product_id` | UUID | ✅ | ID of the product to assign |

**Response:** `201 Created` — [ClientProductOut](#clientproductout-object)

**Errors:**
- `404` — Client or product not found
- `409` — Product already assigned to this client

---

### DELETE `/api/clients/{client_id}/assigned-products/{product_id}`

Remove a product assignment from a client.

**Access:** `super_admin`, `sales`

**Response:** `204 No Content`

**Errors:**
- `404` — Assignment not found

---

## Products

### GET `/api/products/`

List all active products in the organisation.

**Access:** Any authenticated user

**Query parameters:**

| Parameter | Type | Description |
|---|---|---|
| `is_global` | boolean | Filter by global/client-specific |

**Response:** `200 OK` — array of [ProductOut](#productout-object)

---

### POST `/api/products/`

Create a new product.

**Access:** `super_admin`, `sales`

**Request body:**

| Field | Type | Required | Description |
|---|---|:---:|---|
| `name` | string | ✅ | Product name |
| `description` | string | — | Optional description |
| `unit_price` | decimal | ✅ | Price per unit |
| `unit` | string | — | Unit label (default: `"pcs"`) |
| `currency` | string | — | Currency code (default: `"USD"`) |
| `is_global` | boolean | — | Available to all clients (default: `true`) |

**Response:** `201 Created` — [ProductOut](#productout-object)

---

### GET `/api/products/{product_id}`

Get a single product by ID.

**Access:** Any authenticated user

**Response:** `200 OK` — [ProductOut](#productout-object)

**Errors:**
- `404` — Product not found

---

### PATCH `/api/products/{product_id}`

Update a product.

**Access:** `super_admin`, `sales`

**Request body (all fields optional):**

| Field | Type | Description |
|---|---|---|
| `name` | string | Product name |
| `description` | string | Optional description |
| `unit_price` | decimal | Price per unit |
| `unit` | string | Unit label |
| `currency` | string | Currency code |
| `is_global` | boolean | Availability scope |
| `is_active` | boolean | Soft delete / restore |

**Response:** `200 OK` — [ProductOut](#productout-object)

**Errors:**
- `404` — Product not found

---

### DELETE `/api/products/{product_id}`

Soft-delete a product (sets `is_active = false`).

**Access:** `super_admin`, `sales`

**Response:** `204 No Content`

**Errors:**
- `404` — Product not found

---

### GET `/api/products/{product_id}/assigned-clients`

List all clients that have this product explicitly assigned (only meaningful for non-global products).

**Access:** Any authenticated user

**Response:** `200 OK` — array of [ClientOut](#clientout-object)

**Errors:**
- `404` — Product not found

---

## Quotations

### GET `/api/quotations/`

List quotations with optional filters.

**Access:** Any authenticated user

**Query parameters:**

| Parameter | Type | Description |
|---|---|---|
| `status` | [QuotationStatus](#quotationstatus) | Filter by status |
| `client_id` | UUID | Filter by client |
| `skip` | integer | Pagination offset (default: `0`) |
| `limit` | integer | Max results (default: `50`) |

**Response:** `200 OK` — array of [QuotationOut](#quotationout-object)

---

### POST `/api/quotations/`

Create a new quotation.

**Access:** `super_admin`, `sales`

**Request body:**

| Field | Type | Required | Description |
|---|---|:---:|---|
| `client_id` | UUID | ✅ | Client for this quotation |
| `issue_date` | date (`YYYY-MM-DD`) | ✅ | Date of issue |
| `valid_until` | date (`YYYY-MM-DD`) | — | Expiry date |
| `notes` | string | — | Internal / client-facing notes |
| `currency` | string | — | Currency code (default: `"USD"`) |
| `items` | array of [QuotationItemCreate](#quotationitemcreate) | ✅ | At least one item required |

**Response:** `201 Created` — [QuotationDetailOut](#quotationdetailout-object)

**Errors:**
- `400` — No items provided

---

### GET `/api/quotations/{quotation_id}`

Get a quotation with its line items and client.

**Access:** Any authenticated user

**Response:** `200 OK` — [QuotationDetailOut](#quotationdetailout-object)

**Errors:**
- `404` — Quotation not found

---

### PATCH `/api/quotations/{quotation_id}`

Update a quotation. Only allowed when status is `draft`.

**Access:** `super_admin`, `sales`

**Request body (all fields optional):**

| Field | Type | Description |
|---|---|---|
| `issue_date` | date | New issue date |
| `valid_until` | date | New expiry date |
| `notes` | string | Updated notes |
| `items` | array of [QuotationItemCreate](#quotationitemcreate) | Replaces all existing line items |

**Response:** `200 OK` — [QuotationDetailOut](#quotationdetailout-object)

**Errors:**
- `400` — Quotation is not in `draft` status
- `404` — Quotation not found

---

### POST `/api/quotations/{quotation_id}/send`

Transition status from `draft` → `sent`.

**Access:** `super_admin`, `sales`

**Response:** `200 OK` — [QuotationOut](#quotationout-object)

**Errors:**
- `400` — Not in `draft` status
- `404` — Quotation not found

---

### POST `/api/quotations/{quotation_id}/approve`

Transition status from `sent` → `approved`.

**Access:** `super_admin`, `sales`

**Response:** `200 OK` — [QuotationOut](#quotationout-object)

**Errors:**
- `400` — Not in `sent` status
- `404` — Quotation not found

---

### POST `/api/quotations/{quotation_id}/reject`

Transition status from `sent` or `approved` → `rejected`.

**Access:** `super_admin`, `sales`

**Response:** `200 OK` — [QuotationOut](#quotationout-object)

**Errors:**
- `400` — Invalid status for rejection
- `404` — Quotation not found

---

### POST `/api/quotations/{quotation_id}/convert-to-invoice`

Convert an `approved` quotation into an invoice. Quotation status becomes `converted`.

**Access:** `super_admin`, `sales`

**Response:** `201 Created`

```json
{
  "invoice_id": "<uuid>",
  "invoice_number": "INV-0001"
}
```

**Errors:**
- `400` — Quotation is not `approved` (also fires if already `converted`)
- `404` — Quotation not found

---

### GET `/api/quotations/{quotation_id}/pdf`

Download the quotation as a PDF file.

**Access:** Any authenticated user

**Response:** `200 OK` — `application/pdf` binary stream
`Content-Disposition: attachment; filename="QUO-0001.pdf"`

**Errors:**
- `404` — Quotation not found

---

## Invoices

### GET `/api/invoices/`

List invoices with optional filters.

**Access:** Any authenticated user

**Query parameters:**

| Parameter | Type | Description |
|---|---|---|
| `status` | [InvoiceStatus](#invoicestatus) | Filter by status |
| `client_id` | UUID | Filter by client |
| `skip` | integer | Pagination offset (default: `0`) |
| `limit` | integer | Max results (default: `50`) |

**Response:** `200 OK` — array of [InvoiceOut](#invoiceout-object)

---

### POST `/api/invoices/`

Create a new invoice.

**Access:** `super_admin`, `sales`

**Request body:**

| Field | Type | Required | Description |
|---|---|:---:|---|
| `client_id` | UUID | ✅ | Client for this invoice |
| `quotation_id` | UUID | — | Source quotation (if converted) |
| `issue_date` | date (`YYYY-MM-DD`) | ✅ | Date of issue |
| `due_date` | date (`YYYY-MM-DD`) | — | Payment due date |
| `notes` | string | — | Notes |
| `currency` | string | — | Currency code (default: `"USD"`) |
| `items` | array of [InvoiceItemCreate](#invoiceitemcreate) | ✅ | At least one item required |

**Response:** `201 Created` — [InvoiceDetailOut](#invoicedetailout-object)

**Errors:**
- `400` — No items provided

---

### GET `/api/invoices/{invoice_id}`

Get an invoice with its line items and client.

**Access:** Any authenticated user

**Response:** `200 OK` — [InvoiceDetailOut](#invoicedetailout-object)

**Errors:**
- `404` — Invoice not found

---

### PATCH `/api/invoices/{invoice_id}`

Update an invoice. Only allowed when status is `draft`.

**Access:** `super_admin`, `sales`

**Request body (all fields optional):**

| Field | Type | Description |
|---|---|---|
| `issue_date` | date | New issue date |
| `due_date` | date | New due date |
| `notes` | string | Updated notes |
| `items` | array of [InvoiceItemCreate](#invoiceitemcreate) | Replaces all existing line items |

**Response:** `200 OK` — [InvoiceDetailOut](#invoicedetailout-object)

**Errors:**
- `400` — Invoice is not in `draft` status
- `404` — Invoice not found

---

### POST `/api/invoices/{invoice_id}/send`

Transition status from `draft` → `sent`.

**Access:** `super_admin`, `sales`

**Response:** `200 OK` — [InvoiceOut](#invoiceout-object)

**Errors:**
- `400` — Not in `draft` status
- `404` — Invoice not found

---

### POST `/api/invoices/{invoice_id}/mark-paid`

Transition status from `sent` or `overdue` → `paid`. Records `paid_at` timestamp.

**Access:** `super_admin`, `accountant`

**Response:** `200 OK` — [InvoiceOut](#invoiceout-object)

**Errors:**
- `400` — Invoice must be `sent` or `overdue`
- `404` — Invoice not found

---

### POST `/api/invoices/{invoice_id}/mark-overdue`

Transition status from `sent` → `overdue`.

**Access:** `super_admin`, `accountant`

**Response:** `200 OK` — [InvoiceOut](#invoiceout-object)

**Errors:**
- `400` — Invoice must be `sent`
- `404` — Invoice not found

---

### POST `/api/invoices/{invoice_id}/cancel`

Cancel an invoice. Not allowed if already paid.

**Access:** `super_admin`, `sales`

**Response:** `200 OK` — [InvoiceOut](#invoiceout-object)

**Errors:**
- `400` — Cannot cancel a paid invoice
- `404` — Invoice not found

---

### GET `/api/invoices/{invoice_id}/pdf`

Download the invoice as a PDF file.

**Access:** Any authenticated user

**Response:** `200 OK` — `application/pdf` binary stream
`Content-Disposition: attachment; filename="INV-0001.pdf"`

**Errors:**
- `404` — Invoice not found

---

## Dashboard

### GET `/api/dashboard/stats`

Return KPI statistics for the authenticated user's organisation.

**Access:** Any authenticated user

**Response:** `200 OK`

```json
{
  "total_revenue": "150000.00",
  "outstanding_amount": "40000.00",
  "paid_invoices_count": 15,
  "overdue_invoices_count": 2,
  "draft_quotations_count": 3,
  "sent_quotations_count": 5,
  "total_clients": 12,
  "total_products": 8,
  "recent_invoices_count": 25,
  "monthly_revenue": [
    { "month": "2026-01", "revenue": "20000.00" },
    { "month": "2026-02", "revenue": "35000.00" }
  ]
}
```

---

## Reports

### GET `/api/reports/summary`

Return a comprehensive financial report for the organisation. Supports period filtering.

**Access:** `super_admin`, `accountant`

**Query parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `period` | string | `this_year` | One of: `this_month`, `this_quarter`, `this_year`, `all` |

**Response:** `200 OK`

```json
{
  "period": "this_year",
  "total_revenue": "150000.00",
  "total_invoiced": "190000.00",
  "total_outstanding": "30000.00",
  "total_overdue": "10000.00",
  "invoice_status_breakdown": [
    { "status": "paid",    "count": 15, "total": "150000.00" },
    { "status": "sent",    "count": 4,  "total": "20000.00"  },
    { "status": "overdue", "count": 2,  "total": "10000.00"  },
    { "status": "draft",   "count": 3,  "total": "10000.00"  }
  ],
  "quotation_status_breakdown": [
    { "status": "draft",     "count": 3 },
    { "status": "sent",      "count": 5 },
    { "status": "approved",  "count": 4 },
    { "status": "converted", "count": 4 },
    { "status": "rejected",  "count": 1 }
  ],
  "revenue_by_month": [
    { "month": "2026-01", "revenue": "20000.00", "invoice_count": 3 },
    { "month": "2026-02", "revenue": "35000.00", "invoice_count": 5 }
  ],
  "top_clients": [
    {
      "client_id": "uuid",
      "client_name": "Acme Corp",
      "total_invoiced": "50000.00",
      "total_paid": "40000.00",
      "outstanding": "10000.00"
    }
  ]
}
```

**Errors:**
- `403` — Insufficient role (`sales` or `viewer`)

---

## Audit Log

### GET `/api/audit/`

List audit log entries for the organisation, most recent first.

**Access:** `super_admin`, `accountant`

**Query parameters:**

| Parameter | Type | Description |
|---|---|---|
| `resource_type` | string | Filter by resource (e.g. `invoice`, `client`, `user`) |
| `action` | string | Filter by action (e.g. `CREATE`, `UPDATE`, `STATUS_CHANGE`) |
| `skip` | integer | Pagination offset (default: `0`) |
| `limit` | integer | Max results (default: `100`) |

**Response:** `200 OK`

```json
[
  {
    "id": "uuid",
    "org_id": "uuid",
    "user_id": "uuid",
    "action": "STATUS_CHANGE",
    "resource_type": "invoice",
    "resource_id": "uuid",
    "extra_data": { "status": "paid" },
    "ip_address": "192.168.1.1",
    "created_at": "2026-03-16T10:30:00Z"
  }
]
```

---

## Schema Objects

### UserOut object

```json
{
  "id": "uuid",
  "org_id": "uuid",
  "email": "user@example.com",
  "full_name": "Jane Smith",
  "role": "accountant",
  "is_active": true,
  "created_at": "2026-01-01T00:00:00Z",
  "org_currency": "LKR"
}
```

### UserRole

`"super_admin"` | `"accountant"` | `"sales"` | `"viewer"`

---

### ClientOut object

```json
{
  "id": "uuid",
  "org_id": "uuid",
  "name": "Acme Corp",
  "email": "billing@acme.com",
  "phone": "+94 11 234 5678",
  "address": "123 Main St, Colombo",
  "contact_person": "John Doe",
  "is_active": true,
  "created_at": "2026-01-01T00:00:00Z"
}
```

---

### ProductOut object

```json
{
  "id": "uuid",
  "org_id": "uuid",
  "name": "Security Uniform",
  "description": "Standard LSO uniform",
  "unit_price": "2500.00",
  "unit": "pcs",
  "currency": "LKR",
  "is_global": true,
  "is_active": true,
  "created_at": "2026-01-01T00:00:00Z"
}
```

---

### ClientProductOut object

```json
{
  "id": "uuid",
  "org_id": "uuid",
  "client_id": "uuid",
  "product_id": "uuid",
  "created_at": "2026-01-01T00:00:00Z"
}
```

---

### QuotationOut object

```json
{
  "id": "uuid",
  "org_id": "uuid",
  "client_id": "uuid",
  "quote_number": "QUO-0001",
  "status": "draft",
  "issue_date": "2026-03-16",
  "valid_until": "2026-04-16",
  "notes": "Payment due within 30 days.",
  "subtotal": "10000.00",
  "total": "10000.00",
  "currency": "LKR",
  "created_at": "2026-03-16T00:00:00Z"
}
```

### QuotationDetailOut object

Extends `QuotationOut` with:

```json
{
  "client": { /* ClientOut */ },
  "items": [
    {
      "id": "uuid",
      "product_id": "uuid",
      "product_name": "Security Uniform",
      "description": null,
      "qty": "10.00",
      "unit_price": "2500.00",
      "subtotal": "25000.00",
      "sort_order": 0
    }
  ]
}
```

### QuotationStatus

`"draft"` | `"sent"` | `"approved"` | `"rejected"` | `"converted"`

**Valid status transitions:**

```
draft → sent → approved → converted
             ↓
           rejected
```

---

### QuotationItemCreate

```json
{
  "product_id": "uuid (optional)",
  "product_name": "Security Uniform",
  "description": "Optional line description",
  "qty": "10",
  "unit_price": "2500.00"
}
```

---

### InvoiceOut object

```json
{
  "id": "uuid",
  "org_id": "uuid",
  "client_id": "uuid",
  "quotation_id": null,
  "invoice_number": "INV-0001",
  "status": "draft",
  "issue_date": "2026-03-16",
  "due_date": "2026-04-16",
  "paid_at": null,
  "notes": null,
  "subtotal": "25000.00",
  "total": "25000.00",
  "currency": "LKR",
  "created_at": "2026-03-16T00:00:00Z"
}
```

### InvoiceDetailOut object

Extends `InvoiceOut` with `client` and `items` (same structure as quotation detail).

### InvoiceStatus

`"draft"` | `"sent"` | `"paid"` | `"overdue"` | `"cancelled"`

**Valid status transitions:**

```
draft → sent → paid
             ↓
           overdue → paid
draft/sent/overdue → cancelled
```

---

### InvoiceItemCreate

Same shape as `QuotationItemCreate`.
