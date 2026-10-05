from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.domain.enums import AssetType
from app.main import app
from app.market_data.cache import CachedProvider
from app.market_data.provider import (
    AssetMatch,
    MarketDataError,
    PriceOnDate,
    ProviderUnavailableError,
    Quote,
    ReferenceKind,
)
from app.market_data.service import MarketData, get_market_data

PASSWORD = "correct-horse-battery"
FETCHED_AT = datetime(2026, 10, 2, 20, 0, tzinfo=timezone.utc)
# 00:00 New York (EDT) on the quote's session, as the Finnhub adapter computes it.
SESSION_START = datetime(2026, 10, 2, 4, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class QuoteSource:
    """A provider whose prices and failures the test controls."""

    def __init__(self, asset_type: AssetType) -> None:
        self.asset_type = asset_type
        self.prices: dict[str, Decimal] = {}
        self.references: dict[str, tuple[Decimal, datetime, ReferenceKind]] = {}
        self.error: MarketDataError | None = None

    def search(self, query: str) -> list[AssetMatch]:
        return []

    def get_quote(self, symbol: str, provider_id: str | None = None) -> Quote:
        if self.error:
            raise self.error
        reference = self.references.get(symbol)
        return Quote(
            symbol,
            self.asset_type,
            self.prices[symbol],
            "USD",
            FETCHED_AT,
            reference_price=reference[0] if reference else None,
            reference_at=reference[1] if reference else None,
            reference_kind=reference[2] if reference else None,
        )

    def get_price_on(self, symbol: str, on: date, provider_id: str | None = None) -> PriceOnDate:
        raise NotImplementedError


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def stocks() -> QuoteSource:
    return QuoteSource(AssetType.STOCK)


@pytest.fixture
def crypto() -> QuoteSource:
    return QuoteSource(AssetType.CRYPTO)


@pytest.fixture
def api(client: TestClient, stocks: QuoteSource, crypto: QuoteSource, clock: Clock) -> TestClient:
    # The real cache, so stale fallback is exercised end to end.
    market_data = MarketData(
        {
            AssetType.STOCK: CachedProvider(stocks, timer=clock),
            AssetType.CRYPTO: CachedProvider(crypto, timer=clock),
        }
    )
    app.dependency_overrides[get_market_data] = lambda: market_data
    log_in(client, "alice@example.com")
    return client


def log_in(client: TestClient, email: str) -> None:
    client.post("/api/auth/register", json={"email": email, "password": PASSWORD})
    assert client.post("/api/auth/login", json={"email": email, "password": PASSWORD}).is_success


def trade(
    client: TestClient,
    side: str,
    qty: str,
    price: str,
    fee: str = "0",
    day: int = 1,
    symbol: str = "AAPL",
    asset_type: str = "stock",
    at: str | None = None,
) -> dict[str, Any]:
    response = client.post(
        "/api/transactions",
        json={
            "symbol": symbol,
            "asset_type": asset_type,
            "side": side,
            "quantity": qty,
            "price": price,
            "fee": fee,
            "executed_at": at or f"2026-09-{day:02d}T15:00:00Z",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def worked_example(client: TestClient) -> None:
    trade(client, "buy", "10", "100", fee="5", day=1)
    trade(client, "buy", "5", "130", fee="2.50", day=2)
    trade(client, "sell", "6", "150", fee="3", day=3)


def test_holdings_for_the_worked_example(api: TestClient, stocks: QuoteSource) -> None:
    worked_example(api)
    stocks.prices["AAPL"] = Decimal("120")

    response = api.get("/api/portfolio/holdings")
    assert response.status_code == 200
    assert response.json() == [
        {
            "symbol": "AAPL",
            "asset_type": "stock",
            "quantity": "9",
            "average_cost": "110.5",
            "cost_basis": "994.5",
            "current_price": "120",
            "market_value": "1080",
            "unrealized_pl": "85.5",
            "unrealized_pl_pct": "8.5973",
            "allocation_pct": "100",
            "price_as_of": "2026-10-02T20:00:00Z",
            "price_is_stale": False,
            "price_unavailable_reason": None,
            # No reference price from the provider: day change degrades to null, not 0.
            "day_change": None,
            "day_change_pct": None,
            "day_change_basis": None,
            "day_change_reference_price": None,
            "day_change_reference_at": None,
        }
    ]


def test_summary_totals_and_allocation(
    api: TestClient, stocks: QuoteSource, crypto: QuoteSource
) -> None:
    worked_example(api)
    trade(api, "buy", "0.5", "60000", symbol="BTC", asset_type="crypto")
    stocks.prices["AAPL"] = Decimal("120")
    crypto.prices["BTC"] = Decimal("64000")

    body = api.get("/api/portfolio/summary").json()
    # AAPL 1080 + BTC 32000 = 33080 market value; cost 994.5 + 30000 = 30994.5.
    assert body["total_market_value"] == "33080"
    assert body["total_cost_basis"] == "30994.5"
    assert body["total_unrealized_pl"] == "2085.5"
    assert body["total_realized_pl"] == "234"
    assert body["total_unrealized_pl_pct"] == "6.7286"
    assert body["allocation"] == [
        {"symbol": "AAPL", "market_value": "1080", "allocation_pct": "3.2648"},
        {"symbol": "BTC", "market_value": "32000", "allocation_pct": "96.7352"},
    ]
    assert body["unpriced_symbols"] == []
    assert body["has_stale_prices"] is False
    assert body["currency"] == "USD"


def test_realized_pl_breakdown_newest_first(api: TestClient) -> None:
    worked_example(api)
    second = trade(api, "sell", "4", "90", fee="1", day=4)

    body = api.get("/api/portfolio/realized-pl").json()
    # Second sale: (90 - 110.5) * 4 - 1 = -83, so total 234 - 83 = 151.
    assert body["total_realized_pl"] == "151"
    assert [s["realized_pl"] for s in body["sales"]] == ["-83", "234"]
    assert body["sales"][0] == {
        "transaction_id": second["id"],
        "symbol": "AAPL",
        "executed_at": "2026-09-04T15:00:00Z",
        "quantity": "4",
        "price": "90",
        "fee": "1",
        "average_cost": "110.5",
        "cost_basis": "442",
        "proceeds": "359",
        "realized_pl": "-83",
    }


def test_realized_pl_does_not_need_prices(api: TestClient, stocks: QuoteSource) -> None:
    worked_example(api)
    stocks.error = ProviderUnavailableError("down")
    assert api.get("/api/portfolio/realized-pl").json()["total_realized_pl"] == "234"


def test_failed_refresh_serves_last_known_price_marked_stale(
    api: TestClient, stocks: QuoteSource, clock: Clock
) -> None:
    worked_example(api)
    stocks.prices["AAPL"] = Decimal("120")
    assert api.get("/api/portfolio/holdings").json()[0]["price_is_stale"] is False

    clock.now += 61
    stocks.error = ProviderUnavailableError("Finnhub is unreachable right now.")
    [row] = api.get("/api/portfolio/holdings").json()
    assert row["price_is_stale"] is True
    assert row["price_as_of"] == "2026-10-02T20:00:00Z"
    assert (row["current_price"], row["unrealized_pl"]) == ("120", "85.5")
    assert api.get("/api/portfolio/summary").json()["has_stale_prices"] is True


def test_never_priced_holding_has_null_valuation_not_500(
    api: TestClient, stocks: QuoteSource, crypto: QuoteSource
) -> None:
    worked_example(api)
    trade(api, "buy", "2", "3000", symbol="ETH", asset_type="crypto")
    stocks.error = ProviderUnavailableError("Finnhub is unreachable right now.")
    crypto.prices["ETH"] = Decimal("3500")

    response = api.get("/api/portfolio/holdings")
    assert response.status_code == 200
    aapl, eth = response.json()
    assert aapl["symbol"] == "AAPL"
    for field in ("current_price", "market_value", "unrealized_pl", "unrealized_pl_pct"):
        assert aapl[field] is None
    assert aapl["price_unavailable_reason"] == "Finnhub is unreachable right now."
    assert (aapl["quantity"], aapl["average_cost"]) == ("9", "110.5")
    assert (eth["market_value"], eth["allocation_pct"]) == ("7000", "100")

    summary = api.get("/api/portfolio/summary").json()
    assert summary["unpriced_symbols"] == ["AAPL"]
    assert summary["total_market_value"] == "7000"
    assert summary["total_cost_basis"] == "6994.5"


def test_closed_positions_drop_from_holdings_but_keep_realized(
    api: TestClient, stocks: QuoteSource
) -> None:
    trade(api, "buy", "5", "10", symbol="OLD")
    trade(api, "sell", "5", "12", day=2, symbol="OLD")
    assert api.get("/api/portfolio/holdings").json() == []
    assert api.get("/api/portfolio/summary").json()["total_realized_pl"] == "10"


def test_other_users_trades_are_excluded(api: TestClient, stocks: QuoteSource) -> None:
    worked_example(api)
    log_in(api, "bob@example.com")
    stocks.prices["MSFT"] = Decimal("400")
    trade(api, "buy", "1", "390", symbol="MSFT")
    assert [h["symbol"] for h in api.get("/api/portfolio/holdings").json()] == ["MSFT"]
    assert api.get("/api/portfolio/realized-pl").json()["sales"] == []


def test_oversold_history_after_deleting_a_buy_is_a_clear_409(
    api: TestClient, stocks: QuoteSource
) -> None:
    first_buy = trade(api, "buy", "10", "100", day=1)
    trade(api, "sell", "6", "150", day=3)
    assert api.delete(f"/api/transactions/{first_buy['id']}").status_code == 204

    for path in ("holdings", "summary", "realized-pl"):
        response = api.get(f"/api/portfolio/{path}")
        assert response.status_code == 409
        assert "AAPL" in response.json()["detail"]


def test_portfolio_requires_auth(client: TestClient) -> None:
    for path in ("holdings", "summary", "realized-pl"):
        assert client.get(f"/api/portfolio/{path}").status_code == 401


# --- daily change ---


def previous_close(source: QuoteSource, symbol: str, price: str, close: str) -> None:
    source.prices[symbol] = Decimal(price)
    source.references[symbol] = (Decimal(close), SESSION_START, ReferenceKind.PREVIOUS_CLOSE)


def test_day_change_since_previous_close(api: TestClient, stocks: QuoteSource) -> None:
    worked_example(api)
    previous_close(stocks, "AAPL", price="120", close="115")

    [row] = api.get("/api/portfolio/holdings").json()
    # 9 shares held through the session: 9 * (120 - 115) = 45 on a base of 9 * 115 = 1035.
    assert (row["day_change"], row["day_change_pct"]) == ("45", "4.3478")
    assert row["day_change_basis"] == "since_previous_close"
    assert row["day_change_reference_price"] == "115"
    assert row["day_change_reference_at"] == "2026-10-02T04:00:00Z"


def test_position_opened_today_uses_buy_price(api: TestClient, stocks: QuoteSource) -> None:
    trade(api, "buy", "2", "118", at="2026-10-02T14:30:00Z")
    previous_close(stocks, "AAPL", price="120", close="100")

    [row] = api.get("/api/portfolio/holdings").json()
    # Not 2 * (120 - 100) = 40: the shares were bought today at 118.
    assert (row["day_change"], row["day_change_pct"]) == ("4", "1.6949")


def test_summary_total_day_change_labels_mixed_bases(
    api: TestClient, stocks: QuoteSource, crypto: QuoteSource
) -> None:
    worked_example(api)
    trade(api, "buy", "0.5", "60000", symbol="BTC", asset_type="crypto")
    previous_close(stocks, "AAPL", price="120", close="115")
    crypto.prices["BTC"] = Decimal("64000")
    crypto.references["BTC"] = (
        Decimal("62000"),
        FETCHED_AT - timedelta(hours=24),
        ReferenceKind.ROLLING_24H,
    )

    body = api.get("/api/portfolio/summary").json()
    # AAPL +45 on 1035; BTC 0.5 * (64000 - 62000) = +1000 on 31000. Total 1045 / 32035.
    assert body["total_day_change"] == "1045"
    assert body["total_day_change_pct"] == "3.2621"
    assert body["day_change_bases"] == ["rolling_24h", "since_previous_close"]
    assert body["day_change_unavailable_symbols"] == []


def test_holding_without_reference_is_listed_and_left_out_of_total(
    api: TestClient, stocks: QuoteSource, crypto: QuoteSource
) -> None:
    worked_example(api)
    trade(api, "buy", "2", "3000", symbol="ETH", asset_type="crypto")
    previous_close(stocks, "AAPL", price="120", close="115")
    crypto.prices["ETH"] = Decimal("3500")

    body = api.get("/api/portfolio/summary").json()
    assert body["total_day_change"] == "45"
    assert body["day_change_bases"] == ["since_previous_close"]
    assert body["day_change_unavailable_symbols"] == ["ETH"]


def test_unpriced_holding_has_no_day_change(api: TestClient, stocks: QuoteSource) -> None:
    worked_example(api)
    stocks.error = ProviderUnavailableError("down")
    [row] = api.get("/api/portfolio/holdings").json()
    assert (row["day_change"], row["day_change_basis"]) == (None, None)
    body = api.get("/api/portfolio/summary").json()
    assert (body["total_day_change"], body["day_change_unavailable_symbols"]) == (None, ["AAPL"])


def test_stale_quote_keeps_its_own_consistent_day_change(
    api: TestClient, stocks: QuoteSource, clock: Clock
) -> None:
    worked_example(api)
    previous_close(stocks, "AAPL", price="120", close="115")
    api.get("/api/portfolio/holdings")

    clock.now += 61
    stocks.error = ProviderUnavailableError("down")
    [row] = api.get("/api/portfolio/holdings").json()
    assert row["price_is_stale"] is True
    assert (row["day_change"], row["day_change_reference_price"]) == ("45", "115")


def test_empty_portfolio_summary(api: TestClient) -> None:
    body = api.get("/api/portfolio/summary").json()
    assert (body["total_market_value"], body["total_cost_basis"]) == ("0", "0")
    assert (body["total_day_change"], body["total_day_change_pct"]) == (None, None)
    assert (body["allocation"], body["day_change_bases"]) == ([], [])
