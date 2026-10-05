from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import httpx2
import pytest

from app.domain.precision import exact
from app.market_data.coingecko_provider import CoinGeckoProvider
from app.market_data.dates import US_MARKET_TZ
from app.market_data.finnhub_provider import FinnhubProvider
from app.market_data.provider import (
    PriceKind,
    PriceUnavailableError,
    ProviderUnavailableError,
    RateLimitedError,
    ReferenceKind,
    SymbolNotFoundError,
)

Handler = Callable[[httpx2.Request], httpx2.Response]

FRIDAY_CLOSE_TS = int(datetime(2026, 3, 13, 16, 0, tzinfo=US_MARKET_TZ).timestamp())
SATURDAY = datetime(2026, 3, 14, 15, 0, tzinfo=timezone.utc)


def client_for(handler: Handler) -> httpx2.Client:
    return httpx2.Client(transport=httpx2.MockTransport(handler))


def raw_json(text: str, status: int = 200) -> Handler:
    # Raw text rather than json= so float literals reach the parser exactly as a server sends them.
    return lambda _req: httpx2.Response(
        status, text=text, headers={"content-type": "application/json"}
    )


def finnhub(handler: Handler, now: datetime = SATURDAY) -> FinnhubProvider:
    return FinnhubProvider("test-key", client_for(handler), now=lambda: now)


def coingecko(handler: Handler, now: datetime = SATURDAY) -> CoinGeckoProvider:
    return CoinGeckoProvider(client_for(handler), now=lambda: now)


# --- Finnhub ---


def test_finnhub_sends_key_as_header_not_query() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json={"count": 0, "result": []})

    finnhub(handler).search("apple")
    assert seen[0].headers["X-Finnhub-Token"] == "test-key"
    assert "token" not in seen[0].url.params
    assert seen[0].url.params["exchange"] == "US"


def test_finnhub_quote_price_is_exact_decimal() -> None:
    body = f'{{"c": 212.345678912345, "t": {FRIDAY_CLOSE_TS}, "pc": 210.1}}'
    quote = finnhub(raw_json(body)).get_quote("aapl")
    assert quote.price == Decimal("212.345678912345")
    assert quote.symbol == "AAPL"


def test_finnhub_unknown_symbol_zero_quote_is_not_found() -> None:
    with pytest.raises(SymbolNotFoundError):
        finnhub(raw_json('{"c": 0, "d": null, "dp": null, "t": 0}')).get_quote("NOPE")


def test_finnhub_weekend_price_on_falls_back_to_friday_close() -> None:
    body = f'{{"c": 211.5, "t": {FRIDAY_CLOSE_TS}}}'
    result = finnhub(raw_json(body)).get_price_on("AAPL", date(2026, 3, 14))
    assert (result.price, result.price_date, result.kind) == (
        Decimal("211.5"),
        date(2026, 3, 13),
        PriceKind.CLOSE,
    )
    assert result.is_fallback
    assert result.note is not None and "wasn't a trading day" in result.note


def test_finnhub_older_date_explains_paid_plan_requirement() -> None:
    body = f'{{"c": 211.5, "t": {FRIDAY_CLOSE_TS}}}'
    with pytest.raises(PriceUnavailableError, match="paid market-data plan"):
        finnhub(raw_json(body)).get_price_on("AAPL", date(2026, 3, 2))


def test_finnhub_future_date_is_rejected() -> None:
    with pytest.raises(PriceUnavailableError, match="future"):
        finnhub(raw_json("{}")).get_price_on("AAPL", date(2026, 3, 20))


def test_finnhub_missing_key_is_reported_not_crashed() -> None:
    provider = FinnhubProvider(None, client_for(raw_json("{}")))
    with pytest.raises(ProviderUnavailableError, match="FINNHUB_API_KEY"):
        provider.search("apple")


def test_finnhub_rejected_key_is_provider_unavailable() -> None:
    with pytest.raises(ProviderUnavailableError, match="rejected"):
        finnhub(raw_json('{"error": "Invalid API key"}', status=401)).get_quote("AAPL")


def test_rate_limit_is_reported_with_retry_after() -> None:
    def handler(_req: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(429, json={"error": "limit"}, headers={"Retry-After": "30"})

    with pytest.raises(RateLimitedError) as exc:
        finnhub(handler).get_quote("AAPL")
    assert exc.value.retry_after == 30


def test_network_failure_is_provider_unavailable() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("boom", request=request)

    with pytest.raises(ProviderUnavailableError, match="unreachable"):
        finnhub(handler).get_quote("AAPL")


def test_server_error_is_provider_unavailable() -> None:
    with pytest.raises(ProviderUnavailableError):
        finnhub(raw_json("<html>bad gateway</html>", status=502)).get_quote("AAPL")


# --- CoinGecko ---

SEARCH_BODY = """{"coins": [
  {"id": "bitcoin", "name": "Bitcoin", "symbol": "BTC", "market_cap_rank": 1},
  {"id": "bitcoin-cash", "name": "Bitcoin Cash", "symbol": "BCH", "market_cap_rank": 20}
]}"""


def test_coingecko_search_tags_crypto_with_coin_id() -> None:
    matches = coingecko(raw_json(SEARCH_BODY)).search("bitcoin")
    assert [(m.symbol, m.provider_id, m.asset_type.value) for m in matches] == [
        ("BTC", "bitcoin", "crypto"),
        ("BCH", "bitcoin-cash", "crypto"),
    ]


def test_coingecko_close_uses_next_days_snapshot() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(
            200,
            text='{"market_data": {"current_price": {"usd": 71149.2823885419}}}',
            headers={"content-type": "application/json"},
        )

    result = coingecko(handler).get_price_on("BTC", date(2026, 3, 10), provider_id="bitcoin")
    assert seen[0].url.path.endswith("/coins/bitcoin/history")
    assert seen[0].url.params["date"] == "11-03-2026"
    assert result.price == Decimal("71149.2823885419")
    assert (result.price_date, result.kind, result.is_fallback) == (
        date(2026, 3, 10),
        PriceKind.CLOSE,
        False,
    )


def test_coingecko_resolves_symbol_to_top_ranked_exact_match() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path.endswith("/search"):
            return raw_json(SEARCH_BODY)(request)
        return httpx2.Response(200, json={"bitcoin": {"usd": 83552, "last_updated_at": 1}})

    assert coingecko(handler).get_quote("btc").price == Decimal(83552)


def test_coingecko_today_is_a_live_price() -> None:
    body = '{"bitcoin": {"usd": 83552.5, "last_updated_at": 1790778750}}'
    result = coingecko(raw_json(body)).get_price_on("BTC", SATURDAY.date(), provider_id="bitcoin")
    assert (result.kind, result.price) == (PriceKind.LIVE, Decimal("83552.5"))


def test_coingecko_older_than_a_year_is_refused_without_calling() -> None:
    calls: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(request)
        return httpx2.Response(200, json={})

    with pytest.raises(PriceUnavailableError, match="older than 1 year"):
        coingecko(handler).get_price_on("BTC", date(2025, 1, 1), provider_id="bitcoin")
    assert calls == []


def test_coingecko_range_error_401_is_not_mistaken_for_bad_key() -> None:
    # Observed live: CoinGecko reports the free 365-day limit as HTTP 401 + error_code 10012.
    body = '{"error": {"status": {"error_code": 10012, "error_message": "exceeds range"}}}'
    with pytest.raises(PriceUnavailableError, match="older than 1 year"):
        coingecko(raw_json(body, status=401)).get_price_on(
            "BTC", date(2026, 3, 10), provider_id="bitcoin"
        )


def test_coingecko_unknown_coin_is_not_found() -> None:
    body = '{"status": {"error_code": 10013, "error_message": "coin not found"}}'
    with pytest.raises(SymbolNotFoundError):
        coingecko(raw_json(body, status=404)).get_price_on(
            "ZZZ", date(2026, 3, 10), provider_id="zzz"
        )


def test_coingecko_unknown_id_on_simple_price_is_not_found() -> None:
    with pytest.raises(SymbolNotFoundError):
        coingecko(raw_json("{}")).get_quote("ZZZ", provider_id="zzz")


# --- daily-change reference fields ---


def test_finnhub_quote_carries_previous_close_as_reference() -> None:
    body = f'{{"c": 333.77, "d": 0.08, "dp": 0.024, "pc": 333.69, "t": {FRIDAY_CLOSE_TS}}}'
    quote = finnhub(raw_json(body)).get_quote("AAPL")
    assert quote.reference_price == Decimal("333.69")
    assert quote.reference_kind is ReferenceKind.PREVIOUS_CLOSE
    # Session of Friday 2026-03-13 starts at 00:00 New York (EDT) = 04:00 UTC.
    assert quote.reference_at == datetime(2026, 3, 13, 4, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("pc", ["0", "null"])
def test_finnhub_zero_or_missing_previous_close_gives_no_reference(pc: str) -> None:
    body = f'{{"c": 50.5, "pc": {pc}, "t": {FRIDAY_CLOSE_TS}}}'
    quote = finnhub(raw_json(body)).get_quote("NEWIPO")
    assert (quote.reference_price, quote.reference_at, quote.reference_kind) == (None, None, None)


def test_finnhub_zeroed_unknown_symbol_never_becomes_a_quote() -> None:
    # Observed live shape for unknown tickers: everything zero/null. No quote means no
    # reference, so it can't turn into a bogus daily change.
    body = '{"c": 0, "d": null, "dp": null, "h": 0, "l": 0, "o": 0, "pc": 0, "t": 0}'
    with pytest.raises(SymbolNotFoundError):
        finnhub(raw_json(body)).get_quote("ZZZZQ")


def test_coingecko_quote_derives_rolling_24h_reference_from_percentage() -> None:
    body = '{"bitcoin": {"usd": 110, "usd_24h_change": 10, "last_updated_at": 1790778750}}'
    quote = coingecko(raw_json(body)).get_quote("BTC", provider_id="bitcoin")
    assert quote.reference_price == Decimal("100")
    assert quote.reference_kind is ReferenceKind.ROLLING_24H
    assert quote.as_of - quote.reference_at == timedelta(hours=24)  # type: ignore[operator]


def test_coingecko_keeps_the_percentage_exact() -> None:
    body = '{"bitcoin": {"usd": 85222.53, "usd_24h_change": -0.09656965521299134}}'
    quote = coingecko(raw_json(body)).get_quote("BTC", provider_id="bitcoin")
    assert quote.reference_price is not None
    # Re-applying the exact percentage reproduces the price.
    with exact():
        assert quote.reference_price * (1 + Decimal("-0.09656965521299134") / 100) == Decimal(
            "85222.53"
        )


def test_coingecko_null_change_gives_no_reference() -> None:
    body = '{"bitcoin": {"usd": 85222.53, "usd_24h_change": null}}'
    quote = coingecko(raw_json(body)).get_quote("BTC", provider_id="bitcoin")
    assert (quote.reference_price, quote.reference_kind) == (None, None)
