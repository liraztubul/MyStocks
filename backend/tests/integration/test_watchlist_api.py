"""The watchlist API through the real app: a fake CoinGecko behind the real cache."""

from collections.abc import Iterator, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import User, UserAsset, WatchlistItem
from app.domain.enums import AssetType
from app.main import app
from app.market_data.cache import CachedProvider
from app.market_data.provider import (
    AmbiguousSymbolError,
    AssetMatch,
    CoinRef,
    PriceOnDate,
    ProviderUnavailableError,
    Quote,
    SymbolNotFoundError,
)
from app.market_data.service import MarketData, shared_market_data
from app.services.watchlist import MAX_ITEMS

PASSWORD = "correct-horse-battery"
INVITE = "test-invite"
AS_OF = datetime(2026, 10, 7, 15, 0, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class FakeCoins:
    """Coin ids priced by the test (price, 24h change); ticker rules for unpicked adds."""

    def __init__(self) -> None:
        self.prices: dict[str, tuple[Decimal, Decimal | None]] = {
            "bitcoin": (Decimal("83315"), Decimal("-3.193774756256731")),
            "ethereum": (Decimal("2565.11"), Decimal("-5.4274048985087875")),
            "pepe": (Decimal("0.00000404"), None),
        }
        self.rules: dict[str, tuple[str, ...]] = {
            "BTC": ("pick", "bitcoin", "Bitcoin"),
            "ETH": ("pick", "ethereum", "Ethereum"),
            "PEPE": ("ask",),
        }
        self.down = False
        self.quote_calls: list[tuple[str, str | None]] = []
        self.batch_calls: list[list[str]] = []

    def _quote(self, symbol: str, coin_id: str, name: str | None, auto: bool) -> Quote:
        price, change = self.prices[coin_id]
        return Quote(
            symbol.upper(),
            AssetType.CRYPTO,
            price,
            "USD",
            AS_OF,
            coin_id=coin_id,
            coin_name=name,
            coin_auto_picked=auto,
            change_24h_pct=change,
        )

    def search(self, query: str) -> list[AssetMatch]:
        return []

    def get_quote(self, symbol: str, provider_id: str | None = None) -> Quote:
        self.quote_calls.append((symbol, provider_id))
        if self.down:
            raise ProviderUnavailableError("CoinGecko is unreachable right now.")
        if provider_id is not None:
            if provider_id not in self.prices:
                raise SymbolNotFoundError("unknown coin")
            return self._quote(symbol, provider_id, None, False)
        rule = self.rules.get(symbol.upper())
        if rule is None:
            raise SymbolNotFoundError(f"No coin found with symbol {symbol.upper()}.")
        if rule[0] == "ask":
            raise AmbiguousSymbolError(
                symbol.upper(),
                [
                    AssetMatch("PEPE", "Pepe", AssetType.CRYPTO, "pepe", 58),
                    AssetMatch("PEPE", "Based Pepe", AssetType.CRYPTO, "based-pepe", None),
                ],
            )
        return self._quote(symbol, rule[1], rule[2], True)

    def get_quotes(self, coins: Sequence[CoinRef]) -> dict[str, Quote]:
        self.batch_calls.append([c.coin_id for c in coins])
        if self.down:
            raise ProviderUnavailableError("CoinGecko is unreachable right now.")
        return {
            c.coin_id: self._quote(c.symbol, c.coin_id, None, False)
            for c in coins
            if c.coin_id in self.prices
        }

    def get_price_on(self, symbol: str, on: date, provider_id: str | None = None) -> PriceOnDate:
        raise NotImplementedError


class CountingStocks(FakeCoins):
    def get_quote(self, symbol: str, provider_id: str | None = None) -> Quote:
        self.quote_calls.append((symbol, provider_id))
        raise AssertionError("no stock provider call expected")

    def get_quotes(self, coins: Sequence[CoinRef]) -> dict[str, Quote]:
        raise AssertionError("no stock provider call expected")


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def coins() -> FakeCoins:
    return FakeCoins()


@pytest.fixture
def stocks() -> CountingStocks:
    return CountingStocks()


@pytest.fixture
def api(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    coins: FakeCoins,
    stocks: CountingStocks,
    clock: Clock,
) -> Iterator[TestClient]:
    monkeypatch.setattr(settings, "registration_invite_code", INVITE)
    shared = MarketData(
        {
            AssetType.STOCK: CachedProvider(stocks, timer=clock),
            AssetType.CRYPTO: CachedProvider(coins, timer=clock),
        }
    )
    app.dependency_overrides[shared_market_data] = lambda: shared
    log_in(client, "alice@example.com")
    yield client


def log_in(client: TestClient, email: str) -> None:
    body = {"email": email, "password": PASSWORD, "invite_code": INVITE}
    client.post("/api/auth/register", json=body)
    assert client.post("/api/auth/login", json={"email": email, "password": PASSWORD}).is_success


def add(client: TestClient, symbol: str, type_: str = "crypto", id_: str | None = None) -> Any:
    body: dict[str, Any] = {"symbol": symbol, "type": type_}
    if id_ is not None:
        body["id"] = id_
    return client.post("/api/watchlist", json=body)


def items(client: TestClient) -> list[dict[str, Any]]:
    response = client.get("/api/watchlist")
    assert response.status_code == 200, response.text
    return response.json()


def record(db: Session, symbol: str) -> tuple[str | None, str | None] | None:
    row = db.scalar(select(UserAsset).where(UserAsset.symbol == symbol))
    return None if row is None else (row.provider_id, row.id_source)


# --- Access --------------------------------------------------------------------------------------


def test_every_endpoint_requires_login(api: TestClient) -> None:
    api.cookies.clear()
    assert api.get("/api/watchlist").status_code == 401
    assert add(api, "BTC").status_code == 401
    assert api.delete("/api/watchlist/BTC").status_code == 401


def test_users_cannot_see_or_delete_each_others_items(api: TestClient) -> None:
    assert add(api, "BTC").status_code == 200
    log_in(api, "bob@example.com")
    assert items(api) == []
    assert api.delete("/api/watchlist/BTC").status_code == 204  # idempotent, and only bob's
    log_in(api, "alice@example.com")
    assert [i["symbol"] for i in items(api)] == ["BTC"]


# --- Adding --------------------------------------------------------------------------------------


def test_explicit_id_is_saved_without_resolving(
    api: TestClient, coins: FakeCoins, db_session: Session
) -> None:
    response = add(api, "ETH", id_="ethereum")
    assert response.status_code == 200
    body = response.json()
    assert (body["symbol"], body["coin_id"], body["coin_auto_picked"]) == ("ETH", "ethereum", False)
    assert body["price"] == "2565.11" and body["currency"] == "USD"
    assert coins.quote_calls == []  # no single lookup: the id was given
    assert record(db_session, "ETH") == ("ethereum", "user")


def test_unpicked_clear_winner_is_recorded_as_a_rule_pick(
    api: TestClient, db_session: Session
) -> None:
    assert add(api, "BTC").json()["coin_auto_picked"] is True
    assert record(db_session, "BTC") == ("bitcoin", "rule")


def test_ambiguous_ticker_returns_the_candidates_and_saves_nothing(
    api: TestClient, db_session: Session
) -> None:
    response = add(api, "PEPE")
    assert response.status_code == 422
    assert response.json()["code"] == "ambiguous_symbol"
    assert [c["provider_id"] for c in response.json()["candidates"]] == ["pepe", "based-pepe"]
    assert record(db_session, "PEPE") is None
    # The picker's answer: the same request with the chosen id.
    assert add(api, "PEPE", id_="pepe").status_code == 200


def test_unknown_ticker_is_404(api: TestClient) -> None:
    response = add(api, "NOPE")
    assert (response.status_code, response.json()["code"]) == (404, "symbol_not_found")


def test_adding_twice_is_a_no_op(api: TestClient, db_session: Session) -> None:
    first = add(api, "BTC")
    second = add(api, "BTC")
    assert (first.status_code, second.status_code) == (200, 200)
    assert first.json()["added_at"] == second.json()["added_at"]
    assert db_session.scalar(select(func.count()).select_from(WatchlistItem)) == 1


def test_picking_the_coin_the_rules_chose_confirms_it(api: TestClient, db_session: Session) -> None:
    add(api, "BTC")  # the rules pick bitcoin
    response = add(api, "BTC", id_="bitcoin")  # then the user picks it explicitly
    assert (response.status_code, response.json()["coin_auto_picked"]) == (200, False)
    assert record(db_session, "BTC") == ("bitcoin", "user")


def test_a_different_coin_than_the_users_own_pick_is_a_conflict(api: TestClient) -> None:
    add(api, "BTC", id_="bitcoin")
    response = add(api, "BTC", id_="ethereum")
    assert (response.status_code, response.json()["code"]) == (409, "asset_identity_conflict")


def test_the_cap_has_a_stable_code(api: TestClient, db_session: Session) -> None:
    owner = db_session.scalar(select(User).where(User.email == "alice@example.com"))
    assert owner is not None
    for n in range(MAX_ITEMS):
        symbol = f"C{n}"
        db_session.add(
            UserAsset(
                user_id=owner.id,
                symbol=symbol,
                asset_type=AssetType.CRYPTO,
                provider_id=f"coin-{n}",
                id_source="user",
            )
        )
        db_session.add(WatchlistItem(user_id=owner.id, symbol=symbol))
    db_session.commit()
    response = add(api, "BTC")
    assert (response.status_code, response.json()["code"]) == (409, "watchlist_full")
    assert add(api, "C0").status_code == 200  # re-adding an existing item isn't blocked


# --- Stock gate ----------------------------------------------------------------------------------


def test_blocked_user_adding_a_stock_gets_403_with_no_provider_call(
    api: TestClient, monkeypatch: pytest.MonkeyPatch, stocks: CountingStocks, coins: FakeCoins
) -> None:
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "stock_data_allowed_emails", "someone-else@example.com")
    response = add(api, "AAPL", type_="stock")
    assert (response.status_code, response.json()["code"]) == (403, "not_available_on_deployment")
    assert stocks.quote_calls == [] and coins.quote_calls == [] and coins.batch_calls == []


def test_allowed_user_still_cannot_watch_stocks_in_w1(
    api: TestClient, stocks: CountingStocks
) -> None:
    response = add(api, "AAPL", type_="stock")
    assert (response.status_code, response.json()["code"]) == (422, "watchlist_crypto_only")
    assert stocks.quote_calls == []


# --- Provider down -------------------------------------------------------------------------------


def test_503_only_when_the_coin_must_be_worked_out(
    api: TestClient, coins: FakeCoins, db_session: Session
) -> None:
    coins.down = True
    response = add(api, "ETH")  # no id, no record: the rules need the provider
    assert (response.status_code, response.json()["code"]) == (503, "provider_unavailable")
    assert record(db_session, "ETH") is None

    # An explicit id needs no provider: saved, priced as unavailable.
    saved = add(api, "BTC", id_="bitcoin")
    assert saved.status_code == 200
    assert (saved.json()["price"], saved.json()["unavailable_code"]) == (
        None,
        "provider_unavailable",
    )


def test_a_coin_already_recorded_by_a_trade_needs_no_provider(
    api: TestClient, coins: FakeCoins
) -> None:
    trade = {
        "symbol": "ETH",
        "asset_type": "crypto",
        "side": "buy",
        "quantity": "1",
        "price": "2000",
        "fee": "0",
        "executed_at": "2026-09-01T10:00:00Z",
        "provider_id": "ethereum",
    }
    assert api.post("/api/transactions", json=trade).status_code == 201
    coins.down = True
    coins.quote_calls.clear()
    assert add(api, "ETH").status_code == 200
    assert coins.quote_calls == []


def test_provider_failure_serves_stale_price_and_change_together(
    api: TestClient, coins: FakeCoins, clock: Clock
) -> None:
    add(api, "BTC", id_="bitcoin")
    fresh = items(api)[0]
    assert (fresh["change_pct"], fresh["change_basis"], fresh["stale"]) == (
        "-3.1938",
        "24h_rolling",
        False,
    )
    clock.now += 61
    coins.down = True
    stale = items(api)[0]
    assert stale["stale"] is True
    assert (stale["price"], stale["price_as_of"], stale["change_pct"]) == (
        fresh["price"],
        fresh["price_as_of"],
        fresh["change_pct"],
    )


def test_one_batched_call_for_the_whole_list(
    api: TestClient, coins: FakeCoins, clock: Clock
) -> None:
    add(api, "BTC", id_="bitcoin")
    add(api, "ETH", id_="ethereum")
    clock.now += 61  # let the cache expire
    coins.batch_calls.clear()
    items(api)
    assert coins.batch_calls == [["bitcoin", "ethereum"]]


def test_no_price_at_all_is_null_with_a_reason(api: TestClient, coins: FakeCoins) -> None:
    add(api, "ZZZ", id_="delisted-coin")
    item = items(api)[0]
    assert (item["price"], item["unavailable_code"]) == (None, "symbol_not_found")
    assert item["unavailable_reason"]


def test_change_is_null_when_the_provider_gave_none(api: TestClient) -> None:
    add(api, "PEPE", id_="pepe")
    item = items(api)[0]
    assert (item["price"], item["change_pct"], item["change_basis"]) == ("0.00000404", None, None)


# --- Removing ------------------------------------------------------------------------------------


def test_removing_a_watch_only_coin_removes_its_identity_record(
    api: TestClient, db_session: Session
) -> None:
    add(api, "BTC", id_="bitcoin")
    assert api.delete("/api/watchlist/BTC").status_code == 204
    assert record(db_session, "BTC") is None
    assert api.delete("/api/watchlist/BTC").status_code == 204  # idempotent


def test_removing_a_watch_keeps_the_record_while_trades_use_it(
    api: TestClient, db_session: Session
) -> None:
    trade = {
        "symbol": "ETH",
        "asset_type": "crypto",
        "side": "buy",
        "quantity": "1",
        "price": "2000",
        "fee": "0",
        "executed_at": "2026-09-01T10:00:00Z",
        "provider_id": "ethereum",
    }
    api.post("/api/transactions", json=trade)
    add(api, "ETH")
    assert api.delete("/api/watchlist/eth").status_code == 204  # symbol is case-insensitive
    assert record(db_session, "ETH") == ("ethereum", "user")
