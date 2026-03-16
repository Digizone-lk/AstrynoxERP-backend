"""PDF endpoint for quotations (added separately to keep quotations.py clean)."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session, joinedload
from app.core.database import get_db
from app.dependencies import get_any_authenticated
from app.models.quotation import Quotation
from app.models.user import User
from app.services.pdf import generate_quotation_pdf

router = APIRouter(prefix="/api/quotations", tags=["quotations"])


@router.get("/{quotation_id}/pdf")
def download_quotation_pdf(
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

    pdf_bytes = generate_quotation_pdf(quotation)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{quotation.quote_number}.pdf"'},
    )
