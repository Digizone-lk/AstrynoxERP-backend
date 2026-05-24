from uuid import UUID
from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel


class AuditLogOut(BaseModel):
    id: UUID
    org_id: UUID
    user_id: Optional[UUID]
    action: str
    resource_type: str
    resource_id: Optional[str]
    extra_data: Optional[Any]
    ip_address: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True
