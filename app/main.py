import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.core.config import settings
from app.routers import quotations, quotations_pdf
from app.routers import clients
from app.routers import products
from app.routers import auth, users, profile, organization
from app.routers import invoices
from app.routers import dashboard
from app.routers import reports
from app.routers import audit

app = FastAPI(
    title="BillFlow API",
    description="Quotation, Invoicing & Billing SaaS",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files (avatars, etc.)
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

app.include_router(auth.router)
app.include_router(profile.router)   # must be before users.router — /me/* routes take priority over /{user_id}/*
app.include_router(users.router)
app.include_router(organization.router)
app.include_router(clients.router)
app.include_router(products.router)
app.include_router(quotations.router)
app.include_router(quotations_pdf.router)
app.include_router(invoices.router)
app.include_router(dashboard.router)
app.include_router(reports.router)
app.include_router(audit.router)


@app.get("/health")
def health():
    return {"status": "ok"}
