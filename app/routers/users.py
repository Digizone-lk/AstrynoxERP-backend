from uuid import UUID
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import hash_password
from app.dependencies import get_current_user, get_super_admin
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate, UserOut
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
