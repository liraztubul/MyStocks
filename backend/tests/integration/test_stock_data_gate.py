"""The stock-data allowlist, end to end through the API (see app.market_data.access)."""

from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import User
from app.domain.enums import AssetType
from app.main import app
from app.market_data.cache import CachedProvider
from app.market_data.provider import AssetMatch, PriceOnDate, ProviderUnavailableError, Quote
from app.market_data.service import MarketData, shared_market_data

PASSWORD = "correct-horse-battery"
INVITE = "test-invite"
OWNER = "owner@example.com"
GUEST = "guest@example.com"
NOT_AVAILABLE = "not_available_on_deployment"


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class CountingSource:
    def __init__(self, asset_type: AssetType, prices: dict[str, str]) -> None:
        self.asset_type = asset_type
        self.prices = {s: Decimal(p) for s, p in prices.items()}
        self.error: Exception | None = None
        self.calls = 0

    def search(self, query: str) -> list[AssetMatch]:
        self.calls += 1
        return [AssetMatch(query.upper(), query, self.asset_type, query.lower())]

    def get_quote(self, symbol: str, provider_id: str | None = None) -> Quote:
        self.calls += 1
        if self.error:
            raise self.error
        as_of = datetime(2026, 10, 2, 20, 0, tzinfo=UTC)
        return Quote(symbol, self.asset_type, self.prices[symbol], "USD", as_of)

    def get_price_on(self, symbol: str, on: date, provider_id: str | None = None) -> PriceOnDate:
        self.calls += 1
        raise NotImplementedError


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def stocks() -> CountingSource:
    return CountingSource(AssetType.STOCK, {"AAPL": "120"})


@pytest.fixture
def crypto() -> CountingSource:
    return CountingSource(AssetType.CRYPTO, {"BTC": "60000"})


@pytest.fixture
def api(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    stocks: CountingSource,
    crypto: CountingSource,
    clock: Clock,
) -> Iterator[TestClient]:
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "registration_invite_code", INVITE)
    monkeypatch.setattr(settings, "stock_data_allowed_emails", OWNER)
    # The real cache, so "the gate sits in front of it" is tested, not assumed.
    shared = MarketData(
        {
            AssetType.STOCK: CachedProvider(stocks, timer=clock),
            AssetType.CRYPTO: CachedProvider(crypto, timer=clock),
        }
    )
    app.dependency_overrides[shared_market_data] = lambda: shared
    yield client


def register(client: TestClient, email: str) -> int:
    body = {"email": email, "password": PASSWORD, "invite_code": INVITE}
    return client.post("/api/auth/register", json=body).status_code


def log_in(client: TestClient, email: str) -> None:
    register(client, email)
    assert client.post("/api/auth/login", json={"email": email, "password": PASSWORD}).is_success


def buy(
    client: TestClient, symbol: str, asset_type: str, qty: str, price: str, day: int = 1
) -> None:
    response = client.post(
        "/api/transactions",
        json={
            "symbol": symbol,
            "asset_type": asset_type,
            "side": "buy",
            "quantity": qty,
            "price": price,
            "fee": "0",
            "executed_at": f"2026-09-{day:02d}T15:00:00Z",
        },
    )
    assert response.status_code == 201, response.text


def holdings(client: TestClient) -> dict[str, dict[str, Any]]:
    response = client.get("/api/portfolio/holdings")
    assert response.status_code == 200, response.text
    return {h["symbol"]: h for h in response.json()}


def test_blocked_user_keeps_cost_basis_and_gets_no_stock_prices(
    api: TestClient, stocks: CountingSource
) -> None:
    log_in(api, GUEST)
    buy(api, "AAPL", "stock", "10", "100")
    buy(api, "BTC", "crypto", "1", "50000")

    rows = holdings(api)
    aapl, btc = rows["AAPL"], rows["BTC"]
    assert (aapl["quantity"], aapl["average_cost"], aapl["cost_basis"]) == ("10", "100", "1000")
    assert aapl["current_price"] is None and aapl["market_value"] is None
    assert aapl["unrealized_pl"] is None and aapl["day_change"] is None
    assert aapl["price_unavailable_code"] == NOT_AVAILABLE
    assert btc["market_value"] == "60000" and btc["price_unavailable_code"] is None

    summary = api.get("/api/portfolio/summary").json()
    # Cost basis covers everything; value and P/L only the priced subset (BTC).
    assert summary["total_cost_basis"] == "51000"
    assert summary["priced_cost_basis"] == "50000"
    assert summary["total_market_value"] == "60000"
    assert summary["total_unrealized_pl"] == "10000"
    assert summary["total_unrealized_pl_pct"] == "20"
    assert summary["not_available_symbols"] == ["AAPL"]
    assert summary["unpriced_symbols"] == []
    assert "AAPL" not in summary["day_change_unavailable_symbols"]
    assert summary["stock_data_available"] is False
    assert [a["symbol"] for a in summary["allocation"]] == ["BTC"]
    assert stocks.calls == 0


def test_cached_stock_quote_never_leaks_to_a_blocked_user(
    api: TestClient, stocks: CountingSource, clock: Clock
) -> None:
    log_in(api, OWNER)
    buy(api, "AAPL", "stock", "1", "100")
    assert holdings(api)["AAPL"]["current_price"] == "120"
    # Fresh copy expired and the provider down: the owner now gets the stale last-known-good.
    clock.now += 61
    stocks.error = ProviderUnavailableError("down")
    owner_row = holdings(api)["AAPL"]
    assert (owner_row["current_price"], owner_row["price_is_stale"]) == ("120", True)
    calls_before = stocks.calls

    log_in(api, GUEST)
    buy(api, "AAPL", "stock", "1", "100")
    guest_row = holdings(api)["AAPL"]
    assert guest_row["current_price"] is None and guest_row["price_is_stale"] is False
    assert guest_row["price_unavailable_code"] == NOT_AVAILABLE
    assert stocks.calls == calls_before


def test_realized_pl_comes_from_the_ledger_for_everyone(api: TestClient) -> None:
    log_in(api, GUEST)
    buy(api, "AAPL", "stock", "10", "100")
    sell = {
        "symbol": "AAPL",
        "asset_type": "stock",
        "side": "sell",
        "quantity": "4",
        "price": "130",
        "fee": "0",
        "executed_at": "2026-09-05T15:00:00Z",
    }
    assert api.post("/api/transactions", json=sell).status_code == 201
    realized = api.get("/api/portfolio/realized-pl").json()
    assert realized["total_realized_pl"] == "120"


def test_actions_get_403_with_the_code(api: TestClient, stocks: CountingSource) -> None:
    log_in(api, GUEST)
    quote = api.get("/api/assets/AAPL/quote", params={"asset_type": "stock"})
    assert quote.status_code == 403
    assert quote.json()["code"] == NOT_AVAILABLE
    price_on = api.get(
        "/api/assets/AAPL/price-on", params={"asset_type": "stock", "date": "2026-10-01"}
    )
    assert (price_on.status_code, price_on.json()["code"]) == (403, NOT_AVAILABLE)
    assert api.get("/api/assets/BTC/quote", params={"asset_type": "crypto"}).status_code == 200

    search = api.get("/api/assets/search", params={"q": "ap"}).json()
    assert search["stock_data_available"] is False
    assert {r["asset_type"] for r in search["results"]} == {"crypto"}
    assert [(u["asset_type"], u["code"]) for u in search["unavailable"]] == [
        ("stock", NOT_AVAILABLE)
    ]
    assert stocks.calls == 0


def test_allowed_user_is_unchanged(api: TestClient) -> None:
    log_in(api, OWNER)
    buy(api, "AAPL", "stock", "10", "100")
    assert holdings(api)["AAPL"]["market_value"] == "1200"
    summary = api.get("/api/portfolio/summary").json()
    assert summary["stock_data_available"] is True
    assert summary["priced_cost_basis"] == summary["total_cost_basis"] == "1000"
    assert api.get("/api/assets/AAPL/quote", params={"asset_type": "stock"}).status_code == 200


@pytest.mark.parametrize(
    ("environment", "available"), [("production", False), ("development", True)]
)
def test_unset_allowlist_is_closed_in_production_and_open_in_development(
    api: TestClient, monkeypatch: pytest.MonkeyPatch, environment: str, available: bool
) -> None:
    monkeypatch.setattr(settings, "stock_data_allowed_emails", None)
    monkeypatch.setattr(settings, "environment", environment)
    log_in(api, OWNER)
    buy(api, "AAPL", "stock", "1", "100")
    assert api.get("/api/portfolio/summary").json()["stock_data_available"] is available


def test_a_differently_cased_allowlisted_email_cannot_register(api: TestClient) -> None:
    assert register(api, OWNER) == 201
    assert register(api, "Owner@Example.COM") == 409
    assert register(api, "  OWNER@example.com ") in (409, 422)


def test_registration_stores_the_normalized_email(api: TestClient, db_session: Session) -> None:
    assert register(api, "New.Person@Example.COM") == 201
    stored = db_session.scalars(select(User.email).where(User.email.ilike("new.person@%"))).all()
    assert stored == ["new.person@example.com"]


def test_database_rejects_a_mixed_case_email(db_session: Session) -> None:
    db_session.add(User(email="Mixed@Example.com", password_hash="x"))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()
