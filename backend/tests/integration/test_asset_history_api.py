"""GET /api/assets/{symbol}/history through the real app, with fake providers and a fixed clock."""

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.domain.enums import AssetType
from app.main import app
from app.market_data.history import DailyBar
from app.market_data.price_history import (
    STALE_UNAVAILABLE,
    PriceHistoryService,
    shared_price_history,
)
from app.market_data.provider import (
    AmbiguousSymbolError,
    AssetMatch,
    PriceOnDate,
    ProviderUnavailableError,
    Quote,
    SymbolNotFoundError,
)
from app.market_data.service import MarketData, shared_market_data

PASSWORD = "correct-horse-battery"
INVITE = "test-invite"
TODAY = date(2026, 10, 6)
# Coin -> close formula, so a test can tell which coin was charted.
COINS = {"bitcoin": Decimal(60000), "bitcoin-cash": Decimal(400), "ethereum": Decimal(2500)}
MICRO = Decimal("0.000004361234567891")


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


class FakeHistory:
    name = "coingecko"

    def __init__(self) -> None:
        self.error: Exception | None = None
        self.calls: list[tuple[str, date, date]] = []

    def earliest_available(self, now: datetime) -> date | None:
        return now.date() - timedelta(days=365)

    def last_final_date(self, now: datetime) -> date:
        return now.date() - timedelta(days=1)

    def get_daily_closes(self, provider_id: str, start: date, end: date) -> list[DailyBar]:
        self.calls.append((provider_id, start, end))
        if self.error:
            raise self.error
        if provider_id == "micro":
            return [DailyBar(start, MICRO)]
        if provider_id not in COINS:
            raise SymbolNotFoundError("CoinGecko doesn't know that coin.")
        days = (end - start).days + 1
        return [DailyBar(start + timedelta(days=n), COINS[provider_id]) for n in range(days)]


class FakeCrypto:
    """Ticker rules: BTC is picked automatically, PEPE is ambiguous, DOWN fails, others unknown."""

    def search(self, query: str) -> list[AssetMatch]:
        return []

    def get_quote(self, symbol: str, provider_id: str | None = None) -> Quote:
        ticker = symbol.upper()
        if provider_id is None:
            if ticker == "BTC":
                provider_id, name, auto = "bitcoin", "Bitcoin", True
            elif ticker == "PEPE":
                raise AmbiguousSymbolError(
                    "PEPE",
                    [
                        AssetMatch("PEPE", "Pepe", AssetType.CRYPTO, "pepe", 58),
                        AssetMatch("PEPE", "Based Pepe", AssetType.CRYPTO, "based-pepe", None),
                    ],
                )
            elif ticker == "DOWN":
                raise ProviderUnavailableError("CoinGecko is down")
            else:
                raise SymbolNotFoundError(f"No coin found with symbol {ticker}.")
        else:
            name, auto = None, False
        return Quote(
            ticker,
            AssetType.CRYPTO,
            Decimal(1),
            "USD",
            datetime(2026, 10, 6, tzinfo=UTC),
            coin_id=provider_id,
            coin_name=name,
            coin_auto_picked=auto,
        )

    def get_price_on(self, symbol: str, on: date, provider_id: str | None = None) -> PriceOnDate:
        raise NotImplementedError


class FakeStocks(FakeCrypto):
    def get_quote(self, symbol: str, provider_id: str | None = None) -> Quote:
        return Quote(
            symbol.upper(), AssetType.STOCK, Decimal(100), "USD", datetime(2026, 10, 6, tzinfo=UTC)
        )


@pytest.fixture
def fake_history() -> FakeHistory:
    return FakeHistory()


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def api(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, fake_history: FakeHistory, clock: Clock
) -> Iterator[TestClient]:
    monkeypatch.setattr(settings, "registration_invite_code", INVITE)
    shared = MarketData({AssetType.STOCK: FakeStocks(), AssetType.CRYPTO: FakeCrypto()})
    history = PriceHistoryService({AssetType.CRYPTO: fake_history}, clock=clock)
    app.dependency_overrides[shared_market_data] = lambda: shared
    app.dependency_overrides[shared_price_history] = lambda: history
    log_in(client, "alice@example.com")
    yield client


def log_in(client: TestClient, email: str) -> None:
    body = {"email": email, "password": PASSWORD, "invite_code": INVITE}
    client.post("/api/auth/register", json=body)
    assert client.post("/api/auth/login", json={"email": email, "password": PASSWORD}).is_success


def trade(
    client: TestClient,
    symbol: str,
    at: str,
    provider_id: str | None = None,
    asset_type: str = "crypto",
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "symbol": symbol,
        "asset_type": asset_type,
        "side": "buy",
        "quantity": "1.5",
        "price": "0.0000043612",
        "fee": "0",
        "executed_at": at,
    }
    if provider_id:
        body["provider_id"] = provider_id
    response = client.post("/api/transactions", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def history(client: TestClient, symbol: str, **params: str) -> Any:
    return client.get(f"/api/assets/{symbol}/history", params=params)


# --- Access and validation ------------------------------------------------------------------------


def test_requires_login(api: TestClient) -> None:
    api.cookies.clear()
    assert history(api, "BTC", type="crypto").status_code == 401


def test_invalid_range_is_422(api: TestClient) -> None:
    assert history(api, "BTC", type="crypto", range="2W").status_code == 422


def test_type_is_required_for_a_symbol_the_user_has_never_traded(api: TestClient) -> None:
    assert history(api, "ETH").status_code == 422


def test_unknown_ticker_and_unknown_coin_id_are_404(api: TestClient) -> None:
    assert history(api, "NOPE", type="crypto").status_code == 404
    assert history(api, "XYZ", type="crypto", id="does-not-exist").status_code == 404


# --- Charts ---------------------------------------------------------------------------------------


def test_a_symbol_without_trades_gets_a_normal_chart(api: TestClient) -> None:
    body = history(api, "ETH", type="crypto", id="ethereum", range="1M").json()
    assert (body["available"], body["provider"], body["coin_id"]) == (True, "coingecko", "ethereum")
    assert (body["range_start"], body["range_end"]) == ("2026-09-06", "2026-10-05")
    assert len(body["bars"]) == 30 and body["bars"][0] == {"date": "2026-09-06", "close": "2500"}
    assert (body["markers"], body["undrawn_trades"], body["range_note"]) == ([], [], None)


def test_closes_keep_all_18_decimal_places_as_strings(api: TestClient) -> None:
    body = history(api, "MIC", type="crypto", id="micro", range="1M").json()
    assert body["bars"][0]["close"] == "0.000004361234567891"


def test_ytd_starts_on_january_first(api: TestClient) -> None:
    assert history(api, "ETH", type="crypto", id="ethereum", range="YTD").json()["range_start"] == (
        "2026-01-01"
    )


def test_rule_picked_coin_is_reported_as_such(api: TestClient) -> None:
    body = history(api, "BTC", type="crypto").json()
    assert (body["coin_id"], body["coin_name"], body["coin_auto_picked"]) == (
        "bitcoin",
        "Bitcoin",
        True,
    )


def test_ambiguous_ticker_returns_candidates_and_no_bars(api: TestClient) -> None:
    response = history(api, "PEPE", type="crypto")
    assert response.status_code == 200
    body = response.json()
    assert (body["ambiguous"], body["bars"], body["available"]) == (True, [], True)
    assert body["candidates"] == [
        {"id": "pepe", "symbol": "PEPE", "name": "Pepe", "rank": 58},
        {"id": "based-pepe", "symbol": "PEPE", "name": "Based Pepe", "rank": None},
    ]


def test_provider_down_while_resolving_is_stale_not_an_error(api: TestClient) -> None:
    body = history(api, "DOWN", type="crypto").json()
    assert (body["is_stale"], body["stale_reason"], body["bars"]) == (True, STALE_UNAVAILABLE, [])


# --- Markers --------------------------------------------------------------------------------------


def test_held_symbol_uses_the_recorded_coin_and_only_the_users_trades(api: TestClient) -> None:
    mine = trade(api, "BTC", "2026-09-03T10:00:00Z", provider_id="bitcoin-cash")
    log_in(api, "bob@example.com")
    trade(api, "BTC", "2026-09-04T10:00:00Z", provider_id="bitcoin")
    log_in(api, "alice@example.com")

    body = history(api, "BTC", range="3M").json()  # type inferred from alice's record
    assert (body["coin_id"], body["coin_auto_picked"]) == ("bitcoin-cash", False)
    assert body["bars"][0]["close"] == "400"
    assert [m["transaction_id"] for m in body["markers"]] == [mine["id"]]
    marker = body["markers"][0]
    assert (marker["date"], marker["snapped"], marker["quantity"], marker["price"]) == (
        "2026-09-03",
        False,
        "1.5",
        "0.0000043612",
    )


def test_a_trade_is_placed_on_its_utc_day(api: TestClient) -> None:
    trade(api, "BTC", "2026-09-03T23:30:00-05:00", provider_id="bitcoin")  # 04:30 UTC on Sep 4
    marker = history(api, "BTC", range="3M").json()["markers"][0]
    assert (marker["trade_date"], marker["date"]) == ("2026-09-04", "2026-09-04")


def test_trades_outside_the_chart_are_listed_not_drawn(api: TestClient) -> None:
    old = trade(api, "BTC", "2025-06-01T10:00:00Z", provider_id="bitcoin")
    inside = trade(api, "BTC", "2026-09-10T10:00:00Z")
    today = trade(api, "BTC", "2026-10-06T09:00:00Z")
    body = history(api, "BTC", range="ALL").json()
    # ALL starts at the first trade but is capped at the provider's 365 days, with a note.
    assert body["range_start"] == "2025-10-06" and body["range_note"]
    assert [m["transaction_id"] for m in body["markers"]] == [inside["id"]]
    assert {(u["transaction_id"], u["reason"]) for u in body["undrawn_trades"]} == {
        (old["id"], "before_range"),
        (today["id"], "after_range"),
    }


def test_another_coins_chart_does_not_draw_the_users_trades(api: TestClient) -> None:
    mine = trade(api, "BTC", "2026-09-03T10:00:00Z", provider_id="bitcoin-cash")
    body = history(api, "BTC", id="bitcoin", range="3M").json()
    assert body["coin_id"] == "bitcoin" and body["markers"] == []
    assert [(u["transaction_id"], u["reason"]) for u in body["undrawn_trades"]] == [
        (mine["id"], "different_coin")
    ]


# --- Staleness ------------------------------------------------------------------------------------


def test_provider_failure_serves_cached_bars_marked_stale(
    api: TestClient, fake_history: FakeHistory
) -> None:
    fresh = history(api, "ETH", type="crypto", id="ethereum", range="1M").json()
    fake_history.error = ProviderUnavailableError("down")
    body = history(api, "ETH", type="crypto", id="ethereum", range="3M").json()
    assert (body["is_stale"], body["stale_reason"]) == (True, STALE_UNAVAILABLE)
    assert body["bars"] == fresh["bars"]  # what's cached, with when it was fetched
    assert body["as_of"] == fresh["as_of"]


# --- Stock-data gate ------------------------------------------------------------------------------


@pytest.mark.parametrize("symbol", ["AAPL", "NOSUCHTICKER"])
def test_blocked_user_gets_unavailable_for_any_stock(
    api: TestClient, monkeypatch: pytest.MonkeyPatch, fake_history: FakeHistory, symbol: str
) -> None:
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "stock_data_allowed_emails", "someone-else@example.com")
    response = history(api, symbol, type="stock")
    assert response.status_code == 200
    body = response.json()
    assert (body["available"], body["unavailable_reason"]) == (False, "not_available_on_deployment")
    assert body["bars"] == [] and fake_history.calls == []


def test_allowed_user_has_no_stock_history_provider_yet(
    api: TestClient, fake_history: FakeHistory
) -> None:
    held = trade(api, "AAPL", "2026-09-03T15:00:00Z", asset_type="stock")
    body = history(api, "AAPL", range="1M").json()
    assert (body["available"], body["unavailable_reason"]) == (False, "provider_not_configured")
    assert body["bars"] == [] and fake_history.calls == []
    # The user's own trades are still returned, so the page can list them.
    assert [(u["transaction_id"], u["reason"]) for u in body["undrawn_trades"]] == [
        (held["id"], "no_chart")
    ]
