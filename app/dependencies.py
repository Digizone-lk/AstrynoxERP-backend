from typing import List
from fastapi import Depends, HTTPException, status, Cookie
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import decode_token
from app.models.user import User, UserRole


def get_current_user(
    access_token: str = Cookie(None),
    db: Session = Depends(get_db),
) -> User:
    if not access_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    payload = decode_token(access_token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return user


def require_roles(*roles: UserRole):
    def checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {[r.value for r in roles]}",
            )
        return current_user
    return checker


# Shorthand role guards
def get_super_admin(user: User = Depends(require_roles(UserRole.SUPER_ADMIN))) -> User:
    return user


def get_sales_or_admin(
    user: User = Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.SALES))
) -> User:
    return user


def get_accountant_or_admin(
    user: User = Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.ACCOUNTANT))
) -> User:
    return user


def get_any_authenticated(user: User = Depends(get_current_user)) -> User:
    """All roles including viewer can access."""
    return user
