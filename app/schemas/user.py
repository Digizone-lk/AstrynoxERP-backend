from uuid import UUID
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, EmailStr, field_validator
import re
from app.models.user import UserRole, DEFAULT_NOTIFICATION_PREFS

ALL_MODULES = ["dashboard", "clients", "products", "quotations", "invoices", "reports"]


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: str
    role: UserRole = UserRole.VIEWER


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


class UserOut(BaseModel):
    id: UUID
    org_id: UUID
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime
    org_currency: str = "USD"
    allowed_modules: Optional[List[str]] = None

    class Config:
        from_attributes = True


class UserModulesUpdate(BaseModel):
    allowed_modules: Optional[List[str]] = None  # null restores full access

    @field_validator("allowed_modules")
    @classmethod
    def validate_modules(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return v
        invalid = [m for m in v if m not in ALL_MODULES]
        if invalid:
            raise ValueError(f"Unknown modules: {invalid}. Valid: {ALL_MODULES}")
        return v


class UserProfileOut(UserOut):
    phone: Optional[str] = None
    job_title: Optional[str] = None
    timezone: str = "UTC"
    language: str = "en"
    avatar_url: Optional[str] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    job_title: Optional[str] = None
    timezone: Optional[str] = None
    language: Optional[str] = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        return v


class AdminPasswordReset(BaseModel):
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        return v


class NotificationPrefs(BaseModel):
    invoice_paid: bool = True
    invoice_overdue: bool = True
    quotation_approved: bool = True
    quotation_rejected: bool = True
    new_user_added: bool = False


class SessionOut(BaseModel):
    id: UUID
    device_info: Optional[str] = None
    ip_address: Optional[str] = None
    last_active_at: datetime
    created_at: datetime
    is_current: bool = False

    class Config:
        from_attributes = True


class UserActivityOut(BaseModel):
    id: UUID
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    extra_data: Optional[Dict[str, Any]] = None
    ip_address: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
