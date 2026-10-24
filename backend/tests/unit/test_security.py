import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.db.models import User


def test_correct_password_verifies() -> None:
    assert verify_password("s3cret-password", hash_password("s3cret-password"))


def test_wrong_password_fails() -> None:
    assert not verify_password("wrong-password", hash_password("s3cret-password"))


def test_same_password_hashes_differ_due_to_salt() -> None:
    assert hash_password("s3cret-password") != hash_password("s3cret-password")


def test_malformed_hash_fails_instead_of_raising() -> None:
    assert not verify_password("s3cret-password", "not-an-argon2-hash")


def user(version: int | None = None) -> User:
    return User(
        id=uuid.uuid4(), email="alice@example.com", password_hash="x", token_version=version
    )


def test_access_token_round_trips_user_id_and_version() -> None:
    alice = user(3)
    claims = decode_access_token(create_access_token(alice))
    assert claims is not None and (claims.user_id, claims.version) == (alice.id, 3)


def test_an_unsaved_user_has_version_zero() -> None:
    claims = decode_access_token(create_access_token(user()))
    assert claims is not None and claims.version == 0


@pytest.mark.parametrize("ver", [None, "1", True, 1.5])
def test_a_token_without_an_integer_ver_is_rejected(ver: object) -> None:
    payload: dict[str, object] = {
        "sub": str(uuid.uuid4()),
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    if ver is not None:
        payload["ver"] = ver
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    assert decode_access_token(token) is None


def test_expired_token_is_rejected() -> None:
    past = datetime.now(UTC) - timedelta(hours=1)
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "ver": 0, "iat": past, "exp": past + timedelta(minutes=1)},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    assert decode_access_token(token) is None


def test_token_signed_with_other_key_is_rejected() -> None:
    token = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "ver": 0,
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        "some-other-secret-key-of-sufficient-length",
        algorithm=settings.jwt_algorithm,
    )
    assert decode_access_token(token) is None


class FakeSession:
    def __init__(self, user: User | None) -> None:
        self.user = user

    def get(self, _model: type[User], user_id: uuid.UUID) -> User | None:
        return self.user if self.user and self.user.id == user_id else None


def test_get_current_user_without_cookie_raises_401() -> None:
    with pytest.raises(HTTPException) as exc:
        get_current_user(db=FakeSession(None), access_token=None)  # type: ignore[arg-type]  # a stand-in for Session
    assert exc.value.status_code == 401


def test_get_current_user_for_deleted_user_raises_401() -> None:
    token = create_access_token(user())
    with pytest.raises(HTTPException) as exc:
        get_current_user(db=FakeSession(None), access_token=token)  # type: ignore[arg-type]  # a stand-in for Session
    assert exc.value.status_code == 401


def test_get_current_user_returns_user_for_valid_token() -> None:
    alice = user(2)
    token = create_access_token(alice)
    assert get_current_user(db=FakeSession(alice), access_token=token) is alice  # type: ignore[arg-type]  # a stand-in for Session


def test_get_current_user_rejects_a_token_from_before_a_logout() -> None:
    alice = user(2)
    token = create_access_token(alice)
    alice.token_version = 3  # logged out since
    with pytest.raises(HTTPException) as exc:
        get_current_user(db=FakeSession(alice), access_token=token)  # type: ignore[arg-type]  # a stand-in for Session
    assert exc.value.status_code == 401
