from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.modules.ims.routers import quotations_pdf
from app.modules.ims.routers import clients, organization, profile, quotations
from app.modules.ims.routers import products
from app.modules.ims.routers import users
from app.modules.ims.routers import invoices
from app.modules.ims.routers import dashboard
from app.modules.ims.routers import reports
from app.modules.ims.routers import audit, auth
from app.chat import routers

app = FastAPI(
    title="BillFlow API",
    description="Quotation, Invoicing & Billing SaaS",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
app.include_router(routers.router)


@app.get("/health")
def health():
    return {"status": "ok"}
