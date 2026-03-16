from uuid import UUID
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from app.core.database import get_db
from app.dependencies import get_any_authenticated, get_sales_or_admin
from app.models.product import Product
from app.models.client import Client
from app.models.client_product import ClientProduct
from app.models.user import User
from app.schemas.product import ProductCreate, ProductUpdate, ProductOut
from app.schemas.client import ClientOut
from app.services.audit import log_action

router = APIRouter(prefix="/api/products", tags=["products"])


@router.get("/", response_model=List[ProductOut])
def list_products(
    is_global: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_any_authenticated),
):
    q = db.query(Product).filter(Product.org_id == current_user.org_id, Product.is_active == True)
    if is_global is not None:
        q = q.filter(Product.is_global == is_global)
    return q.order_by(Product.name).all()


@router.post("/", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(
    payload: ProductCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_sales_or_admin),
):
    product = Product(org_id=current_user.org_id, **payload.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    log_action(db, current_user, "CREATE", "product", str(product.id))
    return product


@router.get("/{product_id}", response_model=ProductOut)
def get_product(
    product_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_any_authenticated),
):
    product = db.query(Product).filter(Product.id == product_id, Product.org_id == current_user.org_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.patch("/{product_id}", response_model=ProductOut)
def update_product(
    product_id: UUID,
    payload: ProductUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_sales_or_admin),
):
    product = db.query(Product).filter(Product.id == product_id, Product.org_id == current_user.org_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, field, value)

    db.commit()
    db.refresh(product)
    log_action(db, current_user, "UPDATE", "product", str(product_id))
    return product


@router.get("/{product_id}/assigned-clients", response_model=List[ClientOut])
def get_assigned_clients(
    product_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_any_authenticated),
):
    """Return all clients that have this product explicitly assigned."""
    product = db.query(Product).filter(Product.id == product_id, Product.org_id == current_user.org_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    assigned_client_ids = (
        db.query(ClientProduct.client_id)
        .filter(ClientProduct.product_id == product_id, ClientProduct.org_id == current_user.org_id)
        .subquery()
    )
    return (
        db.query(Client)
        .filter(Client.id.in_(assigned_client_ids), Client.org_id == current_user.org_id, Client.is_active == True)
        .order_by(Client.name)
        .all()
    )


@router.delete("/{product_id}", status_code=204)
def delete_product(
    product_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_sales_or_admin),
):
    product = db.query(Product).filter(Product.id == product_id, Product.org_id == current_user.org_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    product.is_active = False
    db.commit()
    log_action(db, current_user, "DELETE", "product", str(product_id))
