from uuid import UUID
from datetime import datetime, date
from typing import Optional, List
from decimal import Decimal
from pydantic import BaseModel
from app.modules.ims.models.quotation import QuotationStatus
from app.modules.ims.schemas.client import ClientOut


class QuotationItemCreate(BaseModel):
    product_id: Optional[UUID] = None
    product_name: str
    description: Optional[str] = None
    qty: Decimal
    unit_price: Decimal


class QuotationItemOut(BaseModel):
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


class QuotationCreate(BaseModel):
    client_id: UUID
    issue_date: date
    valid_until: Optional[date] = None
    notes: Optional[str] = None
    currency: str = "USD"
    items: List[QuotationItemCreate]


class QuotationUpdate(BaseModel):
    issue_date: Optional[date] = None
    valid_until: Optional[date] = None
    notes: Optional[str] = None
    items: Optional[List[QuotationItemCreate]] = None


class QuotationOut(BaseModel):
    id: UUID
    org_id: UUID
    client_id: UUID
    quote_number: str
    status: QuotationStatus
    issue_date: date
    valid_until: Optional[date]
    notes: Optional[str]
    subtotal: Decimal
    total: Decimal
    currency: str
    created_at: datetime

    class Config:
        from_attributes = True


class QuotationDetailOut(QuotationOut):
    client: ClientOut
    items: List[QuotationItemOut]

    class Config:
        from_attributes = True
