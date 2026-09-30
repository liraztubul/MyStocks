from fastapi.testclient import TestClient

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
