import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy import Column, String, Boolean, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    currency = Column(String(10), default="USD")
    is_active = Column(Boolean, default=True)
    subscription_status = Column(String(20), nullable=False, default="trial")
    plan = Column(String(20), nullable=True)
    trial_start_date = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    trial_end_date = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc) + timedelta(days=14))
    paid_activated_at = Column(DateTime(timezone=True), nullable=True)
    paid_activated_by = Column(String(255), nullable=True)
    onboarding_status = Column(String(30), nullable=False, default="completed")
    # Branding — shown on PDF documents
    address = Column(Text, nullable=True)
    phone = Column(String(50), nullable=True)
    email = Column(String(255), nullable=True)
    website = Column(String(255), nullable=True)
    logo_url = Column(String(500), nullable=True)
    pdf_template = Column(String(20), default="classic")  # classic | modern | minimal
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    users = relationship("User", back_populates="organization", cascade="all, delete-orphan")
    clients = relationship("Client", back_populates="organization", cascade="all, delete-orphan")
    products = relationship("Product", back_populates="organization", cascade="all, delete-orphan")
    quotations = relationship("Quotation", back_populates="organization", cascade="all, delete-orphan")
    invoices = relationship("Invoice", back_populates="organization", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="organization", cascade="all, delete-orphan")
    client_products = relationship("ClientProduct", back_populates="organization", cascade="all, delete-orphan")
    invites = relationship("OrganizationInvite", back_populates="organization", cascade="all, delete-orphan")
