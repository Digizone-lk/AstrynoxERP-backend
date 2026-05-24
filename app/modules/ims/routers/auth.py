import re
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID as PyUUID
from fastapi import APIRouter, Depends, HTTPException, Request, Response, Cookie, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import verify_password, hash_password, create_access_token, create_refresh_token, decode_token
from app.core.config import settings
from app.modules.ims.models.organization import Organization
from app.modules.ims.models.user import User, UserRole
from app.modules.ims.models.user_session import UserSession
from app.modules.ims.models.password_reset_token import PasswordResetToken
from app.modules.ims.models.onboarding_otp import OnboardingOtp
from app.modules.ims.schemas.auth import LoginRequest, TokenResponse, RegisterOrgRequest, ForgotPasswordRequest, ResetPasswordRequest
from app.modules.ims.schemas.organization import OnboardingPasswordChange, OnboardingOtpVerify
from app.modules.ims.schemas.user import UserOut
from app.dependencies import get_current_user, enforce_organization_access
from app.modules.ims.services.email import send_password_reset_email, send_onboarding_otp_email
from app.modules.ims.services.audit import log_action

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _set_tokens(response: Response, user: User, db: Session, request: Request) -> TokenResponse:
    org = db.query(Organization).filter(Organization.id == user.org_id).first()
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
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        must_change_password=user.must_change_password,
        email_verified=user.email_verified,
        onboarding_status=org.onboarding_status if org else "completed",
        subscription_status=org.subscription_status if org else "trial",
        plan=org.plan if org else None,
        admin_email=settings.PRODUCT_ADMIN_EMAIL,
    )


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

    now = datetime.now(timezone.utc)
    org = Organization(
        name=payload.org_name,
        slug=payload.org_slug,
        currency=payload.currency,
        subscription_status="trial",
        trial_start_date=now,
        trial_end_date=now + timedelta(days=14),
        onboarding_status="completed",
    )
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
        email_verified=True,
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
    login_id = payload.email.strip()
    user = db.query(User).filter(
        ((User.email == login_id) | (User.username == login_id)),
        User.is_active == True,
    ).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    org = db.query(Organization).filter(Organization.id == user.org_id).first()
    if not org or not org.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization is inactive")
    if org.subscription_status == "trial" and org.trial_end_date:
        now = datetime.now(timezone.utc)
        trial_end = org.trial_end_date
        if trial_end.tzinfo is None:
            now = now.replace(tzinfo=None)
        if trial_end < now:
            org.subscription_status = "trial_expired"
            db.commit()

    return _set_tokens(response, user, db, request)


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    response: Response,
    request: Request,
    refresh_token: Optional[str] = Cookie(None),
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
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired or revoked")
    now = datetime.now(timezone.utc)
    expires = session.expires_at
    if expires.tzinfo is None:
        now = now.replace(tzinfo=None)
    if expires < now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired or revoked")

    try:
        user_id = PyUUID(payload.get("sub"))
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    enforce_organization_access(db, user, request)

    # Revoke old session before issuing new one
    session.is_active = False
    db.commit()

    return _set_tokens(response, user, db, request)


@router.post("/logout")
def logout(
    response: Response,
    refresh_token: Optional[str] = Cookie(None),
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
def me(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    org = db.query(Organization).filter(Organization.id == user.org_id).first()
    user_dict = UserOut.model_validate(user).model_dump()
    user_dict["org_currency"] = org.currency if org else "USD"
    user_dict["onboarding_status"] = org.onboarding_status if org else "completed"
    user_dict["subscription_status"] = org.subscription_status if org else "trial"
    user_dict["plan"] = org.plan if org else None
    user_dict["trial_end_date"] = org.trial_end_date if org else None
    user_dict["admin_email"] = settings.PRODUCT_ADMIN_EMAIL
    return user_dict


@router.post("/onboarding/change-password", status_code=status.HTTP_200_OK)
def onboarding_change_password(
    payload: OnboardingPasswordChange,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if len(payload.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")
    user.hashed_password = hash_password(payload.new_password)
    user.must_change_password = False
    db.query(UserSession).filter(UserSession.user_id == user.id, UserSession.is_active == True).update({"is_active": False})
    db.commit()
    log_action(db, user, "onboarding_password_changed", "user", str(user.id), ip_address=request.client.host if request.client else None)
    return {"message": "Password changed successfully. Please log in again to verify your email."}


@router.post("/onboarding/send-otp", status_code=status.HTTP_200_OK)
def send_onboarding_otp(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.must_change_password:
        raise HTTPException(status_code=400, detail="Password must be changed before OTP verification.")
    if user.email_verified:
        return {"message": "Email already verified."}

    db.query(OnboardingOtp).filter(OnboardingOtp.user_id == user.id, OnboardingOtp.used == False).update({"used": True})
    otp = f"{secrets.randbelow(1000000):06d}"
    record = OnboardingOtp(
        user_id=user.id,
        otp_hash=_hash_token(otp),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    db.add(record)
    db.commit()
    send_onboarding_otp_email(user.email, otp)
    return {"message": "OTP sent to registered email."}


@router.post("/onboarding/verify-otp", status_code=status.HTTP_200_OK)
def verify_onboarding_otp(
    payload: OnboardingOtpVerify,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    record = db.query(OnboardingOtp).filter(
        OnboardingOtp.user_id == user.id,
        OnboardingOtp.otp_hash == _hash_token(payload.otp),
        OnboardingOtp.used == False,
    ).first()
    if not record:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP.")
    now = datetime.now(timezone.utc)
    expires = record.expires_at
    if expires.tzinfo is None:
        now = now.replace(tzinfo=None)
    if expires < now:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP.")

    record.used = True
    user.email_verified = True
    db.commit()
    log_action(db, user, "onboarding_otp_verified", "user", str(user.id), ip_address=request.client.host if request.client else None)
    return {"message": "Email verified successfully."}


@router.post("/forgot-password", status_code=status.HTTP_200_OK)
def forgot_password(payload: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)):
    # Always return the same response to avoid leaking whether an email exists.
    generic_response = {"message": "If that email is registered you will receive a reset link shortly."}

    user = db.query(User).filter(User.email == payload.email, User.is_active == True).first()
    if not user:
        return generic_response

    # Rate limit: max 3 reset requests per user per 15 minutes.
    window_start = datetime.now(timezone.utc) - timedelta(minutes=15)
    recent_count = db.query(func.count(PasswordResetToken.id)).filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.created_at >= window_start,
    ).scalar()
    if recent_count >= 3:
        return generic_response  # silently drop — don't reveal the limit

    # Opportunistic cleanup: delete expired tokens for this user to keep the
    # table lean. Done before creating the new token.
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.expires_at < datetime.now(timezone.utc),
    ).delete()

    # Invalidate any existing unused tokens for this user
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.used == False,
    ).update({"used": True})

    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

    db.add(PasswordResetToken(user_id=user.id, token_hash=token_hash, expires_at=expires_at))
    db.commit()

    reset_link = f"{settings.FRONTEND_URL}/reset-password?token={raw_token}"
    send_password_reset_email(user.email, user.full_name, reset_link)

    return generic_response


@router.post("/reset-password", status_code=status.HTTP_200_OK)
def reset_password(payload: ResetPasswordRequest, request: Request, db: Session = Depends(get_db)):
    if len(payload.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")

    token_hash = hashlib.sha256(payload.token.encode()).hexdigest()
    record = db.query(PasswordResetToken).filter(
        PasswordResetToken.token_hash == token_hash,
        PasswordResetToken.used == False,
    ).first()

    if not record:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link.")

    now = datetime.now(timezone.utc)
    expires = record.expires_at
    if expires.tzinfo is None:
        now = now.replace(tzinfo=None)
    if expires < now:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link.")

    user = db.query(User).filter(User.id == record.user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link.")

    user.hashed_password = hash_password(payload.new_password)
    record.used = True

    # Revoke all active sessions so old devices must log in again
    db.query(UserSession).filter(
        UserSession.user_id == user.id,
        UserSession.is_active == True,
    ).update({"is_active": False})

    db.commit()

    # Audit log — password reset is a high-value security event
    log_action(
        db=db,
        user=user,
        action="password_reset",
        resource_type="user",
        resource_id=str(user.id),
        ip_address=request.client.host if request.client else None,
    )

    return {"message": "Password reset successfully. Please log in with your new password."}
