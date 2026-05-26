import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response, Cookie, status, Header
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, create_refresh_token_with_expiry, decode_token, hash_password
from app.modules.ims.models.audit_log import AuditLog
from app.modules.ims.models.organization import Organization
from app.modules.ims.models.organization_invite import OrganizationInvite
from app.modules.ims.models.product_admin_otp import ProductAdminOtp
from app.modules.ims.models.product_admin_session import ProductAdminSession
from app.modules.ims.models.user import User, UserRole
from app.modules.ims.models.user_session import UserSession
from app.modules.ims.schemas.audit_log import AuditLogOut
from app.modules.ims.schemas.auth import (
    ProductAdminLoginRequest,
    ProductAdminLoginResponse,
    ProductAdminOtpVerifyRequest,
    ProductAdminTokenResponse,
)
from app.modules.ims.schemas.organization import (
    InviteValidateOut,
    InviteValidateRequest,
    PaidPlanUpdate,
    ProductAdminInviteCreate,
    ProductAdminInviteOut,
    ProductAdminOrgOut,
    ProductAdminOrgStatusUpdate,
    ProductAdminSubscriptionUpdate,
    ProductAdminSuperAdminTransfer,
    ProductAdminUserUpdate,
)
from app.modules.ims.schemas.user import UserOut
from app.modules.ims.services.email import send_organization_invite_email, send_product_admin_otp_email

router = APIRouter(prefix="/api/product-admin", tags=["product-admin"])

PRODUCT_ADMIN_ACCESS_TOKEN_MINUTES = 30
PRODUCT_ADMIN_REFRESH_TOKEN_HOURS = 3
PRODUCT_ADMIN_OTP_EXPIRE_MINUTES = 10


def _hash_token(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _temporary_password() -> str:
    return secrets.token_urlsafe(24)[:32]


def _fingerprint(request: Request) -> str:
    user_agent = request.headers.get("user-agent", "")
    ip_address = request.client.host if request.client else ""
    return _hash_token(f"{user_agent}|{ip_address}")


def _invite_link(token: str) -> str:
    return f"{settings.FRONTEND_URL}/org/invite/accept?token={token}"


def _is_expired(value) -> bool:
    now = datetime.now(timezone.utc)
    if value.tzinfo is None:
        now = now.replace(tzinfo=None)
    return value < now


def _product_admin_token_data() -> dict:
    return {"sub": "product_admin", "email": settings.PRODUCT_ADMIN_EMAIL}


def _set_product_admin_tokens(response: Response, db: Session, request: Request) -> ProductAdminTokenResponse:
    data = _product_admin_token_data()
    access_token = create_access_token(data, expires_delta=timedelta(minutes=PRODUCT_ADMIN_ACCESS_TOKEN_MINUTES))
    refresh_token = create_refresh_token_with_expiry(data, timedelta(hours=PRODUCT_ADMIN_REFRESH_TOKEN_HOURS))
    db.add(ProductAdminSession(
        email=settings.PRODUCT_ADMIN_EMAIL,
        refresh_token_hash=_hash_token(refresh_token),
        device_info=(request.headers.get("user-agent", "")[:500] or None),
        ip_address=request.client.host if request.client else None,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=PRODUCT_ADMIN_REFRESH_TOKEN_HOURS),
    ))
    db.commit()
    response.set_cookie(
        key="product_admin_refresh_token",
        value=refresh_token,
        httponly=True,
        secure=settings.ENVIRONMENT == "production",
        samesite="lax",
        max_age=PRODUCT_ADMIN_REFRESH_TOKEN_HOURS * 3600,
    )
    return ProductAdminTokenResponse(access_token=access_token, refresh_token=refresh_token)


def get_product_admin(
    authorization: str = Header(""),
) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = decode_token(authorization[7:])
    if not payload or payload.get("type") != "access" or payload.get("sub") != "product_admin":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    if payload.get("email") != settings.PRODUCT_ADMIN_EMAIL:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return settings.PRODUCT_ADMIN_EMAIL


def _write_org_audit(
    db: Session,
    org_id,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    extra_data: dict | None = None,
    ip_address: str | None = None,
) -> None:
    db.add(AuditLog(
        org_id=org_id,
        user_id=None,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        extra_data=extra_data,
        ip_address=ip_address,
    ))
    db.commit()


def _get_org_or_404(db: Session, org_id: UUID) -> Organization:
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


def _get_org_user_or_404(db: Session, org_id: UUID, user_id: UUID) -> User:
    user = db.query(User).filter(User.id == user_id, User.org_id == org_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.post("/login", response_model=ProductAdminLoginResponse)
def product_admin_login(payload: ProductAdminLoginRequest, db: Session = Depends(get_db)):
    if payload.email != settings.PRODUCT_ADMIN_EMAIL or payload.password != settings.PRODUCT_ADMIN_PASSWORD:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    db.query(ProductAdminOtp).filter(
        ProductAdminOtp.email == settings.PRODUCT_ADMIN_EMAIL,
        ProductAdminOtp.used == False,
    ).update({"used": True})

    otp = f"{secrets.randbelow(1000000):06d}"
    challenge_token = secrets.token_urlsafe(32)
    db.add(ProductAdminOtp(
        email=settings.PRODUCT_ADMIN_EMAIL,
        challenge_hash=_hash_token(challenge_token),
        otp_hash=_hash_token(otp),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=PRODUCT_ADMIN_OTP_EXPIRE_MINUTES),
    ))
    db.commit()

    if not send_product_admin_otp_email(settings.PRODUCT_ADMIN_EMAIL, otp):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not send admin OTP email. Please try again shortly.",
        )
    return ProductAdminLoginResponse(challenge_token=challenge_token)


@router.post("/verify-otp", response_model=ProductAdminTokenResponse)
def product_admin_verify_otp(
    payload: ProductAdminOtpVerifyRequest,
    response: Response,
    request: Request,
    db: Session = Depends(get_db),
):
    record = db.query(ProductAdminOtp).filter(
        ProductAdminOtp.email == settings.PRODUCT_ADMIN_EMAIL,
        ProductAdminOtp.challenge_hash == _hash_token(payload.challenge_token),
        ProductAdminOtp.otp_hash == _hash_token(payload.otp),
        ProductAdminOtp.used == False,
    ).first()
    if not record or _is_expired(record.expires_at):
        raise HTTPException(status_code=400, detail="Invalid or expired OTP.")

    record.used = True
    db.commit()
    return _set_product_admin_tokens(response, db, request)


@router.post("/refresh", response_model=ProductAdminTokenResponse)
def product_admin_refresh(
    response: Response,
    request: Request,
    product_admin_refresh_token: Optional[str] = Cookie(None),
    db: Session = Depends(get_db),
):
    if not product_admin_refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token")

    payload = decode_token(product_admin_refresh_token)
    if (
        not payload
        or payload.get("type") != "refresh"
        or payload.get("sub") != "product_admin"
        or payload.get("email") != settings.PRODUCT_ADMIN_EMAIL
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    session = db.query(ProductAdminSession).filter(
        ProductAdminSession.refresh_token_hash == _hash_token(product_admin_refresh_token),
        ProductAdminSession.is_active == True,
    ).first()
    if not session or _is_expired(session.expires_at):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired or revoked")

    session.is_active = False
    db.commit()
    return _set_product_admin_tokens(response, db, request)


@router.post("/logout")
def product_admin_logout(
    response: Response,
    product_admin_refresh_token: Optional[str] = Cookie(None),
    db: Session = Depends(get_db),
):
    if product_admin_refresh_token:
        session = db.query(ProductAdminSession).filter(
            ProductAdminSession.refresh_token_hash == _hash_token(product_admin_refresh_token),
        ).first()
        if session:
            session.is_active = False
            db.commit()
    response.delete_cookie("product_admin_refresh_token")
    return {"message": "Logged out"}


@router.post("/organizations/invite", response_model=ProductAdminInviteOut, status_code=status.HTTP_201_CREATED)
def create_organization_invite(
    payload: ProductAdminInviteCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin_email: str = Depends(get_product_admin),
):
    if db.query(Organization).filter(Organization.slug == payload.username).first():
        raise HTTPException(status_code=409, detail="Organization username already exists")
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=409, detail="Login username already exists")

    now = datetime.now(timezone.utc)
    temp_password = _temporary_password()
    raw_token = secrets.token_urlsafe(32)

    org = Organization(
        name=payload.username,
        slug=payload.username,
        email=payload.email,
        subscription_status="trial",
        trial_start_date=now,
        trial_end_date=now + timedelta(days=14),
        onboarding_status="invited",
    )
    db.add(org)
    db.flush()

    user = User(
        org_id=org.id,
        email=payload.email,
        username=payload.username,
        full_name=payload.username,
        hashed_password=hash_password(temp_password),
        role=UserRole.SUPER_ADMIN,
        must_change_password=True,
        email_verified=False,
    )
    db.add(user)
    db.flush()

    invite = OrganizationInvite(
        org_id=org.id,
        user_id=user.id,
        email=payload.email,
        username=payload.username,
        token_hash=_hash_token(raw_token),
        expires_at=now + timedelta(hours=24),
        created_by=admin_email,
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)

    send_organization_invite_email(payload.email, payload.username, temp_password, _invite_link(raw_token))
    _write_org_audit(
        db,
        org.id,
        "organization_invite_created",
        "organization_invite",
        str(invite.id),
        {"email": payload.email, "username": payload.username},
        request.client.host if request.client else None,
    )
    return invite


@router.post("/organizations/{org_id}/resend-invite", response_model=ProductAdminInviteOut)
def resend_organization_invite(
    org_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    admin_email: str = Depends(get_product_admin),
):
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    user = db.query(User).filter(User.org_id == org.id, User.role == UserRole.SUPER_ADMIN).first()
    if not user:
        raise HTTPException(status_code=404, detail="Organization admin user not found")

    db.query(OrganizationInvite).filter(
        OrganizationInvite.org_id == org.id,
        OrganizationInvite.used_at == None,
        OrganizationInvite.invalidated == False,
    ).update({"invalidated": True})

    now = datetime.now(timezone.utc)
    temp_password = _temporary_password()
    raw_token = secrets.token_urlsafe(32)
    if org.onboarding_status != "completed":
        user.hashed_password = hash_password(temp_password)
        user.must_change_password = True
        user.email_verified = False

    invite = OrganizationInvite(
        org_id=org.id,
        user_id=user.id,
        email=user.email,
        username=user.username or org.slug,
        token_hash=_hash_token(raw_token),
        expires_at=now + timedelta(hours=24),
        created_by=admin_email,
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)

    send_organization_invite_email(user.email, invite.username, temp_password, _invite_link(raw_token))
    _write_org_audit(
        db,
        org.id,
        "organization_invite_resent",
        "organization_invite",
        str(invite.id),
        {"email": user.email, "username": invite.username},
        request.client.host if request.client else None,
    )
    return invite


@router.post("/invites/validate", response_model=InviteValidateOut)
def validate_invite(payload: InviteValidateRequest, request: Request, db: Session = Depends(get_db)):
    invite = db.query(OrganizationInvite).filter(
        OrganizationInvite.token_hash == _hash_token(payload.token),
        OrganizationInvite.invalidated == False,
    ).first()
    if not invite:
        raise HTTPException(status_code=400, detail="Invalid or expired invite")
    now = datetime.now(timezone.utc)
    expires = invite.expires_at
    if expires.tzinfo is None:
        now = now.replace(tzinfo=None)
    if invite.used_at is not None or expires < now:
        raise HTTPException(status_code=400, detail="Invalid or expired invite")

    fingerprint = _fingerprint(request)
    if invite.opened_at and invite.device_fingerprint != fingerprint:
        raise HTTPException(status_code=400, detail="Invite is locked to another device")
    if not invite.opened_at:
        invite.opened_at = datetime.now(timezone.utc)
        invite.device_fingerprint = fingerprint
        db.commit()
        _write_org_audit(
            db,
            invite.org_id,
            "organization_invite_opened",
            "organization_invite",
            str(invite.id),
            ip_address=request.client.host if request.client else None,
        )

    return InviteValidateOut(email=invite.email, username=invite.username, expires_at=invite.expires_at)


@router.get("/organizations", response_model=list[ProductAdminOrgOut])
def list_organizations(
    db: Session = Depends(get_db),
    admin_email: str = Depends(get_product_admin),
):
    return db.query(Organization).order_by(Organization.created_at.desc()).all()


@router.get("/organizations/{org_id}", response_model=ProductAdminOrgOut)
def get_organization(
    org_id: UUID,
    db: Session = Depends(get_db),
    admin_email: str = Depends(get_product_admin),
):
    return _get_org_or_404(db, org_id)


@router.patch("/organizations/{org_id}/subscription", response_model=ProductAdminOrgOut)
def update_organization_subscription(
    org_id: UUID,
    payload: ProductAdminSubscriptionUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin_email: str = Depends(get_product_admin),
):
    org = _get_org_or_404(db, org_id)
    old = {"subscription_status": org.subscription_status, "plan": org.plan}

    if payload.version == "trial":
        org.subscription_status = "trial"
        org.plan = None
        if not org.trial_start_date:
            org.trial_start_date = datetime.now(timezone.utc)
        if not org.trial_end_date:
            org.trial_end_date = datetime.now(timezone.utc) + timedelta(days=14)
    else:
        org.subscription_status = "paid"
        org.plan = payload.version
        org.paid_activated_at = datetime.now(timezone.utc)
        org.paid_activated_by = admin_email

    db.commit()
    db.refresh(org)
    _write_org_audit(
        db,
        org.id,
        "organization_subscription_updated",
        "organization",
        str(org.id),
        {"old": old, "new": {"subscription_status": org.subscription_status, "plan": org.plan}},
        request.client.host if request.client else None,
    )
    return org


@router.patch("/organizations/{org_id}/status", response_model=ProductAdminOrgOut)
def update_organization_status(
    org_id: UUID,
    payload: ProductAdminOrgStatusUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin_email: str = Depends(get_product_admin),
):
    org = _get_org_or_404(db, org_id)
    old_status = org.is_active
    org.is_active = payload.is_active

    if not payload.is_active:
        db.query(UserSession).filter(
            UserSession.org_id == org.id,
            UserSession.is_active == True,
        ).update({"is_active": False})

    db.commit()
    db.refresh(org)
    _write_org_audit(
        db,
        org.id,
        "organization_status_updated",
        "organization",
        str(org.id),
        {"old": old_status, "new": org.is_active},
        request.client.host if request.client else None,
    )
    return org


@router.get("/organizations/{org_id}/users", response_model=list[UserOut])
def list_organization_users(
    org_id: UUID,
    db: Session = Depends(get_db),
    admin_email: str = Depends(get_product_admin),
):
    _get_org_or_404(db, org_id)
    return db.query(User).filter(User.org_id == org_id).order_by(User.created_at.asc()).all()


@router.patch("/organizations/{org_id}/users/{user_id}", response_model=UserOut)
def update_organization_user(
    org_id: UUID,
    user_id: UUID,
    payload: ProductAdminUserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin_email: str = Depends(get_product_admin),
):
    _get_org_or_404(db, org_id)
    user = _get_org_user_or_404(db, org_id, user_id)
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        return user

    old = {"role": user.role.value, "is_active": user.is_active}
    if payload.role is not None:
        user.role = UserRole(payload.role)
    if payload.is_active is not None:
        user.is_active = payload.is_active
        if not payload.is_active:
            db.query(UserSession).filter(
                UserSession.user_id == user.id,
                UserSession.is_active == True,
            ).update({"is_active": False})

    db.commit()
    db.refresh(user)
    _write_org_audit(
        db,
        org_id,
        "organization_user_updated",
        "user",
        str(user.id),
        {"old": old, "new": {"role": user.role.value, "is_active": user.is_active}},
        request.client.host if request.client else None,
    )
    return user


@router.post("/organizations/{org_id}/users/{user_id}/activate", response_model=UserOut)
def activate_organization_user(
    org_id: UUID,
    user_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    admin_email: str = Depends(get_product_admin),
):
    return update_organization_user(
        org_id,
        user_id,
        ProductAdminUserUpdate(is_active=True),
        request,
        db,
        admin_email,
    )


@router.post("/organizations/{org_id}/users/{user_id}/deactivate", response_model=UserOut)
def deactivate_organization_user(
    org_id: UUID,
    user_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    admin_email: str = Depends(get_product_admin),
):
    return update_organization_user(
        org_id,
        user_id,
        ProductAdminUserUpdate(is_active=False),
        request,
        db,
        admin_email,
    )


@router.post("/organizations/{org_id}/super-admin", response_model=UserOut)
def transfer_organization_super_admin(
    org_id: UUID,
    payload: ProductAdminSuperAdminTransfer,
    request: Request,
    db: Session = Depends(get_db),
    admin_email: str = Depends(get_product_admin),
):
    _get_org_or_404(db, org_id)
    target = _get_org_user_or_404(db, org_id, payload.user_id)
    if not target.is_active:
        raise HTTPException(status_code=400, detail="Cannot make an inactive user the super admin")

    previous_super_admins = db.query(User).filter(
        User.org_id == org_id,
        User.role == UserRole.SUPER_ADMIN,
        User.id != target.id,
    ).all()
    previous_ids = [str(user.id) for user in previous_super_admins]
    for user in previous_super_admins:
        user.role = UserRole.ACCOUNTANT

    target.role = UserRole.SUPER_ADMIN
    db.commit()
    db.refresh(target)
    _write_org_audit(
        db,
        org_id,
        "organization_super_admin_transferred",
        "user",
        str(target.id),
        {"previous_super_admin_ids": previous_ids, "new_super_admin_id": str(target.id)},
        request.client.host if request.client else None,
    )
    return target


@router.get("/organizations/{org_id}/logs", response_model=list[AuditLogOut])
def list_organization_logs(
    org_id: UUID,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    admin_email: str = Depends(get_product_admin),
):
    _get_org_or_404(db, org_id)
    if limit > 200:
        limit = 200
    return (
        db.query(AuditLog)
        .filter(AuditLog.org_id == org_id)
        .order_by(AuditLog.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.post("/organizations/{org_id}/activate-paid", response_model=ProductAdminOrgOut)
def activate_paid_plan(
    org_id: UUID,
    payload: PaidPlanUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin_email: str = Depends(get_product_admin),
):
    org = _get_org_or_404(db, org_id)

    org.subscription_status = "paid"
    org.plan = payload.plan
    org.paid_activated_at = datetime.now(timezone.utc)
    org.paid_activated_by = admin_email
    db.commit()
    db.refresh(org)

    _write_org_audit(
        db,
        org.id,
        "paid_plan_activated",
        "organization",
        str(org.id),
        {"plan": payload.plan},
        request.client.host if request.client else None,
    )
    return org
