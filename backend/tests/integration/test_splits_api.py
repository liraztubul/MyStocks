"""/api/splits and what a recorded split does to holdings. Synthetic prices only."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api import splits as splits_api
from app.core.config import settings
from app.domain.enums import AssetType
from app.main import app
from app.market_data.provider import Quote, ReferenceKind
from app.market_data.service import MarketData, shared_market_data
from tests.integration.test_portfolio_api import SESSION_START, QuoteSource, log_in, trade

URL = "/api/splits"


class CountingSource(QuoteSource):
    def __init__(self, asset_type: AssetType) -> None:
        super().__init__(asset_type)
        self.calls = 0

    def get_quote(self, symbol: str, provider_id: str | None = None) -> Quote:
        self.calls += 1
        return super().get_quote(symbol, provider_id)


@pytest.fixture
def stocks() -> CountingSource:
    return CountingSource(AssetType.STOCK)


@pytest.fixture
def api(client: TestClient, stocks: CountingSource) -> TestClient:
    crypto = CountingSource(AssetType.CRYPTO)
    market_data = MarketData({AssetType.STOCK: stocks, AssetType.CRYPTO: crypto})
    app.dependency_overrides[shared_market_data] = lambda: market_data
    log_in(client, "alice@example.com")
    return client


def add_split(client: TestClient, ratio: str, on: str, symbol: str = "AAPL") -> Any:
    numerator, denominator = ratio.split(":")
    return client.post(
        URL,
        json={
            "symbol": symbol,
            "effective_date": on,
            "numerator": numerator,
            "denominator": denominator,
        },
    )


def holding(client: TestClient, symbol: str = "AAPL") -> dict[str, Any]:
    rows = {r["symbol"]: r for r in client.get("/api/portfolio/holdings").json()}
    return rows[symbol]


def test_a_split_converts_the_holding(api: TestClient, stocks: CountingSource) -> None:
    trade(api, "buy", "10", "400", day=1)  # 2026-09-01: cost 4000
    stocks.prices["AAPL"] = Decimal("105")
    response = add_split(api, "4:1", "2026-09-14")
    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["symbol"], body["numerator"], body["denominator"]) == ("AAPL", "4", "1")
    assert (body["shares_before"], body["shares_after"]) == ("10", "40")

    row = holding(api)
    # 40 shares, cost 4000, average 100; value 40 * 105 = 4200, unrealized 200 (5%).
    assert (row["quantity"], row["cost_basis"], row["average_cost"]) == ("40", "4000", "100")
    assert (row["market_value"], row["unrealized_pl"], row["unrealized_pl_pct"]) == (
        "4200",
        "200",
        "5",
    )
    assert api.get(URL).json() == [body]


def test_a_sell_after_the_split_and_realized_pl(api: TestClient) -> None:
    trade(api, "buy", "1", "400", day=1)
    assert add_split(api, "4:1", "2026-09-14").status_code == 201
    # 4 shares only exist after the split.
    trade(api, "sell", "4", "110", day=15)
    realized = api.get("/api/portfolio/realized-pl").json()
    # Average 400 / 4 = 100: (110 - 100) * 4 = 40.
    assert realized["total_realized_pl"] == "40"
    assert realized["sales"][0]["average_cost"] == "100"
    # The day before the ex-date, the same sell is in pre-split shares: an oversell.
    early = api.post(
        "/api/transactions",
        json={
            "symbol": "AAPL",
            "asset_type": "stock",
            "side": "sell",
            "quantity": "4",
            "price": "400",
            "executed_at": "2026-09-13T15:00:00Z",
        },
    )
    assert early.status_code == 400
    assert "only 1 held" in early.json()["detail"]


@pytest.mark.parametrize(
    ("ratio", "message"),
    [
        ("0:1", "greater than 0"),
        ("1:0", "greater than 0"),
        ("-2:1", "greater than 0"),
        ("3:3", "can't be 1:1"),
        ("10001:1", "between 1:10000 and 10000:1"),
        ("1:10001", "between 1:10000 and 10000:1"),
    ],
)
def test_invalid_ratios_are_422(api: TestClient, ratio: str, message: str) -> None:
    trade(api, "buy", "1", "400", day=1)
    response = add_split(api, ratio, "2026-09-14")
    assert response.status_code == 422
    assert message in str(response.json()["detail"])


def test_ratio_bounds_are_inclusive(api: TestClient) -> None:
    trade(api, "buy", "10000", "1", day=1)
    assert add_split(api, "10000:1", "2026-09-14").status_code == 201
    assert add_split(api, "1:10000", "2026-09-15").status_code == 201


def test_crypto_and_future_dates_are_422(api: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    api.post(
        "/api/transactions",
        json={
            "symbol": "BTC",
            "asset_type": "crypto",
            "side": "buy",
            "quantity": "1",
            "price": "100",
            "executed_at": "2026-09-01T15:00:00Z",
            "provider_id": "bitcoin",
        },
    )
    crypto = add_split(api, "2:1", "2026-09-14", symbol="BTC")
    assert (crypto.status_code, "stocks only" in crypto.json()["detail"]) == (422, True)

    trade(api, "buy", "1", "400", day=1)
    monkeypatch.setattr(splits_api, "today", lambda: date(2026, 9, 20))
    assert add_split(api, "2:1", "2026-09-20").status_code == 201  # today is allowed
    future = add_split(api, "2:1", "2026-09-21")
    assert (future.status_code, "future" in future.json()["detail"]) == (422, True)


def test_nothing_held_before_the_date_is_400(api: TestClient) -> None:
    assert add_split(api, "2:1", "2026-09-14").status_code == 400  # no trades at all
    trade(api, "buy", "1", "400", day=10)
    # The first trade's own day: the split would come before it, with nothing held.
    on_first_day = add_split(api, "2:1", "2026-09-10")
    assert on_first_day.status_code == 400
    assert "held no AAPL shares before 2026-09-10" in on_first_day.json()["detail"]
    assert add_split(api, "2:1", "2026-09-05").status_code == 400
    # Sold out before the date: nothing to split.
    trade(api, "sell", "1", "410", day=11)
    assert add_split(api, "2:1", "2026-09-14").status_code == 400
    assert add_split(api, "2:1", "2026-09-11").status_code == 201  # the sell is after the split


def test_one_split_per_date_is_409(api: TestClient) -> None:
    trade(api, "buy", "1", "400", day=1)
    assert add_split(api, "2:1", "2026-09-14").status_code == 201
    again = add_split(api, "3:1", "2026-09-14")
    assert (again.status_code, again.json()["code"]) == (409, "split_exists")


def test_a_reverse_split_that_would_oversell_a_later_sell_is_refused(api: TestClient) -> None:
    trade(api, "buy", "50", "2", day=1)
    trade(api, "sell", "10", "3", day=20)
    response = add_split(api, "1:10", "2026-09-14")  # 50 -> 5, then a sell of 10
    assert response.status_code == 400
    assert response.json()["detail"].startswith(
        "With this split, your sell of 10 AAPL on 2026-09-20"
    )
    assert api.get(URL).json() == []


def test_edit_a_split(api: TestClient) -> None:
    trade(api, "buy", "10", "400", day=1)
    trade(api, "buy", "5", "100", day=20)
    split_id = add_split(api, "4:1", "2026-09-14").json()["id"]
    edited = api.patch(f"{URL}/{split_id}", json={"numerator": "2"})
    assert edited.status_code == 200
    assert (edited.json()["numerator"], edited.json()["shares_after"]) == ("2", "20")
    assert holding(api)["quantity"] == "25"
    moved = api.patch(f"{URL}/{split_id}", json={"effective_date": "2026-09-21"})
    # Now after the second buy: (10 + 5) * 2 = 30.
    assert (moved.json()["shares_before"], moved.json()["shares_after"]) == ("15", "30")


def test_edits_are_checked_like_new_splits(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    trade(api, "buy", "1", "400", day=10)
    first = add_split(api, "4:1", "2026-09-14").json()["id"]
    assert add_split(api, "2:1", "2026-09-15").status_code == 201
    trade(api, "sell", "4", "110", day=20)  # 8 held then
    monkeypatch.setattr(splits_api, "today", lambda: date(2026, 9, 30))
    url = f"{URL}/{first}"
    assert api.patch(url, json={"denominator": "4"}).status_code == 422  # 4:4
    assert api.patch(url, json={"numerator": None}).status_code == 422
    assert api.patch(url, json={"effective_date": "2026-10-01"}).status_code == 422  # future
    assert api.patch(url, json={"effective_date": "2026-09-15"}).json()["code"] == "split_exists"
    assert api.patch(url, json={"effective_date": "2026-09-10"}).status_code == 400  # nothing held
    # 1:4 makes 1 share 0.25, then 2:1 -> 0.5: the sell of 4 can't happen.
    reverse = api.patch(url, json={"numerator": "1", "denominator": "4"})
    assert reverse.status_code == 400
    assert reverse.json()["detail"].startswith("With this change, your sell of 4 AAPL")
    assert api.get(URL).json()[1]["numerator"] == "4"  # unchanged


def test_delete_a_split_and_the_oversell_recheck(api: TestClient) -> None:
    trade(api, "buy", "1", "400", day=1)
    split_id = add_split(api, "4:1", "2026-09-14").json()["id"]
    trade(api, "sell", "2", "110", day=20)
    refused = api.delete(f"{URL}/{split_id}")
    assert refused.status_code == 400
    assert refused.json()["detail"] == (
        "Without this split, your sell of 2 AAPL on 2026-09-20 would be more than the 1 shares "
        "held then. Edit or delete that sell first."
    )
    sell_id = next(t["id"] for t in api.get("/api/transactions").json() if t["side"] == "sell")
    assert api.delete(f"/api/transactions/{sell_id}").status_code == 204
    assert api.delete(f"{URL}/{split_id}").status_code == 204
    assert api.get(URL).json() == []
    assert holding(api)["quantity"] == "1"


def test_list_by_symbol_and_other_users(api: TestClient) -> None:
    trade(api, "buy", "1", "400", day=1)
    trade(api, "buy", "1", "300", day=1, symbol="MSFT")
    add_split(api, "4:1", "2026-09-14")
    msft = add_split(api, "2:1", "2026-09-16", symbol="msft").json()
    assert [s["symbol"] for s in api.get(URL).json()] == ["MSFT", "AAPL"]  # newest first
    assert api.get(URL, params={"symbol": " msft "}).json() == [msft]

    log_in(api, "bob@example.com")
    assert api.get(URL).json() == []
    assert api.patch(f"{URL}/{msft['id']}", json={"numerator": "3"}).status_code == 404
    assert api.delete(f"{URL}/{msft['id']}").status_code == 404


def test_a_split_keeps_the_symbol_a_stock(api: TestClient) -> None:
    buy = trade(api, "buy", "1", "400", day=1)
    add_split(api, "4:1", "2026-09-14")
    # Deleting the only trade leaves the split (it then converts nothing)...
    assert api.delete(f"/api/transactions/{buy['id']}").status_code == 204
    assert api.get(URL).json()[0]["shares_before"] == "0"
    # ...and the symbol can't become crypto while it's there.
    crypto = api.post(
        "/api/transactions",
        json={
            "symbol": "AAPL",
            "asset_type": "crypto",
            "side": "buy",
            "quantity": "1",
            "price": "1",
            "executed_at": "2026-09-20T15:00:00Z",
            "provider_id": "apple-coin",
        },
    )
    assert (crypto.status_code, crypto.json()["code"]) == (409, "asset_identity_conflict")


def test_split_writes_never_call_a_provider(api: TestClient, stocks: CountingSource) -> None:
    trade(api, "buy", "1", "400", day=1)
    split_id = add_split(api, "4:1", "2026-09-14").json()["id"]
    api.get(URL)
    api.patch(f"{URL}/{split_id}", json={"numerator": "2"})
    api.delete(f"{URL}/{split_id}")
    assert stocks.calls == 0


def test_no_day_change_on_the_splits_session(api: TestClient, stocks: CountingSource) -> None:
    trade(api, "buy", "10", "400", day=1)
    stocks.prices["AAPL"] = Decimal("103")
    stocks.references["AAPL"] = (Decimal("100"), SESSION_START, ReferenceKind.PREVIOUS_CLOSE)
    session = SESSION_START.date() + timedelta(days=0)  # 2026-10-02 in New York
    split_id = add_split(api, "4:1", "2026-09-14").json()["id"]
    # An earlier split: 40 shares * (103 - 100) = 120 on a base of 4000.
    row = holding(api)
    assert (row["day_change"], row["day_change_pct"]) == ("120", "3")
    api.patch(f"{URL}/{split_id}", json={"effective_date": session.isoformat()})
    row = holding(api)
    assert (row["day_change"], row["day_change_basis"]) == (None, None)
    summary = api.get("/api/portfolio/summary").json()
    assert summary["day_change_unavailable_symbols"] == ["AAPL"]


def test_split_writes_are_refused_from_a_foreign_origin(
    api: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    trade(api, "buy", "1", "400", day=1)
    monkeypatch.setattr(settings, "allowed_origins", "https://mystocks.vercel.app")
    body = {"symbol": "AAPL", "effective_date": "2026-09-14", "numerator": "2", "denominator": "1"}
    response = api.post(URL, json=body, headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
    assert api.get(URL).json() == []


def test_splits_require_auth(client: TestClient) -> None:
    assert client.get(URL).status_code == 401
    body = {"symbol": "AAPL", "effective_date": "2026-09-14", "numerator": "2", "denominator": "1"}
    assert client.post(URL, json=body).status_code == 401
