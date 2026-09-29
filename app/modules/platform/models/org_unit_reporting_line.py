import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, ForeignKey, Index, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class OrgUnitReportingLine(Base):
    """Who a person reports to, kept separate from tree position so "my manager" and
    "head of my department" resolve independently (docs/prd.md). Effective-dated.

    person_id/manager_id are not FK'd for the same reason as OrgUnitAssignment.person_id.
    """

    __tablename__ = "org_unit_reporting_lines"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    person_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    manager_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    valid_from = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    valid_to = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_org_unit_reporting_lines_org_person", "org_id", "person_id"),
        Index("ix_org_unit_reporting_lines_org_manager", "org_id", "manager_id"),
        CheckConstraint("person_id <> manager_id", name="ck_reporting_line_no_self_management"),
    )
