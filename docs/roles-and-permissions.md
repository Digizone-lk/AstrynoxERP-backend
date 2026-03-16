# Roles & Permissions

BillFlow uses role-based access control (RBAC). Every user belongs to exactly one organisation and has one of four roles.

---

## Role Definitions

| Role | Value | Description |
|---|---|---|
| **Super Admin** | `super_admin` | Full access to everything. Manages users, all financial records, and org settings. |
| **Accountant** | `accountant` | Read access to all data. Can mark invoices as paid/overdue. Can access reports and audit log. Cannot create/edit clients, products, or quotations. |
| **Sales** | `sales` | Can create and manage clients, products, quotations, and invoices. Cannot access reports or audit log. Cannot manage users. |
| **Viewer** | `viewer` | Read-only access to clients, products, quotations, and invoices. No financial or admin access. |

---

## Permission Matrix

`✅` = allowed  `❌` = denied  `—` = not applicable

### Auth

| Action | Super Admin | Accountant | Sales | Viewer |
|---|:---:|:---:|:---:|:---:|
| Register organisation | ✅ | ✅ | ✅ | ✅ |
| Login / Logout | ✅ | ✅ | ✅ | ✅ |
| Refresh token | ✅ | ✅ | ✅ | ✅ |
| Get own profile (`/me`) | ✅ | ✅ | ✅ | ✅ |

### Users

| Action | Super Admin | Accountant | Sales | Viewer |
|---|:---:|:---:|:---:|:---:|
| List users | ✅ | ❌ | ❌ | ❌ |
| Create user | ✅ | ❌ | ❌ | ❌ |
| Get user | ✅ | ❌ | ❌ | ❌ |
| Update user (role, name, active) | ✅ | ❌ | ❌ | ❌ |

### Clients

| Action | Super Admin | Accountant | Sales | Viewer |
|---|:---:|:---:|:---:|:---:|
| List / Get clients | ✅ | ✅ | ✅ | ✅ |
| Create / Update client | ✅ | ❌ | ✅ | ❌ |
| Assign / Unassign product | ✅ | ❌ | ✅ | ❌ |
| Get eligible products for client | ✅ | ✅ | ✅ | ✅ |
| List assigned products | ✅ | ✅ | ✅ | ✅ |

### Products

| Action | Super Admin | Accountant | Sales | Viewer |
|---|:---:|:---:|:---:|:---:|
| List / Get products | ✅ | ✅ | ✅ | ✅ |
| Create product | ✅ | ❌ | ✅ | ❌ |
| Update product | ✅ | ❌ | ✅ | ❌ |
| Delete product (soft) | ✅ | ❌ | ✅ | ❌ |
| Get assigned clients | ✅ | ✅ | ✅ | ✅ |

### Quotations

| Action | Super Admin | Accountant | Sales | Viewer |
|---|:---:|:---:|:---:|:---:|
| List / Get quotations | ✅ | ✅ | ✅ | ✅ |
| Create quotation | ✅ | ❌ | ✅ | ❌ |
| Update quotation (draft only) | ✅ | ❌ | ✅ | ❌ |
| Send quotation | ✅ | ❌ | ✅ | ❌ |
| Approve quotation | ✅ | ❌ | ✅ | ❌ |
| Reject quotation | ✅ | ❌ | ✅ | ❌ |
| Convert to invoice | ✅ | ❌ | ✅ | ❌ |
| Download PDF | ✅ | ✅ | ✅ | ✅ |

### Invoices

| Action | Super Admin | Accountant | Sales | Viewer |
|---|:---:|:---:|:---:|:---:|
| List / Get invoices | ✅ | ✅ | ✅ | ✅ |
| Create invoice | ✅ | ❌ | ✅ | ❌ |
| Update invoice (draft only) | ✅ | ❌ | ✅ | ❌ |
| Send invoice | ✅ | ❌ | ✅ | ❌ |
| Mark as paid | ✅ | ✅ | ❌ | ❌ |
| Mark as overdue | ✅ | ✅ | ❌ | ❌ |
| Cancel invoice | ✅ | ❌ | ✅ | ❌ |
| Download PDF | ✅ | ✅ | ✅ | ✅ |

### Dashboard

| Action | Super Admin | Accountant | Sales | Viewer |
|---|:---:|:---:|:---:|:---:|
| Get stats | ✅ | ✅ | ✅ | ✅ |

### Reports

| Action | Super Admin | Accountant | Sales | Viewer |
|---|:---:|:---:|:---:|:---:|
| Get report summary | ✅ | ✅ | ❌ | ❌ |

### Audit Log

| Action | Super Admin | Accountant | Sales | Viewer |
|---|:---:|:---:|:---:|:---:|
| List audit logs | ✅ | ✅ | ❌ | ❌ |

---

## Backend Enforcement

Role checks are implemented as FastAPI dependency functions in `app/dependencies.py`:

| Dependency | Allowed roles |
|---|---|
| `get_any_authenticated` | All roles (including viewer) |
| `get_sales_or_admin` | `super_admin`, `sales` |
| `get_accountant_or_admin` | `super_admin`, `accountant` |
| `get_super_admin` | `super_admin` only |
