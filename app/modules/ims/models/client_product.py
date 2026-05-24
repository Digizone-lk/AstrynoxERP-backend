import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base


class ClientProduct(Base):
    """Maps a client-specific product to a client. Products with is_global=False
    must be assigned here to be selectable when that client is chosen."""
    __tablename__ = "client_products"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    organization = relationship("Organization", back_populates="client_products")
    client = relationship("Client", back_populates="client_products")
    product = relationship("Product", back_populates="client_products")

    __table_args__ = (
        UniqueConstraint("client_id", "product_id", name="uq_client_product"),
        UniqueConstraint("org_id", "client_id", "product_id", name="uq_client_product"),
    )
