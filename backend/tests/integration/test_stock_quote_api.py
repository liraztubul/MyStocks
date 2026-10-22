"""The stock "latest price" (GET /api/assets/{symbol}/quote?asset_type=stock) through the real app:
a fake Finnhub behind the real 60 s cache. Synthetic prices only.

Proves the gate (a blocked user never reaches the provider), the change from the previous close,
stale and unavailable answers, and that nothing is persisted: no database writes, no-store, no
prices in logs.
"""

import logging
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, event

from app.core.config import settings
from app.domain.enums import AssetType
from app.main import app
from app.market_data.cache import CachedProvider
from app.market_data.provider import (
    AssetMatch,
    PriceOnDate,
    ProviderUnavailableError,
    Quote,
    ReferenceKind,
    SymbolNotFoundError,
)
from app.market_data.service import MarketData, shared_market_data

PASSWORD = "correct-horse-battery"
INVITE = "test-invite"
AS_OF = datetime(2026, 3, 10, 18, 30, tzinfo=UTC)
SESSION = datetime(2026, 3, 9, 4, 0, tzinfo=UTC)  # 00:00 New York on the previous session


class FakeFinnhub:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.error: Exception | None = None

    def get_quote(self, symbol: str, provider_id: str | None = None) -> Quote:
        self.calls.append(symbol)
        if self.error:
            raise self.error
        if symbol.upper() == "NOPE":
            raise SymbolNotFoundError(f"No US stock quote found for {symbol}.")
        return Quote(
            symbol.upper(),
            AssetType.STOCK,
            Decimal("4321.0987"),
            "USD",
            AS_OF,
            reference_price=Decimal("4000"),
            reference_at=SESSION,
            reference_kind=ReferenceKind.PREVIOUS_CLOSE,
        )

    def search(self, query: str) -> list[AssetMatch]:
        return []

    def get_price_on(self, symbol: str, on: date, provider_id: str | None = None) -> PriceOnDate:
        raise NotImplementedError


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def finnhub() -> FakeFinnhub:
    return FakeFinnhub()


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def api(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, finnhub: FakeFinnhub, clock: Clock
) -> Iterator[TestClient]:
    monkeypatch.setattr(settings, "registration_invite_code", INVITE)
    shared = MarketData(
        {
            AssetType.STOCK: CachedProvider(finnhub, timer=clock),
            AssetType.CRYPTO: CachedProvider(FakeFinnhub(), timer=clock),
        }
    )
    app.dependency_overrides[shared_market_data] = lambda: shared
    body = {"email": "owner@example.com", "password": PASSWORD, "invite_code": INVITE}
    client.post("/api/auth/register", json=body)
    assert client.post("/api/auth/login", json={"email": body["email"], "password": PASSWORD})
    yield client


def quote(client: TestClient, symbol: str = "AAPL") -> Any:
    return client.get(f"/api/assets/{symbol}/quote", params={"asset_type": "stock"})


def test_latest_price_with_the_change_since_the_previous_close(api: TestClient) -> None:
    response = quote(api)
    assert response.status_code == 200
    assert response.json() == {
        "symbol": "AAPL",
        "asset_type": "stock",
        "price": "4321.0987",
        "currency": "USD",
        "as_of": "2026-03-10T18:30:00Z",
        "is_stale": False,
        # 4321.0987 - 4000 = 321.0987; / 4000 * 100 = 8.02746... -> 8.0275 (4 places)
        "change": "321.0987",
        "change_pct": "8.0275",
        "change_basis": "since_previous_close",
        "reference_at": "2026-03-09T04:00:00Z",
    }


def test_requests_within_a_minute_share_one_provider_call(
    api: TestClient, finnhub: FakeFinnhub, clock: Clock
) -> None:
    quote(api)
    clock.now = 59
    quote(api)
    assert finnhub.calls == ["AAPL"]
    clock.now = 61
    quote(api)
    assert finnhub.calls == ["AAPL", "AAPL"]


def test_a_failure_serves_the_last_quote_marked_stale_with_its_time(
    api: TestClient, finnhub: FakeFinnhub, clock: Clock
) -> None:
    quote(api)
    clock.now = 61
    finnhub.error = ProviderUnavailableError("Finnhub is unreachable right now.")
    body = quote(api).json()
    assert (body["is_stale"], body["as_of"], body["price"]) == (
        True,
        "2026-03-10T18:30:00Z",
        "4321.0987",
    )


def test_a_failure_without_a_saved_quote_is_unavailable(
    api: TestClient, finnhub: FakeFinnhub
) -> None:
    finnhub.error = ProviderUnavailableError("Finnhub is unreachable right now.")
    response = quote(api)
    assert (response.status_code, response.json()["code"]) == (503, "provider_unavailable")


def test_unknown_ticker_is_404(api: TestClient) -> None:
    response = quote(api, "NOPE")
    assert (response.status_code, response.json()["code"]) == (404, "symbol_not_found")


def test_blocked_user_is_refused_before_any_provider_call(
    api: TestClient, monkeypatch: pytest.MonkeyPatch, finnhub: FakeFinnhub
) -> None:
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "stock_data_allowed_emails", "someone-else@example.com")
    response = quote(api)
    assert (response.status_code, response.json()["code"]) == (403, "not_available_on_deployment")
    assert finnhub.calls == []


def test_the_quote_path_writes_nothing_and_is_never_cached(api: TestClient, engine: Engine) -> None:
    statements: list[str] = []

    def record(_conn: Any, _cursor: Any, statement: str, *_: Any) -> None:
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        response = quote(api)
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert statements, "the listener saw nothing; the check would be vacuous"
    writes = [
        s for s in statements if s.lstrip().split()[0].upper() in {"INSERT", "UPDATE", "DELETE"}
    ]
    assert writes == []
    assert response.headers["Cache-Control"] == "no-store"


def test_no_price_reaches_the_logs(api: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG):
        body = quote(api).json()
    assert body["price"] == "4321.0987"
    for value in ("4321.0987", "321.0987", "8.0275"):
        assert value not in caplog.text
