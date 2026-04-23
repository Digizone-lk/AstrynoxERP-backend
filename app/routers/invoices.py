from uuid import UUID
from typing import List, Optional
from decimal import Decimal
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from sqlalchemy.orm import Session, joinedload
from app.core.database import get_db
from app.dependencies import get_any_authenticated, get_sales_or_admin, get_accountant_or_admin
from app.models.invoice import Invoice, InvoiceItem, InvoiceStatus
from app.models.user import User, UserRole
from app.schemas.invoice import InvoiceCreate, InvoiceUpdate, InvoiceOut, InvoiceDetailOut
from app.services.audit import log_action
from app.services.numbering import next_invoice_number

router = APIRouter(prefix="/api/invoices", tags=["invoices"])


def _get_invoice_user(current_user: User = Depends(get_any_authenticated)) -> User:
    """Accountants can view; sales+admin can create/edit."""
    return current_user


@router.get("/next-number")
def get_next_invoice_number(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_any_authenticated),
):
    return {"invoice_number": next_invoice_number(db, current_user.org_id)}


@router.get("/", response_model=List[InvoiceOut])
def list_invoices(
    status: Optional[InvoiceStatus] = Query(None),
    client_id: Optional[UUID] = Query(None),
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_any_authenticated),
):
    q = db.query(Invoice).filter(Invoice.org_id == current_user.org_id)
    if status:
        q = q.filter(Invoice.status == status)
    if client_id:
        q = q.filter(Invoice.client_id == client_id)
    return q.order_by(Invoice.created_at.desc()).offset(skip).limit(limit).all()


@router.post("/", response_model=InvoiceDetailOut, status_code=status.HTTP_201_CREATED)
def create_invoice(
    payload: InvoiceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_sales_or_admin),
):
    if not payload.items:
        raise HTTPException(status_code=400, detail="Invoice must have at least one item")

    subtotal = sum(item.qty * item.unit_price for item in payload.items)
    invoice_number = next_invoice_number(db, current_user.org_id)

    invoice = Invoice(
        org_id=current_user.org_id,
        client_id=payload.client_id,
        quotation_id=payload.quotation_id,
        created_by=current_user.id,
        invoice_number=invoice_number,
        issue_date=payload.issue_date,
        due_date=payload.due_date,
        notes=payload.notes,
        currency=payload.currency,
        subtotal=subtotal,
        total=subtotal,
    )
    db.add(invoice)
    db.flush()

    for i, item_data in enumerate(payload.items):
        subtotal_item = item_data.qty * item_data.unit_price
        db.add(InvoiceItem(
            invoice_id=invoice.id,
            product_id=item_data.product_id,
            product_name=item_data.product_name,
            description=item_data.description,
            qty=item_data.qty,
            unit_price=item_data.unit_price,
            subtotal=subtotal_item,
            sort_order=i,
        ))

    db.commit()
    db.refresh(invoice)
    log_action(db, current_user, "CREATE", "invoice", str(invoice.id))
    return db.query(Invoice).options(joinedload(Invoice.client), joinedload(Invoice.items)).filter(Invoice.id == invoice.id).first()


@router.get("/{invoice_id}", response_model=InvoiceDetailOut)
def get_invoice(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_any_authenticated),
):
    invoice = (
        db.query(Invoice)
        .options(joinedload(Invoice.client), joinedload(Invoice.items))
        .filter(Invoice.id == invoice_id, Invoice.org_id == current_user.org_id)
        .first()
    )
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice


@router.patch("/{invoice_id}", response_model=InvoiceDetailOut)
def update_invoice(
    invoice_id: UUID,
    payload: InvoiceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_sales_or_admin),
):
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.org_id == current_user.org_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.status not in (InvoiceStatus.DRAFT,):
        raise HTTPException(status_code=400, detail="Only draft invoices can be edited")

    for field, value in payload.model_dump(exclude_unset=True, exclude={"items"}).items():
        setattr(invoice, field, value)

    if payload.items is not None:
        for item in invoice.items:
            db.delete(item)
        db.flush()
        subtotal = Decimal(0)
        for i, item_data in enumerate(payload.items):
            subtotal_item = item_data.qty * item_data.unit_price
            subtotal += subtotal_item
            db.add(InvoiceItem(
                invoice_id=invoice.id,
                product_id=item_data.product_id,
                product_name=item_data.product_name,
                description=item_data.description,
                qty=item_data.qty,
                unit_price=item_data.unit_price,
                subtotal=subtotal_item,
                sort_order=i,
            ))
        invoice.subtotal = subtotal
        invoice.total = subtotal

    db.commit()
    db.refresh(invoice)
    log_action(db, current_user, "UPDATE", "invoice", str(invoice_id))
    return db.query(Invoice).options(joinedload(Invoice.client), joinedload(Invoice.items)).filter(Invoice.id == invoice_id).first()


@router.post("/{invoice_id}/send", response_model=InvoiceOut)
def send_invoice(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_sales_or_admin),
):
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.org_id == current_user.org_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.status != InvoiceStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Only draft invoices can be sent")

    invoice.status = InvoiceStatus.SENT
    db.commit()
    db.refresh(invoice)
    log_action(db, current_user, "STATUS_CHANGE", "invoice", str(invoice_id), {"status": "sent"})
    return invoice


@router.post("/{invoice_id}/mark-paid", response_model=InvoiceOut)
def mark_paid(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_accountant_or_admin),
):
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.org_id == current_user.org_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.status not in (InvoiceStatus.SENT, InvoiceStatus.OVERDUE):
        raise HTTPException(status_code=400, detail="Invoice must be sent or overdue to mark as paid")

    invoice.status = InvoiceStatus.PAID
    invoice.paid_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(invoice)
    log_action(db, current_user, "STATUS_CHANGE", "invoice", str(invoice_id), {"status": "paid"})
    return invoice


@router.post("/{invoice_id}/mark-overdue", response_model=InvoiceOut)
def mark_overdue(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_accountant_or_admin),
):
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.org_id == current_user.org_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.status != InvoiceStatus.SENT:
        raise HTTPException(status_code=400, detail="Only sent invoices can be marked overdue")

    invoice.status = InvoiceStatus.OVERDUE
    db.commit()
    db.refresh(invoice)
    log_action(db, current_user, "STATUS_CHANGE", "invoice", str(invoice_id), {"status": "overdue"})
    return invoice


@router.post("/{invoice_id}/cancel", response_model=InvoiceOut)
def cancel_invoice(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_sales_or_admin),
):
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id, Invoice.org_id == current_user.org_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.status == InvoiceStatus.PAID:
        raise HTTPException(status_code=400, detail="Cannot cancel a paid invoice")

    invoice.status = InvoiceStatus.CANCELLED
    db.commit()
    db.refresh(invoice)
    log_action(db, current_user, "STATUS_CHANGE", "invoice", str(invoice_id), {"status": "cancelled"})
    return invoice


@router.get("/{invoice_id}/pdf")
def download_invoice_pdf(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_any_authenticated),
):
    from app.services.pdf import generate_invoice_pdf
    from app.models.organization import Organization
    invoice = (
        db.query(Invoice)
        .options(joinedload(Invoice.client), joinedload(Invoice.items))
        .filter(Invoice.id == invoice_id, Invoice.org_id == current_user.org_id)
        .first()
    )
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    org = db.query(Organization).filter(Organization.id == current_user.org_id).first()
    pdf_bytes = generate_invoice_pdf(invoice, org)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{invoice.invoice_number}.pdf"'},
    )


@router.post("/{invoice_id}/email-client")
def email_invoice_to_client(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_sales_or_admin),
):
    """Generate the invoice PDF and send it to the client's email address."""
    from app.services.pdf import generate_invoice_pdf
    from app.services.email import send_document_email
    from app.models.organization import Organization

    invoice = (
        db.query(Invoice)
        .options(joinedload(Invoice.client), joinedload(Invoice.items))
        .filter(Invoice.id == invoice_id, Invoice.org_id == current_user.org_id)
        .first()
    )
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if not invoice.client or not invoice.client.email:
        raise HTTPException(status_code=400, detail="Client has no email address")

    org = db.query(Organization).filter(Organization.id == current_user.org_id).first()
    pdf_bytes = generate_invoice_pdf(invoice, org)

    org_name = org.name if org else "BillFlow"
    subject = f"Invoice {invoice.invoice_number} from {org_name}"
    body_text = (
        f"Hi {invoice.client.name},\n\n"
        f"Please find attached invoice {invoice.invoice_number}.\n\n"
        f"Total: {invoice.currency} {float(invoice.total):,.2f}\n\n"
        f"— {org_name}"
    )
    body_html = (
        f"<p>Hi <strong>{invoice.client.name}</strong>,</p>"
        f"<p>Please find attached invoice <strong>{invoice.invoice_number}</strong>.</p>"
        f"<p>Total: <strong>{invoice.currency} {float(invoice.total):,.2f}</strong></p>"
        f"<p>— {org_name}</p>"
    )

    send_document_email(
        to=invoice.client.email,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        pdf_bytes=pdf_bytes,
        filename=f"{invoice.invoice_number}.pdf",
    )

    log_action(db, current_user, "EMAIL", "invoice", str(invoice_id), {"to": invoice.client.email})
    return {"message": f"Invoice emailed to {invoice.client.email}"}
