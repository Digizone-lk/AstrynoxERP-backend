import re
import hashlib
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, Response, Cookie, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import verify_password, hash_password, create_access_token, create_refresh_token, decode_token
from app.core.config import settings
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.models.user_session import UserSession
from app.schemas.auth import LoginRequest, TokenResponse, RegisterOrgRequest
from app.schemas.user import UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _set_tokens(response: Response, user: User, db: Session, request: Request) -> TokenResponse:
    data = {"sub": str(user.id), "org_id": str(user.org_id), "role": user.role.value}
    access_token = create_access_token(data)
    refresh_token = create_refresh_token(data)

    token_hash = _hash_token(refresh_token)
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    device_info = request.headers.get("user-agent", "")[:500] or None
    ip_address = request.client.host if request.client else None

    session = UserSession(
        user_id=user.id,
        org_id=user.org_id,
        refresh_token_hash=token_hash,
        device_info=device_info,
        ip_address=ip_address,
        expires_at=expires_at,
    )
    db.add(session)
    db.commit()

    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=settings.ENVIRONMENT == "production",
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=settings.ENVIRONMENT == "production",
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
    )
    return TokenResponse(access_token=access_token)


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register_organization(
    payload: RegisterOrgRequest,
    response: Response,
    request: Request,
    db: Session = Depends(get_db),
):
    if not re.match(r"^[a-z0-9-]+$", payload.org_slug):
        raise HTTPException(status_code=400, detail="Slug must be lowercase alphanumeric with hyphens only")

    if db.query(Organization).filter(Organization.slug == payload.org_slug).first():
        raise HTTPException(status_code=409, detail="Organization slug already taken")

    org = Organization(name=payload.org_name, slug=payload.org_slug, currency=payload.currency)
    db.add(org)
    db.flush()

    if db.query(User).filter(User.email == payload.email, User.org_id == org.id).first():
        raise HTTPException(status_code=409, detail="Email already registered")

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

    _set_tokens(response, user, db, request)
    return user


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    response: Response,
    request: Request,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == payload.email, User.is_active == True).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    return _set_tokens(response, user, db, request)


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    response: Response,
    request: Request,
    refresh_token: str = Cookie(None),
    db: Session = Depends(get_db),
):
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token")

    payload = decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    token_hash = _hash_token(refresh_token)
    session = db.query(UserSession).filter(
        UserSession.refresh_token_hash == token_hash,
        UserSession.is_active == True,
    ).first()
    if not session or session.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired or revoked")

    user = db.query(User).filter(User.id == payload.get("sub"), User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    # Revoke old session before issuing new one
    session.is_active = False
    db.commit()

    return _set_tokens(response, user, db, request)


@router.post("/logout")
def logout(
    response: Response,
    refresh_token: str = Cookie(None),
    db: Session = Depends(get_db),
):
    if refresh_token:
        token_hash = _hash_token(refresh_token)
        session = db.query(UserSession).filter(
            UserSession.refresh_token_hash == token_hash,
        ).first()
        if session:
            session.is_active = False
            db.commit()

    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return {"message": "Logged out"}


@router.get("/me", response_model=UserOut)
def me(db: Session = Depends(get_db), access_token: str = Cookie(None)):
    if not access_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_token(access_token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.query(User).filter(User.id == payload.get("sub"), User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    org = db.query(Organization).filter(Organization.id == user.org_id).first()
    user_dict = UserOut.model_validate(user).model_dump()
    user_dict["org_currency"] = org.currency if org else "USD"
    return user_dict
