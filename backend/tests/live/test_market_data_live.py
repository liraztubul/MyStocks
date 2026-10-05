"""Real-network checks against Finnhub and CoinGecko. Excluded by default; run with:

    pytest -m live_network

Finnhub tests are skipped unless FINNHUB_API_KEY is set (env or repo-root .env).
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import httpx2
import pytest

from app.core.config import settings
from app.market_data.coingecko_provider import CoinGeckoProvider
from app.market_data.finnhub_provider import FinnhubProvider
from app.market_data.provider import (
    PriceKind,
    PriceUnavailableError,
    ReferenceKind,
    SymbolNotFoundError,
)

pytestmark = pytest.mark.live_network

needs_finnhub_key = pytest.mark.skipif(
    not settings.finnhub_api_key, reason="FINNHUB_API_KEY not set"
)


@pytest.fixture(scope="module")
def client() -> httpx2.Client:
    return httpx2.Client(timeout=10)


@needs_finnhub_key
def test_finnhub_search_finds_apple(client: httpx2.Client) -> None:
    matches = FinnhubProvider(settings.finnhub_api_key, client).search("apple")
    assert "AAPL" in {m.symbol for m in matches}


@needs_finnhub_key
def test_finnhub_quote_is_a_positive_decimal(client: httpx2.Client) -> None:
    quote = FinnhubProvider(settings.finnhub_api_key, client).get_quote("AAPL")
    assert isinstance(quote.price, Decimal) and quote.price > 0


@needs_finnhub_key
def test_finnhub_free_tier_cannot_price_last_month(client: httpx2.Client) -> None:
    last_month = datetime.now(timezone.utc).date() - timedelta(days=30)
    with pytest.raises(PriceUnavailableError, match="paid"):
        FinnhubProvider(settings.finnhub_api_key, client).get_price_on("AAPL", last_month)


def test_coingecko_search_finds_bitcoin(client: httpx2.Client) -> None:
    matches = CoinGeckoProvider(client, settings.coingecko_demo_api_key).search("bitcoin")
    assert ("BTC", "bitcoin") in {(m.symbol, m.provider_id) for m in matches}


def test_coingecko_historical_close_within_a_year(client: httpx2.Client) -> None:
    provider = CoinGeckoProvider(client, settings.coingecko_demo_api_key)
    result = provider.get_price_on("BTC", date.today() - timedelta(days=30), "bitcoin")
    assert result.kind is PriceKind.CLOSE and result.price > 0


def test_coingecko_refuses_older_than_a_year(client: httpx2.Client) -> None:
    provider = CoinGeckoProvider(client, settings.coingecko_demo_api_key)
    with pytest.raises(PriceUnavailableError):
        provider.get_price_on("BTC", date.today() - timedelta(days=400), "bitcoin")


@needs_finnhub_key
def test_finnhub_quote_has_a_previous_close_reference(client: httpx2.Client) -> None:
    quote = FinnhubProvider(settings.finnhub_api_key, client).get_quote("AAPL")
    assert quote.reference_kind is ReferenceKind.PREVIOUS_CLOSE
    assert quote.reference_price is not None and quote.reference_price > 0
    assert quote.reference_at is not None and quote.reference_at <= quote.as_of


@needs_finnhub_key
def test_finnhub_unknown_symbol_is_not_found(client: httpx2.Client) -> None:
    with pytest.raises(SymbolNotFoundError):
        FinnhubProvider(settings.finnhub_api_key, client).get_quote("ZZZZQ")


def test_coingecko_quote_has_a_rolling_24h_reference(client: httpx2.Client) -> None:
    quote = CoinGeckoProvider(client, settings.coingecko_demo_api_key).get_quote("BTC", "bitcoin")
    assert quote.reference_kind is ReferenceKind.ROLLING_24H
    assert quote.reference_price is not None and quote.reference_price > 0
