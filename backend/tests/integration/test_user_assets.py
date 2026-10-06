"""user_assets: one meaning per (user, symbol), enforced on every transaction write."""

from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Transaction, UserAsset
from app.domain.enums import AssetType
from app.main import app
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
AS_OF = datetime(2026, 10, 2, 20, 0, tzinfo=UTC)


class FakeCrypto:
    """Coin ids priced by the test; tickers resolved the way the test says."""

    def __init__(self) -> None:
        self.prices = {"bitcoin": Decimal("60000"), "bitcoin-cash": Decimal("400")}
        # Ticker -> ("pick", coin id, name) | ("ask",) | ("down",); unknown tickers aren't found.
        self.rules: dict[str, tuple[str, ...]] = {"BTC": ("pick", "bitcoin", "Bitcoin")}
        self.calls: list[tuple[str, str | None]] = []

    def search(self, query: str) -> list[AssetMatch]:
        return []

    def get_quote(self, symbol: str, provider_id: str | None = None) -> Quote:
        self.calls.append((symbol, provider_id))
        auto, name = False, None
        if provider_id is None:
            rule = self.rules.get(symbol.upper())
            if rule is None:
                raise SymbolNotFoundError(f"No coin found with symbol {symbol}.")
            if rule[0] == "ask":
                candidates = [AssetMatch(symbol, "Coin A", AssetType.CRYPTO, "coin-a")]
                raise AmbiguousSymbolError(symbol.upper(), candidates)
            if rule[0] == "down":
                raise ProviderUnavailableError("CoinGecko is down")
            provider_id, name, auto = rule[1], rule[2], True
        return Quote(
            symbol.upper(),
            AssetType.CRYPTO,
            self.prices.get(provider_id, Decimal("1")),
            "USD",
            AS_OF,
            coin_id=provider_id,
            coin_name=name,
            coin_auto_picked=auto,
        )

    def get_price_on(self, symbol: str, on: date, provider_id: str | None = None) -> PriceOnDate:
        raise NotImplementedError


class FakeStocks(FakeCrypto):
    def get_quote(self, symbol: str, provider_id: str | None = None) -> Quote:
        self.calls.append((symbol, provider_id))
        return Quote(symbol.upper(), AssetType.STOCK, Decimal("100"), "USD", AS_OF)


@pytest.fixture
def crypto() -> FakeCrypto:
    return FakeCrypto()


@pytest.fixture
def api(client: TestClient, crypto: FakeCrypto) -> Iterator[TestClient]:
    shared = MarketData({AssetType.STOCK: FakeStocks(), AssetType.CRYPTO: crypto})
    app.dependency_overrides[shared_market_data] = lambda: shared
    log_in(client, "alice@example.com")
    yield client


def log_in(client: TestClient, email: str) -> None:
    client.post("/api/auth/register", json={"email": email, "password": PASSWORD})
    assert client.post("/api/auth/login", json={"email": email, "password": PASSWORD}).is_success


def post_trade(
    client: TestClient,
    symbol: str = "BTC",
    asset_type: str = "crypto",
    side: str = "buy",
    qty: str = "1",
    provider_id: str | None = None,
    day: int = 1,
) -> Any:
    body: dict[str, Any] = {
        "symbol": symbol,
        "asset_type": asset_type,
        "side": side,
        "quantity": qty,
        "price": "100",
        "fee": "0",
        "executed_at": f"2026-09-{day:02d}T15:00:00Z",
    }
    if provider_id is not None:
        body["provider_id"] = provider_id
    return client.post("/api/transactions", json=body)


def record(db: Session, symbol: str = "BTC") -> tuple[str, str | None, str | None] | None:
    row = db.scalar(select(UserAsset).where(UserAsset.symbol == symbol))
    return None if row is None else (row.asset_type.value, row.provider_id, row.id_source)


def btc_holding(client: TestClient) -> dict[str, Any]:
    return next(h for h in client.get("/api/portfolio/holdings").json() if h["symbol"] == "BTC")


def test_picked_coin_is_recorded_as_the_users(api: TestClient, db_session: Session) -> None:
    assert post_trade(api, provider_id="bitcoin").status_code == 201
    assert record(db_session) == ("crypto", "bitcoin", "user")
    holding = btc_holding(api)
    assert (holding["coin_id"], holding["coin_auto_picked"]) == ("bitcoin", False)


def test_unpicked_clear_winner_is_recorded_as_a_rule_and_disclosed(
    api: TestClient, db_session: Session
) -> None:
    assert post_trade(api).status_code == 201
    assert record(db_session) == ("crypto", "bitcoin", "rule")
    # Recorded by a rule, so still disclosed (the name isn't stored; the UI falls back to the id).
    holding = btc_holding(api)
    assert (holding["coin_id"], holding["coin_auto_picked"]) == ("bitcoin", True)


def test_unknown_coin_record_is_resolved_and_disclosed_at_read_time(
    api: TestClient, crypto: FakeCrypto, db_session: Session
) -> None:
    crypto.rules["BTC"] = ("down",)
    assert post_trade(api).status_code == 201  # a provider outage never blocks the write
    assert record(db_session) == ("crypto", None, None)
    crypto.rules["BTC"] = ("pick", "bitcoin", "Bitcoin")
    holding = btc_holding(api)
    assert (holding["coin_id"], holding["coin_name"], holding["coin_auto_picked"]) == (
        "bitcoin",
        "Bitcoin",
        True,
    )


def test_ambiguous_ticker_without_a_pick_is_refused_and_nothing_written(
    api: TestClient, crypto: FakeCrypto, db_session: Session
) -> None:
    crypto.rules["PEPE"] = ("ask",)
    response = post_trade(api, symbol="PEPE")
    assert response.status_code == 422
    assert response.json()["code"] == "ambiguous_symbol"
    assert [c["provider_id"] for c in response.json()["candidates"]] == ["coin-a"]
    assert record(db_session, "PEPE") is None
    assert db_session.scalar(select(Transaction).where(Transaction.symbol == "PEPE")) is None


def test_a_different_coin_than_the_users_pick_is_a_conflict(
    api: TestClient, db_session: Session
) -> None:
    post_trade(api, provider_id="bitcoin")
    response = post_trade(api, provider_id="bitcoin-cash", day=2)
    assert response.status_code == 409
    assert response.json()["code"] == "asset_identity_conflict"
    assert "bitcoin-cash" in response.json()["detail"]
    assert len(api.get("/api/transactions").json()) == 1
    assert record(db_session) == ("crypto", "bitcoin", "user")


def test_an_explicit_pick_replaces_an_automatic_one(
    api: TestClient, crypto: FakeCrypto, db_session: Session
) -> None:
    post_trade(api)  # rule picked bitcoin
    assert post_trade(api, provider_id="bitcoin-cash", day=2).status_code == 201
    assert record(db_session) == ("crypto", "bitcoin-cash", "user")
    crypto.calls.clear()
    assert btc_holding(api)["current_price"] == "400"
    assert ("BTC", "bitcoin-cash") in crypto.calls


def test_picking_the_same_coin_confirms_an_automatic_pick(
    api: TestClient, db_session: Session
) -> None:
    post_trade(api)
    assert post_trade(api, provider_id="bitcoin", day=2).status_code == 201
    assert record(db_session) == ("crypto", "bitcoin", "user")
    assert btc_holding(api)["coin_auto_picked"] is False


def test_a_sell_without_a_pick_inherits_the_coin(
    api: TestClient, crypto: FakeCrypto, db_session: Session
) -> None:
    post_trade(api, provider_id="bitcoin-cash", qty="2")
    crypto.calls.clear()
    assert post_trade(api, side="sell", qty="1", day=2).status_code == 201
    assert crypto.calls == []  # nothing to resolve: the record already says which coin
    assert record(db_session) == ("crypto", "bitcoin-cash", "user")


def test_asset_type_is_pinned_per_symbol(api: TestClient, db_session: Session) -> None:
    assert post_trade(api, symbol="AAPL", asset_type="stock").status_code == 201
    response = post_trade(api, symbol="AAPL", asset_type="crypto", day=2)
    assert (response.status_code, response.json()["code"]) == (409, "asset_identity_conflict")
    assert record(db_session, "AAPL") == ("stock", None, None)


def test_with_no_trades_left_the_old_meaning_binds_nothing(
    api: TestClient, db_session: Session
) -> None:
    created = post_trade(api, provider_id="bitcoin").json()
    assert api.delete(f"/api/transactions/{created['id']}").status_code == 204
    assert post_trade(api, provider_id="bitcoin-cash", day=2).status_code == 201
    assert record(db_session) == ("crypto", "bitcoin-cash", "user")


def test_editing_a_trade_onto_another_symbol_is_checked(api: TestClient) -> None:
    post_trade(api, symbol="AAPL", asset_type="stock")
    btc = post_trade(api, provider_id="bitcoin", day=2).json()
    response = api.patch(f"/api/transactions/{btc['id']}", json={"symbol": "AAPL"})
    assert (response.status_code, response.json()["code"]) == (409, "asset_identity_conflict")
    # The edit was rolled back: the trade is still BTC.
    assert api.get(f"/api/transactions/{btc['id']}").json()["symbol"] == "BTC"


def test_editing_the_only_trade_may_change_its_type(api: TestClient, db_session: Session) -> None:
    created = post_trade(api, symbol="XYZ", asset_type="stock").json()
    response = api.patch(f"/api/transactions/{created['id']}", json={"asset_type": "crypto"})
    assert response.status_code == 200
    assert record(db_session, "XYZ") == ("crypto", None, None)


def test_two_users_can_mean_different_coins_by_the_same_ticker(api: TestClient) -> None:
    post_trade(api, provider_id="bitcoin")
    log_in(api, "bob@example.com")
    assert post_trade(api, provider_id="bitcoin-cash").status_code == 201
    assert btc_holding(api)["current_price"] == "400"
    log_in(api, "alice@example.com")
    assert btc_holding(api)["current_price"] == "60000"


def test_price_on_for_an_ambiguous_ticker_returns_the_candidates(
    api: TestClient, crypto: FakeCrypto
) -> None:
    crypto.rules["PEPE"] = ("ask",)
    crypto.get_price_on = lambda symbol, on, provider_id=None: crypto.get_quote(symbol, provider_id)  # type: ignore[method-assign,assignment,return-value]
    response = api.get(
        "/api/assets/PEPE/price-on", params={"asset_type": "crypto", "date": "2026-10-01"}
    )
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "ambiguous_symbol" and body["candidates"][0]["provider_id"] == "coin-a"
