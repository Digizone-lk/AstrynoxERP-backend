import hashlib
import io
import uuid as uuid_lib
from datetime import datetime, timezone
from typing import List
import cloudinary
import cloudinary.uploader
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Cookie, status
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import get_db
from app.core.security import verify_password, hash_password, decode_token
from app.dependencies import get_any_authenticated
from app.models.audit_log import AuditLog
from app.models.organization import Organization
from app.models.user import User, DEFAULT_NOTIFICATION_PREFS
from app.models.user_session import UserSession
from app.schemas.user import (
    UserProfileOut,
    ProfileUpdate,
    PasswordChange,
    NotificationPrefs,
    SessionOut,
    UserActivityOut,
)
from app.services.audit import log_action

router = APIRouter(prefix="/api/users/me", tags=["profile"])

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
MAX_AVATAR_SIZE = 2 * 1024 * 1024  # 2 MB

cloudinary.config(
    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
    api_key=settings.CLOUDINARY_API_KEY,
    api_secret=settings.CLOUDINARY_API_SECRET,
)


def _build_profile_out(user: User, db: Session) -> UserProfileOut:
    org = db.query(Organization).filter(Organization.id == user.org_id).first()
    data = UserProfileOut.model_validate(user).model_dump()
    data["org_currency"] = org.currency if org else "USD"
    return data


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

@router.get("/profile", response_model=UserProfileOut)
def get_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_any_authenticated),
):
    return _build_profile_out(current_user, db)


@router.patch("/profile", response_model=UserProfileOut)
def update_profile(
    payload: ProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_any_authenticated),
):
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(current_user, field, value)

    db.commit()
    db.refresh(current_user)
    log_action(db, current_user, "UPDATE", "user_profile", str(current_user.id))
    return _build_profile_out(current_user, db)


# ---------------------------------------------------------------------------
# Password
# ---------------------------------------------------------------------------

@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: PasswordChange,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_any_authenticated),
):
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    if verify_password(payload.new_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="New password must be different from current password")

    current_user.hashed_password = hash_password(payload.new_password)
    db.commit()
    log_action(db, current_user, "UPDATE", "user_password", str(current_user.id))


# ---------------------------------------------------------------------------
# Avatar
# ---------------------------------------------------------------------------

@router.post("/avatar", response_model=UserProfileOut)
def upload_avatar(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_any_authenticated),
):
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Only JPEG, PNG, GIF, or WebP images are allowed")

    content = file.file.read()
    if len(content) > MAX_AVATAR_SIZE:
        raise HTTPException(status_code=400, detail="Avatar must be smaller than 2 MB")

    try:
        result = cloudinary.uploader.upload(
            io.BytesIO(content),
            public_id=f"avatars/{current_user.id}",
            overwrite=True,
            resource_type="image",
            transformation={"width": 256, "height": 256, "crop": "fill", "gravity": "face"},
        )
        avatar_url = result["secure_url"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Avatar upload failed: {str(e)}")

    current_user.avatar_url = avatar_url
    db.commit()
    db.refresh(current_user)
    log_action(db, current_user, "UPDATE", "user_avatar", str(current_user.id))
    return _build_profile_out(current_user, db)


@router.delete("/avatar", response_model=UserProfileOut)
def delete_avatar(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_any_authenticated),
):
    if current_user.avatar_url:
        try:
            cloudinary.uploader.destroy(f"avatars/{current_user.id}", resource_type="image")
        except Exception:
            pass  # Don't fail if Cloudinary delete errors — DB cleanup still proceeds

        current_user.avatar_url = None
        db.commit()
        db.refresh(current_user)
        log_action(db, current_user, "UPDATE", "user_avatar", str(current_user.id))

    return _build_profile_out(current_user, db)


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

@router.get("/sessions", response_model=List[SessionOut])
def list_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_any_authenticated),
    access_token: str = Cookie(None),
):
    sessions = db.query(UserSession).filter(
        UserSession.user_id == current_user.id,
        UserSession.is_active == True,
        UserSession.expires_at > datetime.now(timezone.utc),
    ).order_by(UserSession.last_active_at.desc()).all()

    # Determine current session by matching the access token's associated session
    # We identify current session by ip + device and most recent last_active_at
    current_session_id = None
    if access_token:
        payload = decode_token(access_token)
        if payload:
            # Best effort: mark most-recently-active session as current
            if sessions:
                current_session_id = sessions[0].id

    result = []
    for s in sessions:
        out = SessionOut.model_validate(s).model_dump()
        out["is_current"] = (s.id == current_session_id)
        result.append(out)
    return result


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_session(
    session_id: uuid_lib.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_any_authenticated),
):
    session = db.query(UserSession).filter(
        UserSession.id == session_id,
        UserSession.user_id == current_user.id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session.is_active = False
    db.commit()
    log_action(db, current_user, "DELETE", "user_session", str(session_id))


@router.delete("/sessions", status_code=status.HTTP_204_NO_CONTENT)
def revoke_all_other_sessions(
    access_token: str = Cookie(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_any_authenticated),
):
    # Revoke all active sessions except the most recent one (current)
    sessions = db.query(UserSession).filter(
        UserSession.user_id == current_user.id,
        UserSession.is_active == True,
    ).order_by(UserSession.last_active_at.desc()).all()

    # Keep the first (most recent) as current, revoke the rest
    for s in sessions[1:]:
        s.is_active = False

    db.commit()
    log_action(db, current_user, "DELETE", "user_sessions_bulk", str(current_user.id))


# ---------------------------------------------------------------------------
# Notification Preferences
# ---------------------------------------------------------------------------

@router.get("/notifications", response_model=NotificationPrefs)
def get_notifications(
    current_user: User = Depends(get_any_authenticated),
):
    prefs = current_user.notification_prefs or DEFAULT_NOTIFICATION_PREFS
    return NotificationPrefs(**{**DEFAULT_NOTIFICATION_PREFS, **prefs})


@router.patch("/notifications", response_model=NotificationPrefs)
def update_notifications(
    payload: NotificationPrefs,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_any_authenticated),
):
    existing = current_user.notification_prefs or {}
    updated = {**DEFAULT_NOTIFICATION_PREFS, **existing, **payload.model_dump()}
    current_user.notification_prefs = updated
    db.commit()
    return NotificationPrefs(**updated)


# ---------------------------------------------------------------------------
# Activity Log (self-view)
# ---------------------------------------------------------------------------

@router.get("/activity", response_model=List[UserActivityOut])
def get_my_activity(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_any_authenticated),
):
    if limit > 100:
        limit = 100

    logs = (
        db.query(AuditLog)
        .filter(
            AuditLog.user_id == current_user.id,
            AuditLog.org_id == current_user.org_id,
        )
        .order_by(AuditLog.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return logs
