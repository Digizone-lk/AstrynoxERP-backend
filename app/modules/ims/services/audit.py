from typing import Optional, Any
from sqlalchemy.orm import Session
from app.modules.ims.models.audit_log import AuditLog
from app.modules.ims.models.user import User


def log_action(
    db: Session,
    user: User,
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    extra_data: Optional[Any] = None,
    ip_address: Optional[str] = None,
):
    """Write an audit log entry. Call after committing the main transaction."""
    entry = AuditLog(
        org_id=user.org_id,
        user_id=user.id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        extra_data=extra_data,
        ip_address=ip_address,
    )
    db.add(entry)
    db.commit()
