"""The Tiingo adapter against fake transports: header auth, narrowed columns with validation,
our own error wording. The token is a placeholder and every row is synthetic."""

import logging
from datetime import date
from decimal import Decimal
from typing import Any

import httpx2
import pytest

from app.market_data.http import provider_calls
from app.market_data.provider import (
    IncompleteResponseError,
    ProviderUnavailableError,
    RateLimitedError,
    RawStockBar,
    SymbolNotFoundError,
)
from app.market_data.tiingo_provider import TiingoProvider

TOKEN = "tiingo-placeholder-not-a-real-token"
START, END = date(2026, 3, 2), date(2026, 3, 6)


def provider(handler: Any) -> TiingoProvider:
    return TiingoProvider(TOKEN, httpx2.Client(transport=httpx2.MockTransport(handler)))


def rows(*fields: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"date": f"2026-03-0{2 + i}T00:00:00.000Z", **f} for i, f in enumerate(fields)]


def respond(body: Any, status: int = 200, headers: dict[str, str] | None = None) -> Any:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(status, json=body, headers=headers)

    return handler, seen


def test_token_goes_in_a_header_and_columns_are_narrowed() -> None:
    handler, seen = respond(rows({"close": 101.5, "splitFactor": 1.0}))
    provider(handler).fetch_daily("BRK-B", START, END)
    (request,) = seen
    assert request.headers["Authorization"] == f"Token {TOKEN}"
    assert TOKEN not in str(request.url)
    assert request.url.path == "/tiingo/daily/BRK-B/prices"
    assert dict(request.url.params) == {
        "startDate": "2026-03-02",
        "endDate": "2026-03-06",
        "columns": "close,splitFactor",
    }


def test_rows_keep_only_day_close_and_factor_as_decimals() -> None:
    body = rows(
        {"close": 101.5, "splitFactor": 1.0, "adjClose": 99.0, "divCash": 0.25, "volume": 7},
        {"close": 26, "splitFactor": 4},
    )
    handler, _ = respond(body)
    result = provider(handler).fetch_daily("AAPL", START, END, narrow=False)
    assert result == [
        RawStockBar(date(2026, 3, 2), Decimal("101.5"), Decimal("1.0")),
        RawStockBar(date(2026, 3, 3), Decimal(26), Decimal(4)),
    ]
    assert set(RawStockBar.__dataclass_fields__) == {"day", "close", "split_factor"}


def test_full_request_has_no_columns_parameter() -> None:
    handler, seen = respond(rows({"close": 1, "splitFactor": 1}))
    provider(handler).fetch_daily("AAPL", START, END, narrow=False)
    assert "columns" not in seen[0].url.params


def test_ignored_columns_are_an_incomplete_response() -> None:
    handler, _ = respond(rows({"close": 101.5}))  # splitFactor missing
    with pytest.raises(IncompleteResponseError):
        provider(handler).fetch_daily("AAPL", START, END)


@pytest.mark.parametrize(
    "row", [{"close": 101.5}, {"splitFactor": 1}, {"close": "1", "splitFactor": 1}]
)
def test_a_full_response_without_the_needed_fields_is_a_provider_error(
    row: dict[str, Any],
) -> None:
    handler, _ = respond(rows(row))
    with pytest.raises(ProviderUnavailableError) as raised:
        provider(handler).fetch_daily("AAPL", START, END, narrow=False)
    assert not isinstance(raised.value, IncompleteResponseError)


def test_unknown_ticker_is_not_found_in_our_own_words() -> None:
    handler, _ = respond({"detail": "Error: Ticker 'ZZZ' not found"}, status=404)
    with pytest.raises(SymbolNotFoundError) as raised:
        provider(handler).fetch_daily("ZZZ", START, END)
    assert "Error: Ticker" not in raised.value.message


def test_429_is_rate_limited_with_retry_after() -> None:
    handler, _ = respond({"detail": "slow down"}, status=429, headers={"Retry-After": "120"})
    with pytest.raises(RateLimitedError) as raised:
        provider(handler).fetch_daily("AAPL", START, END)
    assert raised.value.retry_after == 120


@pytest.mark.parametrize("status", [401, 403])
def test_a_rejected_token_names_the_setting_not_the_token(status: int) -> None:
    handler, _ = respond({"detail": "Invalid token."}, status=status)
    with pytest.raises(ProviderUnavailableError) as raised:
        provider(handler).fetch_daily("AAPL", START, END)
    assert "TIINGO_API_KEY" in raised.value.message and TOKEN not in raised.value.message


@pytest.mark.parametrize("body", [{"detail": "?"}, [42], [{"close": 1, "splitFactor": 1}]])
def test_unexpected_shapes_are_provider_errors(body: Any) -> None:
    handler, _ = respond(body)
    with pytest.raises(ProviderUnavailableError):
        provider(handler).fetch_daily("AAPL", START, END)


def test_logs_and_usage_counts_carry_no_token_ticker_or_price(
    caplog: pytest.LogCaptureFixture,
) -> None:
    handler, _ = respond(rows({"close": 123.4567, "splitFactor": 1.0}))
    before = provider_calls.snapshot()
    with caplog.at_level(logging.DEBUG):
        provider(handler).fetch_daily("SECRETTICKER", START, END)
    after = provider_calls.snapshot()
    assert {k for k in after if after[k] != before.get(k)} == {
        ("Tiingo", "/tiingo/daily/{ticker}/prices", "ok")
    }
    for text in (TOKEN, "SECRETTICKER", "123.4567"):
        assert text not in caplog.text
