"""Shared audit log service, used across modules (ims, platform, hrms).

Convention (see CLAUDE.md): call log_action() after the main transaction has
already committed, as the last step — never before. A failed main action should
never produce an audit row; only a successful one does.
"""
import uuid
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.modules.platform.db import set_tenant_context
from app.modules.platform.models.audit_log import PlatformAuditLog, AuditActorType


def log_action(
    db: Session,
    org_id: uuid.UUID,
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    actor_type: str = AuditActorType.USER,
    actor_id: Optional[uuid.UUID] = None,
    actor_label: Optional[str] = None,
    before_data: Optional[Any] = None,
    after_data: Optional[Any] = None,
    extra_data: Optional[Any] = None,
    ip_address: Optional[str] = None,
) -> PlatformAuditLog:
    """Write one audit entry and commit it as its own transaction.

    Sets the RLS tenant context itself (rather than trusting the caller already
    did) so this is safe to call from any module's session without coordination.
    """
    set_tenant_context(db, org_id)
    entry = PlatformAuditLog(
        org_id=org_id,
        actor_type=actor_type,
        actor_id=actor_id,
        actor_label=actor_label,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        before_data=before_data,
        after_data=after_data,
        extra_data=extra_data,
        ip_address=ip_address,
    )
    db.add(entry)
    db.commit()
    return entry
