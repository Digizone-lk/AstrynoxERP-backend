import re
from uuid import UUID as PyUUID
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.core.security import verify_password, hash_password, decode_token
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.schemas.auth import RegisterOrgRequest
from app.schemas.user import UserOut


def register_org(db: Session, payload: RegisterOrgRequest) -> User:
    """Create a new organisation and its super-admin user. Returns the new User."""
    if not re.match(r"^[a-z0-9-]+$", payload.org_slug):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Slug must be lowercase alphanumeric with hyphens only",
        )

    if db.query(Organization).filter(Organization.slug == payload.org_slug).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Organization slug already taken",
        )

    org = Organization(name=payload.org_name, slug=payload.org_slug, currency=payload.currency)
    db.add(org)
    db.flush()

    user = User(
        org_id=org.id,
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role=UserRole.SUPER_ADMIN,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> User:
    """Validate credentials and org status. Returns the authenticated User."""
    user = db.query(User).filter(User.email == email, User.is_active == True).first()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    org = db.query(Organization).filter(
        Organization.id == user.org_id, Organization.is_active == True
    ).first()
    if not org:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization is inactive",
        )

    return user


def get_user_from_refresh_token(db: Session, refresh_token: str | None) -> User:
    """Decode a refresh token and return the corresponding active User."""
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No refresh token",
        )

    payload = decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    user = db.query(User).filter(
        User.id == PyUUID(payload["sub"]), User.is_active == True
    ).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return user


def get_user_from_access_token(db: Session, access_token: str | None) -> dict:
    """Decode an access token, fetch the user, and return a UserOut dict with org_currency."""
    if not access_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    payload = decode_token(access_token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user = db.query(User).filter(
        User.id == PyUUID(payload["sub"]), User.is_active == True
    ).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    org = db.query(Organization).filter(Organization.id == user.org_id).first()
    user_dict = UserOut.model_validate(user).model_dump()
    user_dict["org_currency"] = org.currency if org else "USD"
    return user_dict
