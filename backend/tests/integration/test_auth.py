from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import AUTH_COOKIE_NAME

CREDENTIALS = {"email": "alice@example.com", "password": "correct-horse-battery"}


def register(client: TestClient, **overrides: str):
    return client.post("/api/auth/register", json={**CREDENTIALS, **overrides})


def test_register_login_me_happy_path(client: TestClient) -> None:
    registered = register(client)
    assert registered.status_code == 201
    body = registered.json()
    assert body["email"] == CREDENTIALS["email"]
    assert set(body) == {"id", "email"}

    login = client.post("/api/auth/login", json=CREDENTIALS)
    assert login.status_code == 200
    assert login.json() == body
    assert "access_token" not in login.json()
    set_cookie = login.headers["set-cookie"].lower()
    assert f"{AUTH_COOKIE_NAME}=" in set_cookie
    assert "httponly" in set_cookie
    assert "secure" in set_cookie
    assert "samesite=lax" in set_cookie

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json() == body


def test_register_normalizes_email_case(client: TestClient) -> None:
    assert register(client, email="Alice@Example.COM").json()["email"] == "alice@example.com"


def test_register_duplicate_email_returns_409(client: TestClient) -> None:
    assert register(client).status_code == 201
    assert register(client, email="ALICE@example.com").status_code == 409


def test_register_rejects_short_password(client: TestClient) -> None:
    assert register(client, password="short").status_code == 422


def test_login_wrong_password_returns_401(client: TestClient) -> None:
    register(client)
    response = client.post("/api/auth/login", json={**CREDENTIALS, "password": "wrong-password"})
    assert response.status_code == 401
    assert AUTH_COOKIE_NAME not in response.cookies


def test_login_unknown_email_returns_401(client: TestClient) -> None:
    response = client.post("/api/auth/login", json={**CREDENTIALS, "email": "nobody@example.com"})
    assert response.status_code == 401


def test_me_without_cookie_returns_401(client: TestClient) -> None:
    assert client.get("/api/auth/me").status_code == 401


def test_me_with_tampered_cookie_returns_401(client: TestClient) -> None:
    client.cookies.set(AUTH_COOKIE_NAME, "not-a-real-jwt")
    assert client.get("/api/auth/me").status_code == 401


# --- Logout --------------------------------------------------------------------------------------


def logged_in(client: TestClient) -> str:
    register(client)
    assert client.post("/api/auth/login", json=CREDENTIALS).status_code == 200
    token = client.cookies.get(AUTH_COOKIE_NAME)
    assert token
    return token


def cookie_header(token: str) -> dict[str, str]:
    return {"Cookie": f"{AUTH_COOKIE_NAME}={token}"}


def assert_cookie_cleared(response) -> None:  # type: ignore[no-untyped-def]
    set_cookie = response.headers["set-cookie"].lower()
    assert set_cookie.startswith(f"{AUTH_COOKIE_NAME}=")
    assert "max-age=0" in set_cookie
    # Same attributes as login, or the browser would keep the original cookie.
    assert "httponly" in set_cookie and "secure" in set_cookie
    assert "samesite=lax" in set_cookie and "path=/" in set_cookie


def test_logout_clears_the_cookie_and_revokes_the_token(client: TestClient) -> None:
    token = logged_in(client)
    response = client.post("/api/auth/logout")
    assert response.status_code == 204
    assert_cookie_cleared(response)
    assert client.get("/api/auth/me").status_code == 401
    # The old token, replayed as is (e.g. stolen before the logout), no longer works.
    client.cookies.clear()
    assert client.get("/api/auth/me", headers=cookie_header(token)).status_code == 401


def test_logout_ends_every_session_of_the_user(client: TestClient) -> None:
    phone = logged_in(client)
    me = client.get("/api/auth/me").json()
    # Another device's session: same user and version, issued a minute earlier (a distinct token).
    issued = datetime.now(timezone.utc) - timedelta(minutes=1)
    laptop = jwt.encode(
        {"sub": me["id"], "ver": 0, "iat": issued, "exp": issued + timedelta(minutes=30)},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    assert laptop != phone
    client.cookies.clear()
    assert client.get("/api/auth/me", headers=cookie_header(laptop)).status_code == 200
    assert client.post("/api/auth/logout", headers=cookie_header(phone)).status_code == 204
    assert client.get("/api/auth/me", headers=cookie_header(laptop)).status_code == 401


def test_a_new_login_after_logout_works(client: TestClient) -> None:
    logged_in(client)
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json=CREDENTIALS).status_code == 200
    assert client.get("/api/auth/me").status_code == 200


def test_logout_without_a_cookie_is_204_and_still_clears(client: TestClient) -> None:
    response = client.post("/api/auth/logout")
    assert response.status_code == 204
    assert_cookie_cleared(response)


def test_logout_with_an_invalid_or_stale_token_changes_nothing(client: TestClient) -> None:
    token = logged_in(client)
    client.cookies.clear()
    expired = jwt.encode(
        {"sub": "00000000-0000-0000-0000-000000000000", "ver": 0, "exp": 1},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    for bad in ("not-a-real-jwt", expired):
        response = client.post("/api/auth/logout", headers=cookie_header(bad))
        assert response.status_code == 204
        assert_cookie_cleared(response)
    # Nothing was bumped: the real session still works.
    assert client.get("/api/auth/me", headers=cookie_header(token)).status_code == 200
    # A token from before a logout can't bump the version again (or log out a newer session).
    client.post("/api/auth/logout", headers=cookie_header(token))
    assert client.post("/api/auth/login", json=CREDENTIALS).status_code == 200
    fresh = client.cookies.get(AUTH_COOKIE_NAME)
    client.cookies.clear()
    client.post("/api/auth/logout", headers=cookie_header(token))
    assert client.get("/api/auth/me", headers=cookie_header(fresh)).status_code == 200


def test_logout_from_a_foreign_origin_is_refused(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    logged_in(client)
    monkeypatch.setattr(settings, "allowed_origins", "https://mystocks.vercel.app")
    response = client.post("/api/auth/logout", headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
    assert client.get("/api/auth/me").status_code == 200


def test_logout_without_the_proxy_secret_is_refused(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    logged_in(client)
    monkeypatch.setattr(settings, "origin_secret", "s" * 40)
    assert client.post("/api/auth/logout").status_code == 403
    monkeypatch.setattr(settings, "origin_secret", None)
    assert client.get("/api/auth/me").status_code == 200
