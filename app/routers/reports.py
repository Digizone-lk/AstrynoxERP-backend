from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, extract, case
from datetime import datetime, timezone, date
from decimal import Decimal
from typing import Optional

from app.core.database import get_db
from app.dependencies import get_accountant_or_admin
from app.models.invoice import Invoice, InvoiceStatus
from app.models.quotation import Quotation, QuotationStatus
from app.models.client import Client
from app.models.user import User
from app.schemas.reports import (
    ReportSummary,
    RevenueByMonth,
    InvoiceStatusRow,
    QuotationStatusRow,
    TopClient,
)

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _period_filter(period: str):
    """Return (start_date, end_date) or (None, None) for 'all'."""
    today = date.today()
    if period == "this_month":
        return date(today.year, today.month, 1), today
    if period == "this_quarter":
        quarter_start_month = ((today.month - 1) // 3) * 3 + 1
        return date(today.year, quarter_start_month, 1), today
    if period == "this_year":
        return date(today.year, 1, 1), today
    return None, None  # "all"


@router.get("/summary", response_model=ReportSummary)
def get_report_summary(
    period: str = Query("this_year", regex="^(this_month|this_quarter|this_year|all)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_accountant_or_admin),
):
    org_id = current_user.org_id
    start_date, end_date = _period_filter(period)

    def apply_date_filter(q, date_col):
        if start_date:
            q = q.filter(date_col >= start_date, date_col <= end_date)
        return q

    # ── Invoice KPIs ──────────────────────────────────────────────────────────
    inv_base = db.query(Invoice).filter(
        Invoice.org_id == org_id,
        Invoice.status != InvoiceStatus.CANCELLED,
    )
    inv_base = apply_date_filter(inv_base, Invoice.issue_date)

    total_revenue = inv_base.filter(Invoice.status == InvoiceStatus.PAID).with_entities(
        func.coalesce(func.sum(Invoice.total), 0)
    ).scalar()

    total_invoiced = inv_base.with_entities(
        func.coalesce(func.sum(Invoice.total), 0)
    ).scalar()

    total_outstanding = inv_base.filter(
        Invoice.status.in_([InvoiceStatus.SENT, InvoiceStatus.OVERDUE])
    ).with_entities(func.coalesce(func.sum(Invoice.total), 0)).scalar()

    total_overdue = inv_base.filter(Invoice.status == InvoiceStatus.OVERDUE).with_entities(
        func.coalesce(func.sum(Invoice.total), 0)
    ).scalar()

    # ── Invoice status breakdown ───────────────────────────────────────────────
    inv_breakdown_q = (
        db.query(Invoice.status, func.count(Invoice.id), func.coalesce(func.sum(Invoice.total), 0))
        .filter(Invoice.org_id == org_id)
    )
    inv_breakdown_q = apply_date_filter(inv_breakdown_q, Invoice.issue_date)
    inv_breakdown_rows = inv_breakdown_q.group_by(Invoice.status).all()

    invoice_status_breakdown = [
        InvoiceStatusRow(status=row[0].value, count=row[1], total=Decimal(str(row[2])))
        for row in inv_breakdown_rows
    ]

    # ── Quotation status breakdown ─────────────────────────────────────────────
    quot_breakdown_q = (
        db.query(Quotation.status, func.count(Quotation.id))
        .filter(Quotation.org_id == org_id)
    )
    quot_breakdown_q = apply_date_filter(quot_breakdown_q, Quotation.issue_date)
    quot_breakdown_rows = quot_breakdown_q.group_by(Quotation.status).all()

    quotation_status_breakdown = [
        QuotationStatusRow(status=row[0].value, count=row[1])
        for row in quot_breakdown_rows
    ]

    # ── Revenue by month (paid invoices) ──────────────────────────────────────
    rev_q = (
        db.query(
            extract("year", Invoice.paid_at).label("year"),
            extract("month", Invoice.paid_at).label("month"),
            func.sum(Invoice.total).label("revenue"),
            func.count(Invoice.id).label("invoice_count"),
        )
        .filter(
            Invoice.org_id == org_id,
            Invoice.status == InvoiceStatus.PAID,
            Invoice.paid_at.isnot(None),
        )
    )
    if start_date:
        rev_q = rev_q.filter(Invoice.paid_at >= start_date, Invoice.paid_at <= end_date)

    monthly_rows = (
        rev_q.group_by("year", "month").order_by("year", "month").limit(24).all()
    )

    revenue_by_month = [
        RevenueByMonth(
            month=f"{int(r.year)}-{int(r.month):02d}",
            revenue=Decimal(str(r.revenue)),
            invoice_count=r.invoice_count,
        )
        for r in monthly_rows
    ]

    # ── Top clients by revenue ─────────────────────────────────────────────────
    top_q = (
        db.query(
            Client.id,
            Client.name,
            func.coalesce(func.sum(Invoice.total), 0).label("total_invoiced"),
            func.coalesce(
                func.sum(case((Invoice.status == InvoiceStatus.PAID, Invoice.total), else_=0)), 0
            ).label("total_paid"),
            func.coalesce(
                func.sum(
                    case(
                        (Invoice.status.in_([InvoiceStatus.SENT, InvoiceStatus.OVERDUE]), Invoice.total),
                        else_=0,
                    )
                ),
                0,
            ).label("outstanding"),
        )
        .join(Invoice, Invoice.client_id == Client.id)
        .filter(
            Client.org_id == org_id,
            Invoice.status != InvoiceStatus.CANCELLED,
        )
    )
    if start_date:
        top_q = top_q.filter(Invoice.issue_date >= start_date, Invoice.issue_date <= end_date)

    top_rows = (
        top_q.group_by(Client.id, Client.name)
        .order_by(func.sum(Invoice.total).desc())
        .limit(10)
        .all()
    )

    top_clients = [
        TopClient(
            client_id=str(r[0]),
            client_name=r[1],
            total_invoiced=Decimal(str(r[2])),
            total_paid=Decimal(str(r[3])),
            outstanding=Decimal(str(r[4])),
        )
        for r in top_rows
    ]

    return ReportSummary(
        period=period,
        total_revenue=Decimal(str(total_revenue)),
        total_invoiced=Decimal(str(total_invoiced)),
        total_outstanding=Decimal(str(total_outstanding)),
        total_overdue=Decimal(str(total_overdue)),
        invoice_status_breakdown=invoice_status_breakdown,
        quotation_status_breakdown=quotation_status_breakdown,
        revenue_by_month=revenue_by_month,
        top_clients=top_clients,
    )
