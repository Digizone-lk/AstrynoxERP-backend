from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str = ""
    token_type: str = "bearer"


class RegisterOrgRequest(BaseModel):
    org_name: str
    org_slug: str
    currency: str = "USD"
    full_name: str
    email: EmailStr
    password: str
