from typing import Optional
from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str = ""
    token_type: str = "bearer"
    must_change_password: bool = False
    email_verified: bool = True
    requires_otp_verification: bool = False
    onboarding_status: str = "completed"
    subscription_status: str = "trial"
    plan: Optional[str] = None
    admin_email: Optional[str] = None


class RegisterOrgRequest(BaseModel):
    org_name: str
    org_slug: str
    currency: str = "USD"
    full_name: str
    email: EmailStr
    password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class ProductAdminLoginRequest(BaseModel):
    email: EmailStr
    password: str


class ProductAdminLoginResponse(BaseModel):
    challenge_token: str
    requires_otp_verification: bool = True
    message: str = "OTP sent to product admin email."


class ProductAdminOtpVerifyRequest(BaseModel):
    challenge_token: str
    otp: str


class ProductAdminTokenResponse(BaseModel):
    access_token: str
    refresh_token: str = ""
    token_type: str = "bearer"
