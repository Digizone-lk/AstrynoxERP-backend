from uuid import UUID
from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from app.modules.ims.schemas.product import ProductOut


class ClientProductAssign(BaseModel):
    product_id: UUID


class ClientProductOut(BaseModel):
    id: UUID
    org_id: UUID
    client_id: UUID
    product_id: UUID
    created_at: datetime
    product: Optional[ProductOut] = None

    class Config:
        from_attributes = True
