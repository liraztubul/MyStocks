import uuid
from datetime import datetime, timedelta, timezone

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


def test_access_token_round_trips_user_id() -> None:
    user_id = uuid.uuid4()
    assert decode_access_token(create_access_token(user_id)) == user_id


def test_expired_token_is_rejected() -> None:
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "iat": past, "exp": past + timedelta(minutes=1)},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    assert decode_access_token(token) is None


def test_token_signed_with_other_key_is_rejected() -> None:
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
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
        get_current_user(db=FakeSession(None), access_token=None)
    assert exc.value.status_code == 401


def test_get_current_user_for_deleted_user_raises_401() -> None:
    token = create_access_token(uuid.uuid4())
    with pytest.raises(HTTPException) as exc:
        get_current_user(db=FakeSession(None), access_token=token)
    assert exc.value.status_code == 401


def test_get_current_user_returns_user_for_valid_token() -> None:
    user = User(id=uuid.uuid4(), email="alice@example.com", password_hash="x")
    token = create_access_token(user.id)
    assert get_current_user(db=FakeSession(user), access_token=token) is user
