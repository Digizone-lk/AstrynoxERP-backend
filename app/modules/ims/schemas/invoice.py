from uuid import UUID
from datetime import datetime, date
from typing import Optional, List
from decimal import Decimal
from pydantic import BaseModel
from app.modules.ims.models.invoice import InvoiceStatus
from app.modules.ims.schemas.client import ClientOut


class InvoiceItemCreate(BaseModel):
    product_id: Optional[UUID] = None
    product_name: str
    description: Optional[str] = None
    qty: Decimal
    unit_price: Decimal


class InvoiceItemOut(BaseModel):
    id: UUID
    product_id: Optional[UUID]
    product_name: str
    description: Optional[str]
    qty: Decimal
    unit_price: Decimal
    subtotal: Decimal
    sort_order: int

    class Config:
        from_attributes = True


class InvoiceCreate(BaseModel):
    client_id: UUID
    quotation_id: Optional[UUID] = None  # If converting from quotation
    issue_date: date
    due_date: Optional[date] = None
    notes: Optional[str] = None
    currency: str = "USD"
    items: List[InvoiceItemCreate]


class InvoiceUpdate(BaseModel):
    issue_date: Optional[date] = None
    due_date: Optional[date] = None
    notes: Optional[str] = None
    items: Optional[List[InvoiceItemCreate]] = None


class InvoiceOut(BaseModel):
    id: UUID
    org_id: UUID
    client_id: UUID
    quotation_id: Optional[UUID]
    invoice_number: str
    status: InvoiceStatus
    issue_date: date
    due_date: Optional[date]
    paid_at: Optional[datetime]
    notes: Optional[str]
    subtotal: Decimal
    total: Decimal
    currency: str
    created_at: datetime

    class Config:
        from_attributes = True


class InvoiceDetailOut(InvoiceOut):
    client: ClientOut
    items: List[InvoiceItemOut]

    class Config:
        from_attributes = True
