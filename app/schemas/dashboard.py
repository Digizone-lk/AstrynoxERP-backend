from typing import List
from decimal import Decimal
from pydantic import BaseModel


class MonthlyRevenue(BaseModel):
    month: str
    revenue: Decimal


class DashboardStats(BaseModel):
    total_revenue: Decimal
    outstanding_amount: Decimal  # Sent + overdue invoices
    paid_invoices_count: int
    overdue_invoices_count: int
    draft_quotations_count: int
    sent_quotations_count: int
    total_clients: int
    total_products: int
    monthly_revenue: List[MonthlyRevenue]
    recent_invoices_count: int
