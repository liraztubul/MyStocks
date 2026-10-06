"""CoinGecko daily history. Response shapes follow the M6a Stage 2 probe (keyless API, 2026-10-06):
points at 00:00 UTC with interval=daily, prices as JSON numbers, 10012 beyond 365 days, 404
{"error": "coin not found"}, 429 {"status": {"error_code": 429, ...}}. Bodies here are built to
that shape; 86489.73482686514 is a price the probe actually received."""

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx2
import pytest

from app.market_data.coingecko_provider import CoinGeckoProvider
from app.market_data.history import round_close
from app.market_data.provider import PriceUnavailableError, RateLimitedError, SymbolNotFoundError

NOW = datetime(2026, 10, 6, 13, 37, tzinfo=UTC)
Handler = Callable[[httpx2.Request], httpx2.Response]


def midnight_ms(day: date) -> int:
    return int(datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp() * 1000)


def provider(handler: Handler, now: datetime = NOW) -> CoinGeckoProvider:
    return CoinGeckoProvider(
        httpx2.Client(transport=httpx2.MockTransport(handler)), now=lambda: now
    )


def respond(text: str, status: int = 200, seen: list[httpx2.Request] | None = None) -> Handler:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if seen is not None:
            seen.append(request)
        return httpx2.Response(status, text=text, headers={"content-type": "application/json"})

    return handler


def prices_body(points: list[tuple[int, str]]) -> str:
    # Raw numbers, as CoinGecko sends them, so the Decimal parsing path is exercised.
    return '{"prices": [' + ", ".join(f"[{ms}, {price}]" for ms, price in points) + "]}"


def test_requests_daily_points_for_the_next_days_snapshots() -> None:
    seen: list[httpx2.Request] = []
    provider(respond(prices_body([]), seen=seen)).get_daily_closes(
        "bitcoin", date(2026, 9, 1), date(2026, 9, 30)
    )
    params = seen[0].url.params
    assert seen[0].url.path.endswith("/coins/bitcoin/market_chart/range")
    assert params["interval"] == "daily"
    assert params["vs_currency"] == "usd"
    # The close of Sep 1 is the Sep 2 00:00 snapshot; the close of Sep 30 is Oct 1 00:00.
    assert int(params["from"]) * 1000 == midnight_ms(date(2026, 9, 2))
    assert int(params["to"]) * 1000 == midnight_ms(date(2026, 10, 1))


def test_midnight_point_is_the_previous_days_close_and_others_are_dropped() -> None:
    body = prices_body(
        [
            (midnight_ms(date(2026, 10, 5)), "86489.73482686514"),
            (midnight_ms(date(2026, 10, 6)), "86500.5"),
            # An in-progress "now" point: not a close.
            (midnight_ms(date(2026, 10, 6)) + 13 * 3_600_000, "86999.9"),
        ]
    )
    bars = provider(respond(body)).get_daily_closes("bitcoin", date(2026, 10, 4), date(2026, 10, 5))
    assert [(b.day, b.close) for b in bars] == [
        (date(2026, 10, 4), Decimal("86489.734826865140000000")),
        (date(2026, 10, 5), Decimal("86500.500000000000000000")),
    ]


def test_null_prices_are_skipped() -> None:
    body = '{"prices": [[' + str(midnight_ms(date(2026, 10, 2))) + ", null]]}"
    assert provider(respond(body)).get_daily_closes("x", date(2026, 10, 1), date(2026, 10, 1)) == []


@pytest.mark.parametrize(
    ("raw", "stored"),
    [
        # A micro-priced coin keeps its significant digits at 18 places.
        ("0.0000043612345678901234565", "0.000004361234567890"),
        # Half-even at the 18th place: ties go to the even digit.
        ("1.0000000000000000005", "1.000000000000000000"),
        ("1.0000000000000000015", "1.000000000000000002"),
        ("123456789012345678.123456789", "123456789012345678.123456789000000000"),
    ],
)
def test_closes_are_rounded_half_even_to_18_places(raw: str, stored: str) -> None:
    assert round_close(Decimal(raw)) == Decimal(stored)
    assert str(round_close(Decimal(raw))) == stored


def test_range_is_clamped_to_the_free_365_days_without_failing() -> None:
    seen: list[httpx2.Request] = []
    p = provider(respond(prices_body([]), seen=seen))
    earliest = p.earliest_available(NOW)
    assert earliest == date(2025, 10, 6)  # oldest snapshot 364 days back = close of 365 days ago
    p.get_daily_closes("bitcoin", date(2024, 1, 1), date(2026, 10, 5))
    assert int(seen[0].url.params["from"]) * 1000 == midnight_ms(earliest + timedelta(days=1))


def test_a_range_entirely_too_old_makes_no_call() -> None:
    def fail(_request: httpx2.Request) -> httpx2.Response:
        raise AssertionError("no request expected")

    assert provider(fail).get_daily_closes("bitcoin", date(2024, 1, 1), date(2024, 2, 1)) == []


def test_last_final_date_is_yesterday_utc() -> None:
    p = provider(respond("{}"))
    assert p.last_final_date(NOW) == date(2026, 10, 5)
    assert p.last_final_date(datetime(2026, 10, 6, 0, 0, 1, tzinfo=UTC)) == date(2026, 10, 5)


def test_error_10012_maps_to_price_unavailable() -> None:
    body = (
        '{"error": {"status": {"error_code": 10012, "error_message": "Your request exceeds the '
        "allowed time range. Public API users are limited to querying historical data within "
        'the past 365 days."}}}'
    )
    with pytest.raises(PriceUnavailableError):
        provider(respond(body, status=401)).get_daily_closes(
            "bitcoin", date(2026, 1, 1), date(2026, 1, 2)
        )


def test_unknown_coin_is_not_found() -> None:
    with pytest.raises(SymbolNotFoundError):
        provider(respond('{"error": "coin not found"}', status=404)).get_daily_closes(
            "nope", date(2026, 9, 1), date(2026, 9, 2)
        )


def test_rate_limit_is_reported_as_such() -> None:
    body = '{"status": {"error_code": 429, "error_message": "You\'ve exceeded the Rate Limit."}}'
    with pytest.raises(RateLimitedError):
        provider(respond(body, status=429)).get_daily_closes(
            "bitcoin", date(2026, 9, 1), date(2026, 9, 2)
        )
