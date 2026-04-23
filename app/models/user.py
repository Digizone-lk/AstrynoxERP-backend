import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum
from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey, Enum, JSON, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base


class UserRole(str, PyEnum):
    SUPER_ADMIN = "super_admin"
    ACCOUNTANT = "accountant"
    SALES = "sales"
    VIEWER = "viewer"


DEFAULT_NOTIFICATION_PREFS = {
    "invoice_paid": True,
    "invoice_overdue": True,
    "quotation_approved": True,
    "quotation_rejected": True,
    "new_user_added": False,
}


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    email = Column(String(255), nullable=False, index=True)
    full_name = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.VIEWER)
    is_active = Column(Boolean, default=True)

    # Profile fields
    phone = Column(String(50), nullable=True)
    job_title = Column(String(100), nullable=True)
    timezone = Column(String(50), nullable=True, default="UTC")
    language = Column(String(10), nullable=True, default="en")
    avatar_url = Column(String(500), nullable=True)
    notification_prefs = Column(JSON, nullable=True)
    allowed_modules = Column(JSON, nullable=True)  # null = all access; list of module keys to restrict

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    organization = relationship("Organization", back_populates="users")
    audit_logs = relationship("AuditLog", back_populates="user")
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("org_id", "email", name="uq_user_org_email"),
    )
