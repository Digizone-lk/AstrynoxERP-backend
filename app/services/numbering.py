from sqlalchemy.orm import Session
from sqlalchemy import func


def next_quote_number(db: Session, org_id) -> str:
    from app.models.quotation import Quotation
    count = db.query(func.count(Quotation.id)).filter(Quotation.org_id == org_id).scalar() or 0
    return f"QUO-{(count + 1):04d}"


def next_invoice_number(db: Session, org_id) -> str:
    from app.models.invoice import Invoice
    count = db.query(func.count(Invoice.id)).filter(Invoice.org_id == org_id).scalar() or 0
    return f"INV-{(count + 1):04d}"
