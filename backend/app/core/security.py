import hashlib
import hmac
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Cookie, Depends, HTTPException, status

from app.core.config import settings
from app.db.models import User
from app.db.session import DbSession

AUTH_COOKIE_NAME = "access_token"

_hasher = PasswordHasher()
# Verified against when the email doesn't exist, so login timing doesn't reveal registered emails.
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing")


def secrets_equal(supplied: str, expected: str) -> bool:
    """Constant-time comparison. Hashing first equalizes lengths, so even the length of the
    expected secret doesn't leak through timing."""
    return hmac.compare_digest(
        hashlib.sha256(supplied.encode()).digest(), hashlib.sha256(expected.encode()).digest()
    )


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def burn_verify_time(password: str) -> None:
    verify_password(password, _DUMMY_HASH)


@dataclass(frozen=True)
class TokenClaims:
    user_id: uuid.UUID
    # The user's token_version when the token was issued; a later logout makes it stale.
    version: int


def token_version(user: User) -> int:
    # 0 until the row is flushed (the column's default applies on insert).
    return user.token_version or 0


def create_access_token(user: User) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user.id),
        "ver": token_version(user),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> TokenClaims | None:
    """The token's claims, or None if it is invalid, expired, or lacks `ver` (issued before
    logout existed: those are rejected, forcing one new login)."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub", "ver"]},
        )
        version = payload["ver"]
        if isinstance(version, bool) or not isinstance(version, int):
            return None
        return TokenClaims(uuid.UUID(payload["sub"]), version)
    except (jwt.PyJWTError, ValueError):
        return None


def get_current_user(
    db: DbSession,
    access_token: Annotated[str | None, Cookie(alias=AUTH_COOKIE_NAME)] = None,
) -> User:
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    if not access_token:
        raise unauthorized
    claims = decode_access_token(access_token)
    if claims is None:
        raise unauthorized
    user = db.get(User, claims.user_id)
    # A token issued before the user's last logout is no longer valid, wherever it is.
    if user is None or token_version(user) != claims.version:
        raise unauthorized
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
