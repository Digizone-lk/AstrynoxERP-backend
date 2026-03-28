from uuid import UUID
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, field_validator


SUPPORTED_CURRENCIES = {
    "USD", "EUR", "GBP", "AUD", "CAD", "SGD", "INR", "LKR", "JPY", "CNY", "AED",
}


class OrgOut(BaseModel):
    id: UUID
    name: str
    slug: str
    currency: str
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class OrgUpdate(BaseModel):
    name: Optional[str] = None
    currency: Optional[str] = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.strip():
            raise ValueError("Name cannot be blank")
        return v.strip() if v else v

    @field_validator("currency")
    @classmethod
    def currency_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v.upper() not in SUPPORTED_CURRENCIES:
            raise ValueError(f"Unsupported currency. Supported: {sorted(SUPPORTED_CURRENCIES)}")
        return v.upper() if v else v
