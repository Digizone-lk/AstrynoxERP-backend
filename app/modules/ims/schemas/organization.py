from uuid import UUID
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, field_validator


SUPPORTED_CURRENCIES = {
    "USD", "EUR", "GBP", "AUD", "CAD", "SGD", "INR", "LKR", "JPY", "CNY", "AED",
}

PDF_TEMPLATES = {"classic", "modern", "minimal"}


class OrgOut(BaseModel):
    id: UUID
    name: str
    slug: str
    currency: str
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    logo_url: Optional[str] = None
    pdf_template: str = "classic"
    subscription_status: str = "trial"
    plan: Optional[str] = None
    trial_start_date: Optional[datetime] = None
    trial_end_date: Optional[datetime] = None
    onboarding_status: str = "completed"

    class Config:
        from_attributes = True


class OrgUpdate(BaseModel):
    name: Optional[str] = None
    currency: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    logo_url: Optional[str] = None
    pdf_template: Optional[str] = None

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

    @field_validator("pdf_template")
    @classmethod
    def template_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in PDF_TEMPLATES:
            raise ValueError(f"Invalid template. Choose from: {sorted(PDF_TEMPLATES)}")
        return v


class ProductAdminInviteCreate(BaseModel):
    username: str
    email: EmailStr

    @field_validator("username")
    @classmethod
    def username_valid(cls, v: str) -> str:
        value = v.strip().lower()
        if not value:
            raise ValueError("Username cannot be blank")
        if not value.replace("-", "").replace("_", "").isalnum():
            raise ValueError("Username can only contain letters, numbers, hyphens, and underscores")
        return value


class ProductAdminInviteOut(BaseModel):
    id: UUID
    org_id: UUID
    user_id: UUID
    email: str
    username: str
    expires_at: datetime
    opened_at: Optional[datetime] = None
    used_at: Optional[datetime] = None
    invalidated: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ProductAdminOrgOut(OrgOut):
    paid_activated_at: Optional[datetime] = None
    paid_activated_by: Optional[str] = None


class PaidPlanUpdate(BaseModel):
    plan: str

    @field_validator("plan")
    @classmethod
    def plan_valid(cls, v: str) -> str:
        value = v.strip().lower()
        if value not in {"pro", "business"}:
            raise ValueError("Plan must be pro or business")
        return value


class InviteValidateRequest(BaseModel):
    token: str


class InviteValidateOut(BaseModel):
    email: str
    username: str
    expires_at: datetime


class OnboardingPasswordChange(BaseModel):
    new_password: str


class OnboardingOtpVerify(BaseModel):
    otp: str
