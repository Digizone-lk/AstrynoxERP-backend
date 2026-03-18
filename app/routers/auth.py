from fastapi import APIRouter, Depends, Response, Cookie, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import create_access_token, create_refresh_token
from app.core.config import settings
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse, RegisterOrgRequest
from app.schemas.user import UserOut
from app.services.auth import (
    register_org,
    authenticate_user,
    get_user_from_refresh_token,
    get_user_from_access_token,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_tokens(response: Response, user: User) -> TokenResponse:
    data = {"sub": str(user.id), "org_id": str(user.org_id), "role": user.role.value}
    access_token = create_access_token(data)
    refresh_token = create_refresh_token(data)

    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=settings.ENVIRONMENT == "production",
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=settings.ENVIRONMENT == "production",
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
    )
    return TokenResponse(access_token=access_token)


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register_organization(payload: RegisterOrgRequest, response: Response, db: Session = Depends(get_db)):
    user = register_org(db, payload)
    _set_tokens(response, user)
    return user


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = authenticate_user(db, payload.email, payload.password)
    return _set_tokens(response, user)


@router.post("/refresh", response_model=TokenResponse)
def refresh(response: Response, refresh_token: str = Cookie(None), db: Session = Depends(get_db)):
    user = get_user_from_refresh_token(db, refresh_token)
    return _set_tokens(response, user)


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return {"message": "Logged out"}


@router.get("/me", response_model=UserOut)
def me(db: Session = Depends(get_db), access_token: str = Cookie(None)):
    return get_user_from_access_token(db, access_token)
