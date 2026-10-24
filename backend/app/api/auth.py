from typing import Annotated

from fastapi import APIRouter, Cookie, HTTPException, Request, Response, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.edge import client_ip
from app.core.rate_limit import (
    LOGIN_FAILURES_PER_IP_AND_EMAIL,
    LOGIN_PER_IP,
    REGISTER_PER_IP,
    Limit,
    limiter,
)
from app.core.security import (
    AUTH_COOKIE_NAME,
    CurrentUser,
    burn_verify_time,
    create_access_token,
    decode_access_token,
    hash_password,
    secrets_equal,
    token_version,
    verify_password,
)
from app.db.models import User
from app.db.session import DbSession
from app.schemas.auth import LoginRequest, RegisterRequest, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])

REGISTRATION_UNAVAILABLE = "Registration is not available"


def _enforce(key: tuple[str, ...], limit: Limit) -> None:
    retry_after = limiter.retry_after(key, limit)
    if retry_after is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )


def invite_code_accepted(supplied: str | None) -> bool:
    expected = settings.registration_invite_code
    if not expected:
        # No code configured: open in development, closed in production.
        return not settings.is_production
    # Constant-time so response timing can't be used to guess the code character by character.
    return secrets_equal(supplied or "", expected)


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, request: Request, db: DbSession) -> User:
    ip_key = ("register", client_ip(request))
    _enforce(ip_key, REGISTER_PER_IP)
    limiter.record(ip_key)
    # One generic answer for wrong, missing or disabled codes.
    if not invite_code_accepted(body.invite_code):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=REGISTRATION_UNAVAILABLE)

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
def login(body: LoginRequest, request: Request, response: Response, db: DbSession) -> User:
    ip = client_ip(request)
    ip_key = ("login", ip)
    account_key = ("login-failure", ip, body.email)
    _enforce(ip_key, LOGIN_PER_IP)
    _enforce(account_key, LOGIN_FAILURES_PER_IP_AND_EMAIL)
    limiter.record(ip_key)

    user = db.scalar(select(User).where(User.email == body.email))
    if user is None:
        burn_verify_time(body.password)
    if user is None or not verify_password(body.password, user.password_hash):
        limiter.record(account_key)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=create_access_token(user),
        max_age=settings.access_token_expire_minutes * 60,
        **_cookie_attributes(),
    )
    return user


def _cookie_attributes() -> dict[str, object]:
    # Shared by login and logout: a cookie is only deleted if these match the ones it was set with.
    return {"httponly": True, "secure": settings.cookie_secure, "samesite": "lax", "path": "/"}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    db: DbSession,
    access_token: Annotated[str | None, Cookie(alias=AUTH_COOKIE_NAME)] = None,
) -> Response:
    """Always 204, and always clears the cookie (also when it is missing, expired or invalid).
    A valid, current token also bumps the user's token_version, so every token issued before,
    on any device, stops working."""
    claims = decode_access_token(access_token) if access_token else None
    if claims is not None:
        user = db.get(User, claims.user_id)
        if user is not None and token_version(user) == claims.version:
            db.execute(
                update(User).where(User.id == user.id).values(token_version=User.token_version + 1)
            )
            db.commit()
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(AUTH_COOKIE_NAME, **_cookie_attributes())  # type: ignore[arg-type]
    return response


@router.get("/me", response_model=UserRead)
def me(user: CurrentUser) -> User:
    return user
