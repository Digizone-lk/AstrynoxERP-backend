from uuid import UUID
from typing import List, Optional
from decimal import Decimal
from datetime import date, datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from app.core.database import get_db
from app.dependencies import get_any_authenticated, get_sales_or_admin, get_accountant_or_admin
from app.models.quotation import Quotation, QuotationItem, QuotationStatus
from app.models.user import User, UserRole
from app.schemas.quotation import QuotationCreate, QuotationUpdate, QuotationOut, QuotationDetailOut
from app.services.audit import log_action
from app.services.numbering import next_quote_number

router = APIRouter(prefix="/api/quotations", tags=["quotations"])


def _calc_totals(items_data) -> Decimal:
    return sum(item.qty * item.unit_price for item in items_data)


def _build_items(quotation_id, items_data, db):
    items = []
    for i, item_data in enumerate(items_data):
        subtotal = item_data.qty * item_data.unit_price
        item = QuotationItem(
            quotation_id=quotation_id,
            product_id=item_data.product_id,
            product_name=item_data.product_name,
            description=item_data.description,
            qty=item_data.qty,
            unit_price=item_data.unit_price,
            subtotal=subtotal,
            sort_order=i,
        )
        items.append(item)
    return items


@router.get("/next-number")
def get_next_quote_number(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_any_authenticated),
):
    return {"quote_number": next_quote_number(db, current_user.org_id)}


@router.get("/", response_model=List[QuotationOut])
def list_quotations(
    status: Optional[QuotationStatus] = Query(None),
    client_id: Optional[UUID] = Query(None),
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_any_authenticated),
):
    q = db.query(Quotation).filter(Quotation.org_id == current_user.org_id)
    if status:
        q = q.filter(Quotation.status == status)
    if client_id:
        q = q.filter(Quotation.client_id == client_id)
    return q.order_by(Quotation.created_at.desc()).offset(skip).limit(limit).all()


@router.post("/", response_model=QuotationDetailOut, status_code=status.HTTP_201_CREATED)
def create_quotation(
    payload: QuotationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_sales_or_admin),
):
    if not payload.items:
        raise HTTPException(status_code=400, detail="Quotation must have at least one item")

    subtotal = sum(item.qty * item.unit_price for item in payload.items)
    quote_number = next_quote_number(db, current_user.org_id)

    quotation = Quotation(
        org_id=current_user.org_id,
        client_id=payload.client_id,
        created_by=current_user.id,
        quote_number=quote_number,
        issue_date=payload.issue_date,
        valid_until=payload.valid_until,
        notes=payload.notes,
        currency=payload.currency,
        subtotal=subtotal,
        total=subtotal,
    )
    db.add(quotation)
    db.flush()

    for i, item_data in enumerate(payload.items):
        subtotal_item = item_data.qty * item_data.unit_price
        db.add(QuotationItem(
            quotation_id=quotation.id,
            product_id=item_data.product_id,
            product_name=item_data.product_name,
            description=item_data.description,
            qty=item_data.qty,
            unit_price=item_data.unit_price,
            subtotal=subtotal_item,
            sort_order=i,
        ))

    db.commit()
    db.refresh(quotation)
    log_action(db, current_user, "CREATE", "quotation", str(quotation.id))
    return db.query(Quotation).options(joinedload(Quotation.client), joinedload(Quotation.items)).filter(Quotation.id == quotation.id).first()


@router.get("/{quotation_id}", response_model=QuotationDetailOut)
def get_quotation(
    quotation_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_any_authenticated),
):
    quotation = (
        db.query(Quotation)
        .options(joinedload(Quotation.client), joinedload(Quotation.items))
        .filter(Quotation.id == quotation_id, Quotation.org_id == current_user.org_id)
        .first()
    )
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")
    return quotation


@router.patch("/{quotation_id}", response_model=QuotationDetailOut)
def update_quotation(
    quotation_id: UUID,
    payload: QuotationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_sales_or_admin),
):
    quotation = db.query(Quotation).filter(Quotation.id == quotation_id, Quotation.org_id == current_user.org_id).first()
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")
    if quotation.status not in (QuotationStatus.DRAFT,):
        raise HTTPException(status_code=400, detail="Only draft quotations can be edited")

    for field, value in payload.model_dump(exclude_unset=True, exclude={"items"}).items():
        setattr(quotation, field, value)

    if payload.items is not None:
        for item in quotation.items:
            db.delete(item)
        db.flush()
        subtotal = Decimal(0)
        for i, item_data in enumerate(payload.items):
            subtotal_item = item_data.qty * item_data.unit_price
            subtotal += subtotal_item
            db.add(QuotationItem(
                quotation_id=quotation.id,
                product_id=item_data.product_id,
                product_name=item_data.product_name,
                description=item_data.description,
                qty=item_data.qty,
                unit_price=item_data.unit_price,
                subtotal=subtotal_item,
                sort_order=i,
            ))
        quotation.subtotal = subtotal
        quotation.total = subtotal

    db.commit()
    db.refresh(quotation)
    log_action(db, current_user, "UPDATE", "quotation", str(quotation_id))
    return db.query(Quotation).options(joinedload(Quotation.client), joinedload(Quotation.items)).filter(Quotation.id == quotation_id).first()


@router.post("/{quotation_id}/send", response_model=QuotationOut)
def send_quotation(
    quotation_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_sales_or_admin),
):
    quotation = db.query(Quotation).filter(Quotation.id == quotation_id, Quotation.org_id == current_user.org_id).first()
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")
    if quotation.status != QuotationStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Only draft quotations can be sent")

    quotation.status = QuotationStatus.SENT
    db.commit()
    db.refresh(quotation)
    log_action(db, current_user, "STATUS_CHANGE", "quotation", str(quotation_id), {"status": "sent"})
    return quotation


@router.post("/{quotation_id}/approve", response_model=QuotationOut)
def approve_quotation(
    quotation_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_sales_or_admin),
):
    quotation = db.query(Quotation).filter(Quotation.id == quotation_id, Quotation.org_id == current_user.org_id).first()
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")
    if quotation.status != QuotationStatus.SENT:
        raise HTTPException(status_code=400, detail="Only sent quotations can be approved")

    quotation.status = QuotationStatus.APPROVED
    db.commit()
    db.refresh(quotation)
    log_action(db, current_user, "STATUS_CHANGE", "quotation", str(quotation_id), {"status": "approved"})
    return quotation


@router.post("/{quotation_id}/reject", response_model=QuotationOut)
def reject_quotation(
    quotation_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_sales_or_admin),
):
    quotation = db.query(Quotation).filter(Quotation.id == quotation_id, Quotation.org_id == current_user.org_id).first()
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")
    if quotation.status not in (QuotationStatus.SENT, QuotationStatus.APPROVED):
        raise HTTPException(status_code=400, detail="Cannot reject quotation in current status")

    quotation.status = QuotationStatus.REJECTED
    db.commit()
    db.refresh(quotation)
    log_action(db, current_user, "STATUS_CHANGE", "quotation", str(quotation_id), {"status": "rejected"})
    return quotation


@router.post("/{quotation_id}/convert-to-invoice", status_code=status.HTTP_201_CREATED)
def convert_to_invoice(
    quotation_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_sales_or_admin),
):
    from app.models.invoice import Invoice, InvoiceItem
    from app.services.numbering import next_invoice_number

    quotation = (
        db.query(Quotation)
        .options(joinedload(Quotation.items))
        .filter(Quotation.id == quotation_id, Quotation.org_id == current_user.org_id)
        .first()
    )
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")
    if quotation.status != QuotationStatus.APPROVED:
        raise HTTPException(status_code=400, detail="Only approved quotations can be converted to invoice")
    if quotation.invoice:
        raise HTTPException(status_code=409, detail="Quotation already converted to invoice")

    invoice_number = next_invoice_number(db, current_user.org_id)
    invoice = Invoice(
        org_id=current_user.org_id,
        client_id=quotation.client_id,
        quotation_id=quotation.id,
        created_by=current_user.id,
        invoice_number=invoice_number,
        issue_date=date.today(),
        currency=quotation.currency,
        notes=quotation.notes,
        subtotal=quotation.subtotal,
        total=quotation.total,
    )
    db.add(invoice)
    db.flush()

    for i, q_item in enumerate(quotation.items):
        db.add(InvoiceItem(
            invoice_id=invoice.id,
            product_id=q_item.product_id,
            product_name=q_item.product_name,
            description=q_item.description,
            qty=q_item.qty,
            unit_price=q_item.unit_price,
            subtotal=q_item.subtotal,
            sort_order=i,
        ))

    quotation.status = QuotationStatus.CONVERTED
    db.commit()
    db.refresh(invoice)
    log_action(db, current_user, "CONVERT", "quotation", str(quotation_id), {"invoice_id": str(invoice.id)})
    return {"invoice_id": str(invoice.id), "invoice_number": invoice.invoice_number}
