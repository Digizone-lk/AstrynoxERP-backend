import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base


class OrgUnitType:
    """Suggested unit types for the Organization > Branch > Department > Team > Sub Team
    hierarchy (docs/prd.md). `unit_type` is a free-text column, not a DB enum — tenants
    may introduce new level types (Region, Division, ...) with no schema change."""

    ORGANIZATION = "organization"
    BRANCH = "branch"
    DEPARTMENT = "department"
    TEAM = "team"
    SUB_TEAM = "sub_team"


class OrgUnit(Base):
    """A node in a tenant's org tree. Each unit has a type and a parent (pure tree —
    no cross-branch sharing). The unit with parent_id IS NULL is the tree root and
    represents the organization itself (org_id -> organizations.id).

    Subtree queries go through OrgUnitClosure, not recursive parent_id walks.
    Reporting lines and unit heads live in their own tables, not here.
    """

    __tablename__ = "org_units"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    unit_type = Column(String(50), nullable=False)
    name = Column(String(255), nullable=False)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("org_units.id", ondelete="RESTRICT"), nullable=True, index=True)

    # Optional tenant-defined function tag (Sales, Finance, Operations, ...) so reports
    # roll up across branches regardless of tree position. Not restricted to departments.
    function_tag = Column(String(100), nullable=True)

    valid_from = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    valid_to = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    parent = relationship("OrgUnit", remote_side=[id], backref="children")

    __table_args__ = (
        Index("ix_org_units_org_id_unit_type", "org_id", "unit_type"),
    )
