from uuid import UUID as PyUUID
from typing import List, Optional
from datetime import datetime, timezone
from fastapi import Depends, HTTPException, Request, status, Cookie, Header
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import decode_token
from app.core.config import settings
from app.modules.ims.models.organization import Organization
from app.modules.ims.models.user import User, UserRole


TRIAL_ALLOWED_PATHS = {
    "/api/auth/me",
    "/api/auth/refresh",
    "/api/auth/logout",
}


def _is_past(value) -> bool:
    if value is None:
        return False
    now = datetime.now(timezone.utc)
    if value.tzinfo is None:
        now = now.replace(tzinfo=None)
    return value < now


def enforce_organization_access(db: Session, user: User, request: Optional[Request] = None) -> Organization:
    org = db.query(Organization).filter(Organization.id == user.org_id).first()
    if not org or not org.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization is inactive")

    if org.subscription_status == "trial" and _is_past(org.trial_end_date):
        org.subscription_status = "trial_expired"
        db.commit()
        db.refresh(org)

    if org.subscription_status == "trial_expired":
        path = request.url.path if request else ""
        if path not in TRIAL_ALLOWED_PATHS:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "code": "TRIAL_EXPIRED",
                    "message": "Your 14-day trial has ended. Please contact the platform admin to continue using the platform.",
                    "admin_email": settings.PRODUCT_ADMIN_EMAIL,
                },
            )

    return org


def get_current_user(
    request: Request,
    access_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> User:
    # Prefer Authorization: Bearer header, fall back to cookie
    token: Optional[str] = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
    elif access_token:
        token = access_token

    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user_id_str = payload.get("sub")
    if not user_id_str:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    try:
        user_id = PyUUID(user_id_str)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    enforce_organization_access(db, user, request)
    return user


def require_roles(*roles: UserRole):
    def checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {[r.value for r in roles]}",
            )
        return current_user
    return checker


# Shorthand role guards
def get_super_admin(user: User = Depends(require_roles(UserRole.SUPER_ADMIN))) -> User:
    return user


def get_sales_or_admin(
    user: User = Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.SALES))
) -> User:
    return user


def get_accountant_or_admin(
    user: User = Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.ACCOUNTANT))
) -> User:
    return user


def get_any_authenticated(user: User = Depends(get_current_user)) -> User:
    """All roles including viewer can access."""
    return user
