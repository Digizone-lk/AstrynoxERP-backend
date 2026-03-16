from uuid import UUID
from datetime import datetime
from typing import Optional
from decimal import Decimal
from pydantic import BaseModel


class ProductCreate(BaseModel):
    name: str
    description: Optional[str] = None
    unit_price: Decimal
    unit: str = "pcs"
    currency: str = "USD"
    is_global: bool = True


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    unit_price: Optional[Decimal] = None
    unit: Optional[str] = None
    currency: Optional[str] = None
    is_global: Optional[bool] = None
    is_active: Optional[bool] = None


class ProductOut(BaseModel):
    id: UUID
    org_id: UUID
    name: str
    description: Optional[str]
    unit_price: Decimal
    unit: str
    currency: str
    is_global: bool
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True
