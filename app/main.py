from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.routers import quotations, quotations_pdf

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

app.include_router(quotations.router)
app.include_router(quotations_pdf.router)


@app.get("/health")
def health():
    return {"status": "ok"}
