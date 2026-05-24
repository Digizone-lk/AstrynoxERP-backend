import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request, status, Header
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, decode_token, hash_password
from app.modules.ims.models.audit_log import AuditLog
from app.modules.ims.models.organization import Organization
from app.modules.ims.models.organization_invite import OrganizationInvite
from app.modules.ims.models.user import User, UserRole
from app.modules.ims.schemas.auth import ProductAdminLoginRequest, ProductAdminTokenResponse
from app.modules.ims.schemas.organization import (
    InviteValidateOut,
    InviteValidateRequest,
    PaidPlanUpdate,
    ProductAdminInviteCreate,
    ProductAdminInviteOut,
    ProductAdminOrgOut,
)
from app.modules.ims.services.email import send_organization_invite_email

router = APIRouter(prefix="/api/product-admin", tags=["product-admin"])


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


def get_product_admin(authorization: str = Header("")) -> str:
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


@router.post("/login", response_model=ProductAdminTokenResponse)
def product_admin_login(payload: ProductAdminLoginRequest):
    if payload.email != settings.PRODUCT_ADMIN_EMAIL or payload.password != settings.PRODUCT_ADMIN_PASSWORD:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token(
        {"sub": "product_admin", "email": settings.PRODUCT_ADMIN_EMAIL},
        expires_delta=timedelta(hours=8),
    )
    return ProductAdminTokenResponse(access_token=token)


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


@router.post("/organizations/{org_id}/activate-paid", response_model=ProductAdminOrgOut)
def activate_paid_plan(
    org_id: UUID,
    payload: PaidPlanUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin_email: str = Depends(get_product_admin),
):
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

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
