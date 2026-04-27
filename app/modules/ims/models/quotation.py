import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Numeric, Integer, Enum, Date
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base


class QuotationStatus(str, PyEnum):
    DRAFT = "draft"
    SENT = "sent"
    APPROVED = "approved"
    REJECTED = "rejected"
    CONVERTED = "converted"  # Converted to invoice


class Quotation(Base):
    __tablename__ = "quotations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False, index=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    quote_number = Column(String(20), nullable=False)  # QUO-0001
    status = Column(Enum(QuotationStatus), default=QuotationStatus.DRAFT, nullable=False)
    issue_date = Column(Date, nullable=False)
    valid_until = Column(Date, nullable=True)
    notes = Column(Text, nullable=True)
    subtotal = Column(Numeric(14, 2), default=0)
    total = Column(Numeric(14, 2), default=0)
    currency = Column(String(10), default="USD")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    organization = relationship("Organization", back_populates="quotations")
    client = relationship("Client", back_populates="quotations")
    items = relationship("QuotationItem", back_populates="quotation", cascade="all, delete-orphan")
    invoice = relationship("Invoice", back_populates="quotation", uselist=False)


class QuotationItem(Base):
    __tablename__ = "quotation_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    quotation_id = Column(UUID(as_uuid=True), ForeignKey("quotations.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    product_name = Column(String(255), nullable=False)  # Price snapshot
    description = Column(Text, nullable=True)
    qty = Column(Numeric(10, 2), nullable=False, default=1)
    unit_price = Column(Numeric(12, 2), nullable=False)  # Price snapshot
    subtotal = Column(Numeric(14, 2), nullable=False)
    sort_order = Column(Integer, default=0)

    quotation = relationship("Quotation", back_populates="items")
