import pytest
from starlette.requests import Request

from app.api.auth import invite_code_accepted
from app.core.config import settings
from app.core.edge import client_ip, has_valid_origin_secret
from app.core.security import secrets_equal

SECRET = "s" * 40


def request_with(headers: dict[str, str], peer: str = "10.0.0.9") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/x",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": (peer, 1234),
    }
    return Request(scope)


def test_secrets_equal() -> None:
    assert secrets_equal("abc", "abc")
    assert not secrets_equal("abc", "abd")
    assert not secrets_equal("", "abc")
    assert not secrets_equal("abc", "abcd")


class TestInviteCode:
    def test_development_without_code_is_open(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "environment", "development")
        monkeypatch.setattr(settings, "registration_invite_code", None)
        assert invite_code_accepted(None)

    def test_production_without_code_is_closed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "environment", "production")
        monkeypatch.setattr(settings, "registration_invite_code", None)
        assert not invite_code_accepted(None)
        assert not invite_code_accepted("anything")

    @pytest.mark.parametrize("environment", ["development", "production"])
    def test_configured_code_must_match(
        self, monkeypatch: pytest.MonkeyPatch, environment: str
    ) -> None:
        monkeypatch.setattr(settings, "environment", environment)
        monkeypatch.setattr(settings, "registration_invite_code", "open-sesame")
        assert invite_code_accepted("open-sesame")
        assert not invite_code_accepted("open-sesamE")
        assert not invite_code_accepted("")
        assert not invite_code_accepted(None)


class TestClientIp:
    def test_forwarded_for_is_trusted_only_with_the_origin_secret(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "origin_secret", SECRET)
        via_vercel = request_with({"x-origin-secret": SECRET, "x-forwarded-for": "203.0.113.7"})
        assert has_valid_origin_secret(via_vercel)
        assert client_ip(via_vercel) == "203.0.113.7"

    def test_leftmost_forwarded_entry_is_the_visitor(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Render may append its own hop after Vercel's value.
        monkeypatch.setattr(settings, "origin_secret", SECRET)
        chain = "203.0.113.7, 76.76.21.1"
        req = request_with({"x-origin-secret": SECRET, "x-forwarded-for": chain})
        assert client_ip(req) == "203.0.113.7"

    def test_spoofed_forwarded_for_without_secret_is_ignored(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "origin_secret", SECRET)
        direct = request_with({"x-forwarded-for": "1.2.3.4"}, peer="10.0.0.9")
        assert not has_valid_origin_secret(direct)
        assert client_ip(direct) == "10.0.0.9"

    def test_wrong_secret_is_ignored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "origin_secret", SECRET)
        req = request_with({"x-origin-secret": "x" * 40, "x-forwarded-for": "1.2.3.4"})
        assert client_ip(req) == "10.0.0.9"

    def test_no_secret_configured_uses_peer(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "origin_secret", None)
        req = request_with({"x-origin-secret": "", "x-forwarded-for": "1.2.3.4"})
        assert client_ip(req) == "10.0.0.9"
