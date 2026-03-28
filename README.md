# BillFlow — Quotation, Invoicing & Billing SaaS

A full-stack multi-tenant SaaS built with **FastAPI** (Python) + **Next.js 14** (TypeScript).

---

## Features

- **Multi-tenancy** — each organization is isolated
- **4 roles** — Super Admin, Accountant, Sales, Viewer
- **Client management** with client-specific product assignments
- **Products** — global (all clients) or client-specific (only when that client is selected)
- **Quotations** — draft → sent → approved/rejected → convert to invoice
- **Invoices** — direct creation or from quotation; draft → sent → paid/overdue/cancelled
- **Auto-numbered** documents (QUO-0001, INV-0001) per organization
- **PDF export** for invoices and quotations
- **Dashboard** with KPI cards and monthly revenue chart
- **Audit log** — all write operations tracked (visible to Accountant + Super Admin)
- **JWT auth** with httpOnly cookies + refresh token rotation

---

## Quick Start (Docker)

```bash
# 1. Clone the repo
git clone ... && cd saas-billing

# 2. Start everything
docker-compose up --build

# 3. Open the app
open http://localhost:3000
```

The first time you open the app you'll be redirected to `/register` to create your organization and Super Admin account.

---

## Local Development

### Backend

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy env file
cp .env.example .env
# Edit .env with your Postgres credentials

# Run migrations
alembic upgrade head

# Start dev server
uvicorn app.main:app --reload --port 8000
```

API docs available at: http://localhost:8000/docs

### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Set env
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local

# Start dev server
npm run dev
```

Open http://localhost:3000

---

## Architecture

```
saas-billing/
├── backend/              # FastAPI + SQLAlchemy + Alembic
│   ├── app/
│   │   ├── core/         # Config, DB, JWT security
│   │   ├── models/       # SQLAlchemy ORM models
│   │   ├── schemas/      # Pydantic schemas
│   │   ├── routers/      # API route handlers
│   │   ├── services/     # Business logic (audit, PDF, numbering)
│   │   └── main.py       # FastAPI app entry point
│   └── alembic/          # DB migrations
└── frontend/             # Next.js 14 App Router
    ├── app/
    │   ├── (auth)/       # Login + Register pages
    │   └── (app)/        # Protected app pages
    ├── components/       # Reusable components
    └── lib/              # API client, types, utilities
```

---

## Roles & Permissions

| Feature               | Super Admin | Accountant | Sales | Viewer |
|-----------------------|:-----------:|:----------:|:-----:|:------:|
| Create/edit clients   | ✓           | ✗          | ✓     | ✗      |
| Create/edit products  | ✓           | ✗          | ✓     | ✗      |
| Create quotations     | ✓           | ✗          | ✓     | ✗      |
| Create invoices       | ✓           | ✗          | ✓     | ✗      |
| Mark invoice paid     | ✓           | ✓          | ✗     | ✗      |
| Mark invoice overdue  | ✓           | ✓          | ✗     | ✗      |
| View audit log        | ✓           | ✓          | ✗     | ✗      |
| Manage users          | ✓           | ✗          | ✗     | ✗      |
| View all records      | ✓           | ✓          | ✓     | ✓      |

---

## Client-Specific Products

When creating a quotation or invoice:
1. Select a **client** first
2. The product picker shows only **eligible products**:
   - All products with `is_global = true`
   - Products explicitly assigned to the selected client (via the Client detail page)

This ensures products like "Security Uniform (LSO)" only appear for "Octogon Force Pvt Ltd".

---

## Environment Variables

### Backend
| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `SECRET_KEY` | JWT signing secret (min 32 chars in production) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access token TTL (default: 30) |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Refresh token TTL (default: 7) |
| `FRONTEND_URL` | CORS allowed origin |

### Frontend
| Variable | Description |
|---|---|
| `NEXT_PUBLIC_API_URL` | FastAPI backend URL |
