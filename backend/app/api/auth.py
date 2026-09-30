from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.security import (
    AUTH_COOKIE_NAME,
    CurrentUser,
    burn_verify_time,
    create_access_token,
    hash_password,
    verify_password,
)
from app.db.models import User
from app.db.session import DbSession
from app.schemas.auth import LoginRequest, RegisterRequest, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: DbSession) -> User:
    user = User(email=body.email, password_hash=hash_password(body.password))
    db.add(user)
    # Rely on the unique constraint, not a pre-check that would race with concurrent signups.
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Email already registered") from None
    return user


@router.post("/login", response_model=UserRead)
def login(body: LoginRequest, response: Response, db: DbSession) -> User:
    user = db.scalar(select(User).where(User.email == body.email))
    if user is None:
        burn_verify_time(body.password)
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=create_access_token(user.id),
        max_age=settings.access_token_expire_minutes * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return user


@router.get("/me", response_model=UserRead)
def me(user: CurrentUser) -> User:
    return user
