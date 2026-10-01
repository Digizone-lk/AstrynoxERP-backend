import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, JSON, Index
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class AuditActorType:
    """Free-text, not a DB enum — mirrors OrgUnitType's rationale (new actor kinds,
    e.g. a specific AI agent name, shouldn't need a migration)."""

    USER = "user"
    AI = "ai"
    SYSTEM = "system"


class PlatformAuditLog(Base):
    """Shared audit trail for every module (ims, platform, hrms), replacing the
    per-module log_action() pattern (see app/modules/ims/services/audit.py, which
    predates the platform module and stays as-is for BillFlow's own use).

    Named PlatformAuditLog, not AuditLog: ims already has an AuditLog class, and
    ims's Organization/User models reference it via the string form
    relationship("AuditLog", ...), which SQLAlchemy resolves by class name across
    its *entire* shared declarative registry — two classes named AuditLog makes
    that lookup ambiguous and breaks mapper configuration for Organization/User.

    actor_id is intentionally not a foreign key to `users` — the platform module
    doesn't own that table (it currently lives in app/modules/ims), and per
    docs/prd.md modules talk through service interfaces, never each other's tables.
    actor_label snapshots a human-readable name at write time instead, the same
    snapshot approach already used for InvoiceItem/QuotationItem (see CLAUDE.md).
    This also covers actors with no user row at all: an AI agent or a scheduled job.
    """

    __tablename__ = "platform_audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)

    actor_type = Column(String(20), nullable=False, default=AuditActorType.USER)
    actor_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    actor_label = Column(String(255), nullable=True)

    action = Column(String(100), nullable=False)  # CREATE, UPDATE, DELETE, STATUS_CHANGE, ...
    resource_type = Column(String(100), nullable=False)  # org_unit, workflow_instance, employee, ...
    resource_id = Column(String(255), nullable=True)

    before_data = Column(JSON, nullable=True)
    after_data = Column(JSON, nullable=True)
    extra_data = Column(JSON, nullable=True)  # anything else: workflow step id, AI model/prompt version, ...
    ip_address = Column(String(50), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    __table_args__ = (
        Index("ix_platform_audit_logs_org_resource", "org_id", "resource_type", "resource_id"),
        Index("ix_platform_audit_logs_org_created_at", "org_id", "created_at"),
    )
