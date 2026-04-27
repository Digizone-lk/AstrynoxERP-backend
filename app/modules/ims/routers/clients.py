from uuid import UUID
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from app.core.database import get_db
from app.dependencies import get_any_authenticated, get_sales_or_admin
from app.modules.ims.models.client import Client
from app.modules.ims.models.client_product import ClientProduct
from app.modules.ims.models.product import Product
from app.modules.ims.models.user import User
from app.modules.ims.schemas.client import ClientCreate, ClientUpdate, ClientOut
from app.modules.ims.schemas.client_product import ClientProductAssign, ClientProductOut
from app.modules.ims.schemas.product import ProductOut
from app.modules.ims.services.audit import log_action

router = APIRouter(prefix="/api/clients", tags=["clients"])


@router.get("/", response_model=List[ClientOut])
def list_clients(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_any_authenticated),
):
    return (
        db.query(Client)
        .filter(Client.org_id == current_user.org_id, Client.is_active == True)
        .order_by(Client.name)
        .all()
    )


@router.post("/", response_model=ClientOut, status_code=status.HTTP_201_CREATED)
def create_client(
    payload: ClientCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_sales_or_admin),
):
    client = Client(org_id=current_user.org_id, **payload.model_dump())
    db.add(client)
    db.commit()
    db.refresh(client)
    log_action(db, current_user, "CREATE", "client", str(client.id))
    return client


@router.get("/{client_id}", response_model=ClientOut)
def get_client(
    client_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_any_authenticated),
):
    client = db.query(Client).filter(Client.id == client_id, Client.org_id == current_user.org_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@router.patch("/{client_id}", response_model=ClientOut)
def update_client(
    client_id: UUID,
    payload: ClientUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_sales_or_admin),
):
    client = db.query(Client).filter(Client.id == client_id, Client.org_id == current_user.org_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    if "email" in payload.model_fields_set and payload.email is None:
        raise HTTPException(status_code=422, detail="Email cannot be removed from a client")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(client, field, value)

    db.commit()
    db.refresh(client)
    log_action(db, current_user, "UPDATE", "client", str(client_id))
    return client


# ─── Client-specific product assignments ───────────────────────────────────────

@router.get("/{client_id}/products", response_model=List[ProductOut])
def get_eligible_products(
    client_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_any_authenticated),
):
    """Return all products eligible for this client:
    global products + products explicitly assigned to this client."""
    client = db.query(Client).filter(Client.id == client_id, Client.org_id == current_user.org_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Global products
    global_products = (
        db.query(Product)
        .filter(Product.org_id == current_user.org_id, Product.is_global == True, Product.is_active == True)
        .all()
    )

    # Client-specific products
    assigned_product_ids = (
        db.query(ClientProduct.product_id)
        .filter(ClientProduct.client_id == client_id, ClientProduct.org_id == current_user.org_id)
        .subquery()
    )
    client_specific = (
        db.query(Product)
        .filter(
            Product.org_id == current_user.org_id,
            Product.is_global == False,
            Product.is_active == True,
            Product.id.in_(assigned_product_ids),
        )
        .all()
    )

    seen = {p.id for p in global_products}
    combined = list(global_products)
    for p in client_specific:
        if p.id not in seen:
            combined.append(p)

    return combined


@router.get("/{client_id}/assigned-products", response_model=List[ClientProductOut])
def list_assigned_products(
    client_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_any_authenticated),
):
    client = db.query(Client).filter(Client.id == client_id, Client.org_id == current_user.org_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    return (
        db.query(ClientProduct)
        .options(joinedload(ClientProduct.product))
        .filter(ClientProduct.client_id == client_id, ClientProduct.org_id == current_user.org_id)
        .all()
    )


@router.post("/{client_id}/assigned-products", response_model=ClientProductOut, status_code=201)
def assign_product(
    client_id: UUID,
    payload: ClientProductAssign,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_sales_or_admin),
):
    client = db.query(Client).filter(Client.id == client_id, Client.org_id == current_user.org_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    product = db.query(Product).filter(Product.id == payload.product_id, Product.org_id == current_user.org_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    existing = db.query(ClientProduct).filter(
        ClientProduct.client_id == client_id, ClientProduct.product_id == payload.product_id
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Product already assigned to client")

    cp = ClientProduct(org_id=current_user.org_id, client_id=client_id, product_id=payload.product_id)
    db.add(cp)
    db.commit()
    db.refresh(cp)
    log_action(db, current_user, "ASSIGN_PRODUCT", "client_product", str(cp.id))
    return cp


@router.delete("/{client_id}/assigned-products/{product_id}", status_code=204)
def unassign_product(
    client_id: UUID,
    product_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_sales_or_admin),
):
    cp = db.query(ClientProduct).filter(
        ClientProduct.client_id == client_id,
        ClientProduct.product_id == product_id,
        ClientProduct.org_id == current_user.org_id,
    ).first()
    if not cp:
        raise HTTPException(status_code=404, detail="Assignment not found")

    db.delete(cp)
    db.commit()
    log_action(db, current_user, "UNASSIGN_PRODUCT", "client_product", str(product_id))
