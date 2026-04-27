from uuid import UUID
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr


class ClientCreate(BaseModel):
    name: str
    email: EmailStr          # required — needed to send quotations and invoices
    phone: Optional[str] = None
    address: Optional[str] = None
    contact_person: Optional[str] = None


class ClientUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None   # optional in PATCH — omit to leave unchanged
    phone: Optional[str] = None
    address: Optional[str] = None
    contact_person: Optional[str] = None
    is_active: Optional[bool] = None


class ClientOut(BaseModel):
    id: UUID
    org_id: UUID
    name: str
    email: Optional[str]
    phone: Optional[str]
    address: Optional[str]
    contact_person: Optional[str]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True
