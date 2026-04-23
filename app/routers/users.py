from uuid import UUID
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import hash_password
from app.dependencies import get_current_user, get_super_admin
from app.models.audit_log import AuditLog
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate, UserOut, AdminPasswordReset, UserActivityOut, UserModulesUpdate
from app.services.audit import log_action

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/", response_model=List[UserOut])
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_super_admin),
):
    return db.query(User).filter(User.org_id == current_user.org_id).all()


@router.post("/", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_super_admin),
):
    if db.query(User).filter(User.email == payload.email, User.org_id == current_user.org_id).first():
        raise HTTPException(status_code=409, detail="Email already exists in this organization")

    user = User(
        org_id=current_user.org_id,
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    log_action(db, current_user, "CREATE", "user", str(user.id))
    return user


@router.get("/{user_id}", response_model=UserOut)
def get_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_super_admin),
):
    user = db.query(User).filter(User.id == user_id, User.org_id == current_user.org_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: UUID,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_super_admin),
):
    user = db.query(User).filter(User.id == user_id, User.org_id == current_user.org_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, field, value)

    db.commit()
    db.refresh(user)
    log_action(db, current_user, "UPDATE", "user", str(user_id))
    return user


@router.post("/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def admin_reset_password(
    user_id: UUID,
    payload: AdminPasswordReset,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_super_admin),
):
    user = db.query(User).filter(User.id == user_id, User.org_id == current_user.org_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.hashed_password = hash_password(payload.new_password)
    db.commit()
    log_action(
        db, current_user, "UPDATE", "user_password", str(user_id),
        extra_data={"reset_by": str(current_user.id)},
    )


@router.post("/{user_id}/deactivate", response_model=UserOut)
def deactivate_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_super_admin),
):
    user = db.query(User).filter(User.id == user_id, User.org_id == current_user.org_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate your own account")

    user.is_active = False
    db.commit()
    db.refresh(user)
    log_action(db, current_user, "UPDATE", "user", str(user_id), extra_data={"action": "deactivate"})
    return user


@router.post("/{user_id}/reactivate", response_model=UserOut)
def reactivate_user(
    user_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_super_admin),
):
    user = db.query(User).filter(User.id == user_id, User.org_id == current_user.org_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.is_active:
        raise HTTPException(status_code=400, detail="User is already active")

    user.is_active = True
    db.commit()
    db.refresh(user)
    log_action(db, current_user, "UPDATE", "user", str(user_id), extra_data={"action": "reactivate"})
    return user


@router.patch("/{user_id}/modules", response_model=UserOut)
def update_user_modules(
    user_id: UUID,
    payload: UserModulesUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_super_admin),
):
    """Set or clear the module access list for a user. Pass null to restore full access."""
    user = db.query(User).filter(User.id == user_id, User.org_id == current_user.org_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role == user.role.SUPER_ADMIN:
        raise HTTPException(status_code=400, detail="Cannot restrict module access for super admins")

    user.allowed_modules = payload.allowed_modules
    db.commit()
    db.refresh(user)
    log_action(
        db, current_user, "UPDATE", "user_modules", str(user_id),
        extra_data={"allowed_modules": payload.allowed_modules},
    )
    return user


@router.get("/{user_id}/activity", response_model=List[UserActivityOut])
def get_user_activity(
    user_id: UUID,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_super_admin),
):
    user = db.query(User).filter(User.id == user_id, User.org_id == current_user.org_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if limit > 100:
        limit = 100

    logs = (
        db.query(AuditLog)
        .filter(AuditLog.user_id == user_id, AuditLog.org_id == current_user.org_id)
        .order_by(AuditLog.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return logs
