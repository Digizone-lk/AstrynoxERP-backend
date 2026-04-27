from typing import List
from decimal import Decimal
from pydantic import BaseModel


class RevenueByMonth(BaseModel):
    month: str
    revenue: Decimal
    invoice_count: int


class InvoiceStatusRow(BaseModel):
    status: str
    count: int
    total: Decimal


class QuotationStatusRow(BaseModel):
    status: str
    count: int


class TopClient(BaseModel):
    client_id: str
    client_name: str
    total_invoiced: Decimal
    total_paid: Decimal
    outstanding: Decimal


class ReportSummary(BaseModel):
    period: str
    total_revenue: Decimal
    total_invoiced: Decimal
    total_outstanding: Decimal
    total_overdue: Decimal
    invoice_status_breakdown: List[InvoiceStatusRow]
    quotation_status_breakdown: List[QuotationStatusRow]
    revenue_by_month: List[RevenueByMonth]
    top_clients: List[TopClient]
