from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.dependencies import get_any_authenticated, get_super_admin
from app.modules.ims.models.organization import Organization
from app.modules.ims.models.user import User
from app.modules.ims.models.organization_invite import OrganizationInvite
from app.modules.ims.schemas.organization import OrgOut, OrgUpdate
from app.modules.ims.services.audit import log_action

router = APIRouter(prefix="/api/org", tags=["organization"])


@router.get("", response_model=OrgOut)
def get_org(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_any_authenticated),
):
    org = db.query(Organization).filter(Organization.id == current_user.org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


@router.patch("", response_model=OrgOut)
def update_org(
    payload: OrgUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_super_admin),
):
    org = db.query(Organization).filter(Organization.id == current_user.org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    updated_fields = payload.model_dump(exclude_unset=True)
    for field, value in updated_fields.items():
        setattr(org, field, value)

    db.commit()
    db.refresh(org)
    log_action(
        db, current_user, "UPDATE", "organization", str(org.id),
        extra_data=updated_fields,
    )
    return org


@router.patch("/onboarding", response_model=OrgOut)
def complete_onboarding_org_details(
    payload: OrgUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_super_admin),
):
    if current_user.must_change_password:
        raise HTTPException(status_code=400, detail="Password must be changed before completing onboarding")
    if not current_user.email_verified:
        raise HTTPException(status_code=400, detail="Email must be verified before completing onboarding")

    org = db.query(Organization).filter(Organization.id == current_user.org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    updated_fields = payload.model_dump(exclude_unset=True)
    for field, value in updated_fields.items():
        setattr(org, field, value)
    org.onboarding_status = "completed"

    db.query(OrganizationInvite).filter(
        OrganizationInvite.org_id == org.id,
        OrganizationInvite.used_at == None,
        OrganizationInvite.invalidated == False,
    ).update({"used_at": datetime.now(timezone.utc)})

    db.commit()
    db.refresh(org)
    log_action(
        db, current_user, "onboarding_details_completed", "organization", str(org.id),
        extra_data=updated_fields,
    )
    return org
