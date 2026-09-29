from sqlalchemy import Column, Integer, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class OrgUnitClosure(Base):
    """Transitive-closure table over org_units for fast subtree/ancestor queries
    (one row per (ancestor, descendant) pair, including a depth-0 self row).

    Reflects the *current* tree shape. It is maintained by
    app.modules.platform.services.org_tree whenever a unit is created or moved.
    """

    __tablename__ = "org_unit_closures"

    ancestor_id = Column(UUID(as_uuid=True), ForeignKey("org_units.id", ondelete="CASCADE"), primary_key=True)
    descendant_id = Column(UUID(as_uuid=True), ForeignKey("org_units.id", ondelete="CASCADE"), primary_key=True)
    depth = Column(Integer, nullable=False)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)

    __table_args__ = (
        Index("ix_org_unit_closures_descendant_id", "descendant_id"),
    )
