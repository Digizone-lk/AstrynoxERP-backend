import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class OrgUnitAssignment(Base):
    """Where a person sits in the tree (their position's org_unit), effective-dated.

    person_id is intentionally not a foreign key: per docs/prd.md, "a user is not an
    employee" — some employees never log in, and records exist before accounts during
    onboarding. This will point at hrms employee records once that table exists.
    """

    __tablename__ = "org_unit_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    unit_id = Column(UUID(as_uuid=True), ForeignKey("org_units.id", ondelete="CASCADE"), nullable=False, index=True)
    person_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    position_title = Column(String(255), nullable=True)

    valid_from = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    valid_to = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_org_unit_assignments_org_person", "org_id", "person_id"),
        Index("ix_org_unit_assignments_org_unit", "org_id", "unit_id"),
    )
