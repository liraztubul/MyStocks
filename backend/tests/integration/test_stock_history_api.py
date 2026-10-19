"""Stock history through the real app, with a fake transient provider (synthetic bars only).

Also proves the no-persistence rules for this path: no database writes, no-store responses, no
prices in logs, nothing reused between requests.
"""

import logging
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, event, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import CoinIndexEntry, DailyClose, PriceHistoryCoverage
from app.main import app
from app.market_data.access import StockDataNotAvailableError, UserStockHistory
from app.market_data.provider import (
    ProviderUnavailableError,
    RateLimitedError,
    RawStockBar,
    SymbolNotFoundError,
)
from app.market_data.stock_history import StockHistoryService, shared_stock_history

PASSWORD = "correct-horse-battery"
INVITE = "test-invite"
# 22:00 New York on Tuesday 10 March 2026 (EDT): the day's bar would already be final.
NOW = datetime(2026, 3, 11, 2, 0, tzinfo=UTC)
TODAY = date(2026, 3, 10)
# Synthetic: a 2:1 split on 5 March. Adjusted: 1234.5678, 1235, 1236, 1235, 1236.
RAW = [
    ("2026-03-02", "2469.1356", "1"),
    ("2026-03-03", "2470", "1"),
    ("2026-03-04", "2472", "1"),
    ("2026-03-05", "1235", "2"),
    ("2026-03-06", "1236", "1"),
]
PRICE_STRINGS = ["2469.1356", "1234.5678"]


class FakeStocks:
    name = "fake"

    def __init__(self) -> None:
        self.calls: list[tuple[str, date, date, bool]] = []
        self.error: Exception | None = None

    def fetch_daily(
        self, ticker: str, start: date, end: date, *, narrow: bool = True
    ) -> list[RawStockBar]:
        self.calls.append((ticker, start, end, narrow))
        if self.error:
            raise self.error
        return [
            RawStockBar(date.fromisoformat(d), Decimal(c), Decimal(f))
            for d, c, f in RAW
            if start <= date.fromisoformat(d) <= end
        ]


@pytest.fixture
def stocks() -> FakeStocks:
    return FakeStocks()


@pytest.fixture
def api(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, stocks: FakeStocks
) -> Iterator[TestClient]:
    monkeypatch.setattr(settings, "registration_invite_code", INVITE)
    service = StockHistoryService(stocks, now=lambda: NOW)
    app.dependency_overrides[shared_stock_history] = lambda: service
    body = {"email": "owner@example.com", "password": PASSWORD, "invite_code": INVITE}
    client.post("/api/auth/register", json=body)
    assert client.post("/api/auth/login", json={"email": body["email"], "password": PASSWORD})
    yield client


def history(client: TestClient, symbol: str, **params: str) -> Any:
    return client.get(f"/api/assets/{symbol}/history", params={"type": "stock", **params})


def stock_trade(client: TestClient, symbol: str, at: str, price: str) -> dict[str, Any]:
    body = {
        "symbol": symbol,
        "asset_type": "stock",
        "side": "buy",
        "quantity": "3",
        "price": price,
        "fee": "0",
        "executed_at": at,
    }
    response = client.post("/api/transactions", json=body)
    assert response.status_code == 201, response.text
    return response.json()


# --- The chart -----------------------------------------------------------------------------------


def test_closes_are_split_adjusted_and_labelled(api: TestClient, stocks: FakeStocks) -> None:
    response = history(api, "AAPL", range="1M")
    assert response.status_code == 200
    body = response.json()
    assert (body["available"], body["adjustment"], body["provider"]) == (
        True,
        "split_adjusted",
        "fake",
    )
    assert [(b["date"], b["close"]) for b in body["bars"]] == [
        ("2026-03-02", "1234.5678"),
        ("2026-03-03", "1235"),
        ("2026-03-04", "1236"),
        ("2026-03-05", "1235"),
        ("2026-03-06", "1236"),
    ]
    assert body["splits"] == [{"date": "2026-03-05", "ratio": "2"}]
    assert (body["range_start"], body["range_end"], body["is_stale"]) == (
        "2026-02-10",
        "2026-03-06",
        False,
    )
    assert stocks.calls == [("AAPL", date(2026, 2, 10), TODAY, True)]


def test_markers_keep_the_price_paid_and_sit_on_the_adjusted_line(api: TestClient) -> None:
    before = stock_trade(api, "AAPL", "2026-03-03T15:00:00Z", "2470")
    on_ex_date = stock_trade(api, "AAPL", "2026-03-05T15:00:00Z", "1235")
    older = stock_trade(api, "AAPL", "2025-06-02T15:00:00Z", "100")
    body = history(api, "AAPL", range="1M").json()
    markers = {m["transaction_id"]: (m["price"], m["chart_price"]) for m in body["markers"]}
    assert markers == {before["id"]: ("2470", "1235"), on_ex_date["id"]: ("1235", "1235")}
    assert [(u["transaction_id"], u["reason"]) for u in body["undrawn_trades"]] == [
        (older["id"], "before_range")
    ]


def test_all_starts_at_the_first_trade(api: TestClient, stocks: FakeStocks) -> None:
    stock_trade(api, "AAPL", "2020-08-14T15:00:00Z", "100")
    body = history(api, "AAPL", range="ALL").json()
    assert (body["range_start"], body["range_note"]) == ("2020-08-14", None)
    assert stocks.calls[0][1] == date(2020, 8, 14)


def test_all_without_trades_is_capped_at_ten_years_with_a_note(
    api: TestClient, stocks: FakeStocks
) -> None:
    body = history(api, "AAPL", range="ALL").json()
    assert body["range_start"] == "2016-03-10"
    assert "past 10 years" in body["range_note"]
    assert stocks.calls[0][1] == date(2016, 3, 10)


def test_the_users_ticker_is_kept_and_the_provider_gets_its_own_spelling(
    api: TestClient, stocks: FakeStocks
) -> None:
    body = history(api, "brk.b", range="1M").json()
    assert body["symbol"] == "BRK.B"
    assert stocks.calls[0][0] == "BRK-B"


# --- Failures: no stale data exists for stocks ---------------------------------------------------


def test_unknown_ticker_is_404_in_our_own_words(api: TestClient, stocks: FakeStocks) -> None:
    stocks.error = SymbolNotFoundError("Error: Ticker 'ZZZQ' not found")
    response = history(api, "ZZZQ", range="1M")
    assert response.status_code == 404
    assert response.json()["detail"] == "No stock history found for ZZZQ."


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (RateLimitedError("slow down", retry_after=60), "rate_limited"),
        (ProviderUnavailableError("down"), "provider_unavailable"),
    ],
)
def test_provider_failures_are_unavailable_with_a_reason(
    api: TestClient, stocks: FakeStocks, error: Exception, reason: str
) -> None:
    held = stock_trade(api, "AAPL", "2026-03-03T15:00:00Z", "2470")
    stocks.error = error
    body = history(api, "AAPL", range="1M").json()
    assert (body["available"], body["unavailable_reason"], body["bars"]) == (False, reason, [])
    assert body["retry_after"] == (60 if reason == "rate_limited" else None)
    assert [(u["transaction_id"], u["reason"]) for u in body["undrawn_trades"]] == [
        (held["id"], "no_chart")
    ]


def test_without_a_key_the_provider_is_not_configured(api: TestClient) -> None:
    app.dependency_overrides[shared_stock_history] = lambda: StockHistoryService(None)
    body = history(api, "AAPL", range="1M").json()
    assert (body["available"], body["unavailable_reason"]) == (False, "provider_not_configured")


# --- The gate ------------------------------------------------------------------------------------


@pytest.mark.parametrize("range_", ["1M", "ALL"])
def test_blocked_user_never_reaches_the_provider(
    api: TestClient, monkeypatch: pytest.MonkeyPatch, stocks: FakeStocks, range_: str
) -> None:
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "stock_data_allowed_emails", "someone-else@example.com")
    body = history(api, "AAPL", range=range_).json()
    assert (body["available"], body["unavailable_reason"]) == (False, "not_available_on_deployment")
    assert body["bars"] == [] and stocks.calls == []


def test_the_gate_object_refuses_a_blocked_user_before_the_service(stocks: FakeStocks) -> None:
    gate = UserStockHistory(
        StockHistoryService(stocks, now=lambda: NOW), stock_data_available=False
    )
    with pytest.raises(StockDataNotAvailableError):
        gate.series("AAPL", TODAY, TODAY)
    assert stocks.calls == []


def test_login_required(api: TestClient) -> None:
    api.cookies.clear()
    assert history(api, "AAPL", range="1M").status_code == 401


# --- No persistence ------------------------------------------------------------------------------


def table_counts(db: Session) -> tuple[int, int, int]:
    return (
        db.scalar(select(func.count()).select_from(DailyClose)) or 0,
        db.scalar(select(func.count()).select_from(PriceHistoryCoverage)) or 0,
        db.scalar(select(func.count()).select_from(CoinIndexEntry)) or 0,
    )


def test_the_stock_history_path_writes_nothing_to_the_database(
    api: TestClient, engine: Engine, db_session: Session
) -> None:
    stock_trade(api, "AAPL", "2026-03-03T15:00:00Z", "2470")
    counts = table_counts(db_session)
    statements: list[str] = []

    def record(_conn: Any, _cursor: Any, statement: str, *_: Any) -> None:
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        for range_ in ("1M", "ALL", "YTD"):
            assert history(api, "AAPL", range=range_).json()["available"] is True
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert statements, "the listener saw nothing; the check would be vacuous"
    writes = [
        s for s in statements if s.lstrip().split()[0].upper() in {"INSERT", "UPDATE", "DELETE"}
    ]
    assert writes == []
    touched = [
        s
        for s in statements
        if any(t in s for t in ("daily_closes", "price_history_coverage", "coin_index"))
    ]
    assert touched == []
    assert table_counts(db_session) == counts


def test_responses_are_never_cached(api: TestClient) -> None:
    response = history(api, "AAPL", range="1M")
    assert response.headers["Cache-Control"] == "no-store"
    assert history(api, "AAPL", range="ALL").headers["Cache-Control"] == "no-store"


def test_no_price_reaches_the_logs(api: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    stock_trade(api, "AAPL", "2026-03-03T15:00:00Z", "2470")
    with caplog.at_level(logging.DEBUG):
        body = history(api, "AAPL", range="1M").json()
    assert body["bars"][0]["close"] == "1234.5678"  # the values were really served...
    for value in PRICE_STRINGS:
        assert value not in caplog.text  # ...and never logged


def test_every_request_fetches_again(api: TestClient, stocks: FakeStocks) -> None:
    first = history(api, "AAPL", range="1M").json()
    second = history(api, "AAPL", range="1M").json()
    assert first["bars"] == second["bars"]
    assert len(stocks.calls) == 2
    third = history(api, "AAPL", range="3M").json()
    assert third["range_start"] == "2025-12-10" and len(stocks.calls) == 3
