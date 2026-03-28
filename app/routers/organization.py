from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.dependencies import get_any_authenticated, get_super_admin
from app.models.organization import Organization
from app.models.user import User
from app.schemas.organization import OrgOut, OrgUpdate
from app.services.audit import log_action

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
