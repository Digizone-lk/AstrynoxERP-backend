from uuid import UUID
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class OrgOut(BaseModel):
    id: UUID
    name: str
    slug: str
    currency: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class OrgUpdate(BaseModel):
    name: Optional[str] = None
    currency: Optional[str] = None
