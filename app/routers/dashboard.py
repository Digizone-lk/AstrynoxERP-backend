from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from datetime import datetime, timezone
from app.core.database import get_db
from app.dependencies import get_any_authenticated
from app.models.invoice import Invoice, InvoiceStatus
from app.models.quotation import Quotation, QuotationStatus
from app.models.client import Client
from app.models.product import Product
from app.models.user import User
from app.schemas.dashboard import DashboardStats, MonthlyRevenue
from decimal import Decimal

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStats)
def get_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_any_authenticated),
):
    org_id = current_user.org_id

    total_revenue = db.query(func.coalesce(func.sum(Invoice.total), 0)).filter(
        Invoice.org_id == org_id, Invoice.status == InvoiceStatus.PAID
    ).scalar()

    outstanding = db.query(func.coalesce(func.sum(Invoice.total), 0)).filter(
        Invoice.org_id == org_id, Invoice.status.in_([InvoiceStatus.SENT, InvoiceStatus.OVERDUE])
    ).scalar()

    paid_count = db.query(func.count(Invoice.id)).filter(
        Invoice.org_id == org_id, Invoice.status == InvoiceStatus.PAID
    ).scalar()

    overdue_count = db.query(func.count(Invoice.id)).filter(
        Invoice.org_id == org_id, Invoice.status == InvoiceStatus.OVERDUE
    ).scalar()

    draft_quotes = db.query(func.count(Quotation.id)).filter(
        Quotation.org_id == org_id, Quotation.status == QuotationStatus.DRAFT
    ).scalar()

    sent_quotes = db.query(func.count(Quotation.id)).filter(
        Quotation.org_id == org_id, Quotation.status == QuotationStatus.SENT
    ).scalar()

    total_clients = db.query(func.count(Client.id)).filter(
        Client.org_id == org_id, Client.is_active == True
    ).scalar()

    total_products = db.query(func.count(Product.id)).filter(
        Product.org_id == org_id, Product.is_active == True
    ).scalar()

    recent_invoices = db.query(func.count(Invoice.id)).filter(Invoice.org_id == org_id).scalar()

    # Monthly revenue for last 12 months
    monthly_rows = (
        db.query(
            extract("year", Invoice.paid_at).label("year"),
            extract("month", Invoice.paid_at).label("month"),
            func.sum(Invoice.total).label("revenue"),
        )
        .filter(
            Invoice.org_id == org_id,
            Invoice.status == InvoiceStatus.PAID,
            Invoice.paid_at.isnot(None),
        )
        .group_by("year", "month")
        .order_by("year", "month")
        .limit(12)
        .all()
    )

    monthly_revenue = [
        MonthlyRevenue(month=f"{int(row.year)}-{int(row.month):02d}", revenue=Decimal(str(row.revenue)))
        for row in monthly_rows
    ]

    return DashboardStats(
        total_revenue=Decimal(str(total_revenue)),
        outstanding_amount=Decimal(str(outstanding)),
        paid_invoices_count=paid_count,
        overdue_invoices_count=overdue_count,
        draft_quotations_count=draft_quotes,
        sent_quotations_count=sent_quotes,
        total_clients=total_clients,
        total_products=total_products,
        monthly_revenue=monthly_revenue,
        recent_invoices_count=recent_invoices,
    )
