from uuid import UUID
from datetime import datetime
from pydantic import BaseModel
from app.schemas.product import ProductOut


class ClientProductAssign(BaseModel):
    product_id: UUID


class ClientProductOut(BaseModel):
    id: UUID
    client_id: UUID
    product_id: UUID
    product: ProductOut
    created_at: datetime

    class Config:
        from_attributes = True
