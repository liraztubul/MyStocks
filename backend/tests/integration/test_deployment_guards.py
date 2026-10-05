from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import OperationalError

from app.api import probes
from app.core.config import settings
from app.db.session import create_db_engine

from .conftest import TEST_DB_URL

PASSWORD = "correct-horse-battery"
SECRET = "v" * 48
VIA_VERCEL = {"x-origin-secret": SECRET}


def register(client: TestClient, email: str, **extra: Any):
    return client.post("/api/auth/register", json={"email": email, "password": PASSWORD, **extra})


def login(client: TestClient, email: str, password: str = PASSWORD, headers: dict | None = None):
    return client.post(
        "/api/auth/login", json={"email": email, "password": password}, headers=headers or {}
    )


# --- invite code ---


class TestInviteCode:
    def test_right_code_registers(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "registration_invite_code", "open-sesame")
        assert register(client, "a@example.com", invite_code="open-sesame").status_code == 201

    @pytest.mark.parametrize("code", ["wrong", "", None])
    def test_wrong_or_missing_code_gets_a_generic_403(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, code: str | None
    ) -> None:
        monkeypatch.setattr(settings, "registration_invite_code", "open-sesame")
        extra = {} if code is None else {"invite_code": code}
        response = register(client, "a@example.com", **extra)
        assert response.status_code == 403
        assert response.json() == {"detail": "Registration is not available"}

    def test_production_without_a_code_disables_registration(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "environment", "production")
        monkeypatch.setattr(settings, "registration_invite_code", None)
        response = register(client, "a@example.com", invite_code="anything")
        assert (response.status_code, response.json()["detail"]) == (
            403,
            "Registration is not available",
        )

    def test_refused_registration_creates_no_user(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "registration_invite_code", "open-sesame")
        register(client, "a@example.com", invite_code="wrong")
        monkeypatch.setattr(settings, "registration_invite_code", None)
        assert register(client, "a@example.com").status_code == 201


# --- rate limiting ---


class TestRateLimits:
    def test_register_is_limited_per_ip(self, client: TestClient) -> None:
        for i in range(5):
            assert register(client, f"user{i}@example.com").status_code == 201
        blocked = register(client, "user5@example.com")
        assert blocked.status_code == 429
        assert int(blocked.headers["retry-after"]) > 0

    def test_repeated_failures_lock_that_ip_and_email_pair(self, client: TestClient) -> None:
        register(client, "victim@example.com")
        for _ in range(5):
            assert login(client, "victim@example.com", "wrong-password").status_code == 401
        # Even the right password is refused until the window passes...
        assert login(client, "victim@example.com").status_code == 429
        # ...but other accounts from the same IP are unaffected (below the per-IP limit).
        register(client, "other@example.com")
        assert login(client, "other@example.com").status_code == 200

    def test_login_attempts_are_limited_per_ip(self, client: TestClient) -> None:
        register(client, "a@example.com")
        for _ in range(10):
            assert login(client, "a@example.com").status_code == 200
        assert login(client, "a@example.com").status_code == 429

    def test_limits_key_on_the_vercel_forwarded_ip(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "origin_secret", SECRET)
        client.post(
            "/api/auth/register",
            json={"email": "a@example.com", "password": PASSWORD},
            headers=VIA_VERCEL,
        )
        first = {**VIA_VERCEL, "x-forwarded-for": "198.51.100.1"}
        second = {**VIA_VERCEL, "x-forwarded-for": "198.51.100.2"}
        for _ in range(10):
            login(client, "a@example.com", headers=first)
        blocked = login(client, "a@example.com", headers=first)
        other_visitor = login(client, "a@example.com", headers=second)
        assert (blocked.status_code, other_visitor.status_code) == (429, 200)


# --- origin secret and Origin checks ---


class TestEdgeGuard:
    def test_api_without_origin_secret_is_a_generic_403(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "origin_secret", SECRET)
        for response in (
            client.get("/api/auth/me"),
            client.get("/api/auth/me", headers={"x-origin-secret": "x" * 48}),
            client.post("/api/auth/login", json={"email": "a@example.com", "password": "x"}),
        ):
            assert (response.status_code, response.json()) == (403, {"detail": "Forbidden"})

    def test_api_with_origin_secret_passes(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "origin_secret", SECRET)
        assert client.get("/api/auth/me", headers=VIA_VERCEL).status_code == 401

    def test_probes_do_not_need_the_secret(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "origin_secret", SECRET)
        assert client.get("/healthz").status_code == 200

    def test_foreign_origin_cannot_post(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "allowed_origins", "https://mystocks.vercel.app")
        evil = {"origin": "https://evil.example"}
        response = client.post(
            "/api/auth/login", json={"email": "a@example.com", "password": "x"}, headers=evil
        )
        assert response.status_code == 403
        # Reads are unaffected; SameSite and the absence of CORS already protect them.
        assert client.get("/api/auth/me", headers=evil).status_code == 401

    def test_allowed_origin_can_post(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "allowed_origins", "https://mystocks.vercel.app")
        register(client, "a@example.com")
        response = login(client, "a@example.com", headers={"origin": "https://mystocks.vercel.app"})
        assert response.status_code == 200

    def test_api_responses_are_never_cacheable(self, client: TestClient) -> None:
        assert client.get("/api/auth/me").headers["cache-control"] == "no-store"
        register(client, "a@example.com")
        assert login(client, "a@example.com").headers["cache-control"] == "no-store"


# --- probes ---


class BrokenEngine:
    def connect(self) -> None:
        raise OperationalError("SELECT 1", {}, Exception("database is down"))


def test_healthz_never_touches_the_database(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(probes, "engine", BrokenEngine())
    assert client.get("/healthz").json() == {"status": "ok"}


def test_readyz_reports_the_database(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(probes, "engine", create_engine(TEST_DB_URL))
    assert client.get("/readyz").status_code == 200
    monkeypatch.setattr(probes, "engine", BrokenEngine())
    response = client.get("/readyz")
    assert (response.status_code, response.json()) == (503, {"status": "unavailable"})


# --- first request after Neon suspends ---


def _kill_pooled_connections(engine: Engine) -> None:
    # Same effect as Neon suspending compute: the server side of every idle connection vanishes.
    admin = create_engine(TEST_DB_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = current_database() AND pid <> pg_backend_pid() "
                "AND application_name = 'neon-suspend-test'"
            )
        )
    admin.dispose()


def _engine(pre_ping: bool) -> Engine:
    url = TEST_DB_URL.update_query_dict({"application_name": "neon-suspend-test"})
    if pre_ping:
        return create_db_engine(url.render_as_string(hide_password=False))
    return create_engine(url, pool_size=3)


def test_first_query_after_the_database_dropped_connections_succeeds() -> None:
    engine = _engine(pre_ping=True)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))  # leaves one idle connection in the pool
    _kill_pooled_connections(engine)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT 1")).scalar() == 1
    engine.dispose()


def test_without_pre_ping_the_same_scenario_fails() -> None:
    # Control case: proves the test above exercises a real failure mode.
    engine = _engine(pre_ping=False)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    _kill_pooled_connections(engine)
    with pytest.raises(OperationalError), engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    engine.dispose()
