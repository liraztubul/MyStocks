"""Batch quotes: the CoinGecko adapter (one /simple/price call) and the cached wrapper.

The response shape follows a keyless probe on 2026-10-07: ids comma-separated, an unknown id is
simply absent from a 200 response, last_updated_at in seconds."""

from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal

import httpx2
import pytest

from app.domain.enums import AssetType
from app.market_data.cache import CachedProvider
from app.market_data.coingecko_provider import MAX_IDS_PER_CALL, CoinGeckoProvider
from app.market_data.provider import (
    AssetMatch,
    CoinRef,
    PriceOnDate,
    ProviderUnavailableError,
    Quote,
    RateLimitedError,
    SymbolNotFoundError,
)

UPDATED = 1791387240  # 2026-10-07 ~13:34 UTC, a probe value


def coingecko(handler) -> CoinGeckoProvider:  # type: ignore[no-untyped-def]
    return CoinGeckoProvider(httpx2.Client(transport=httpx2.MockTransport(handler)))


def test_coingecko_prices_many_coins_in_one_call() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        text = (
            '{"bitcoin": {"usd": 83220, "usd_24h_change": -3.6691332478572978, '
            f'"last_updated_at": {UPDATED}}}, '
            '"ethereum": {"usd": 2565.39, "usd_24h_change": -5.609169155835858, '
            f'"last_updated_at": {UPDATED}}}}}'
        )
        return httpx2.Response(200, text=text, headers={"content-type": "application/json"})

    coins = [CoinRef("bitcoin", "BTC"), CoinRef("ethereum", "ETH"), CoinRef("no-such-coin", "XYZ")]
    quotes = coingecko(handler).get_quotes(coins)
    assert len(seen) == 1
    assert seen[0].url.params["ids"] == "bitcoin,ethereum,no-such-coin"
    # The unknown id is simply absent, as the probe showed.
    assert set(quotes) == {"bitcoin", "ethereum"}
    eth = quotes["ethereum"]
    assert (eth.symbol, eth.price, eth.coin_id) == ("ETH", Decimal("2565.39"), "ethereum")
    assert eth.as_of == datetime.fromtimestamp(UPDATED, tz=UTC)


def test_coingecko_splits_very_long_lists_below_the_documented_limit() -> None:
    calls: list[int] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(len(request.url.params["ids"].split(",")))
        return httpx2.Response(200, json={})

    coingecko(handler).get_quotes([CoinRef(f"c{i}", f"C{i}") for i in range(MAX_IDS_PER_CALL + 1)])
    assert calls == [MAX_IDS_PER_CALL, 1]
    assert MAX_IDS_PER_CALL < 515  # CoinGecko's documented maximum per request


# --- CachedProvider.get_quotes ---------------------------------------------------------------


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class FakeBatch:
    def __init__(self) -> None:
        self.prices = {"bitcoin": Decimal("60000"), "ethereum": Decimal("2500")}
        self.batches: list[list[str]] = []
        self.singles: list[str] = []
        self.error: Exception | None = None

    def _quote(self, coin_id: str, symbol: str) -> Quote:
        return Quote(
            symbol,
            AssetType.CRYPTO,
            self.prices[coin_id],
            "USD",
            datetime(2026, 10, 7, 12, tzinfo=UTC),
            coin_id=coin_id,
        )

    def get_quotes(self, coins: Sequence[CoinRef]) -> dict[str, Quote]:
        self.batches.append([c.coin_id for c in coins])
        if self.error:
            raise self.error
        return {
            c.coin_id: self._quote(c.coin_id, c.symbol) for c in coins if c.coin_id in self.prices
        }

    def search(self, query: str) -> list[AssetMatch]:
        return []

    def get_quote(self, symbol: str, provider_id: str | None = None) -> Quote:
        assert provider_id is not None
        self.singles.append(provider_id)
        if self.error:
            raise self.error
        if provider_id not in self.prices:
            raise SymbolNotFoundError("unknown")
        return self._quote(provider_id, symbol)

    def get_price_on(self, symbol: str, on: date, provider_id: str | None = None) -> PriceOnDate:
        raise NotImplementedError


BTC, ETH, NOPE = CoinRef("bitcoin", "BTC"), CoinRef("ethereum", "ETH"), CoinRef("nope", "NOPE")


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def inner() -> FakeBatch:
    return FakeBatch()


@pytest.fixture
def cached(inner: FakeBatch, clock: Clock) -> CachedProvider:
    return CachedProvider(inner, timer=clock)


def test_one_call_for_all_uncached_coins(cached: CachedProvider, inner: FakeBatch) -> None:
    results = cached.get_quotes([BTC, ETH])
    assert inner.batches == [["bitcoin", "ethereum"]]
    assert results["bitcoin"].price == Decimal("60000")  # type: ignore[union-attr]


def test_cached_coins_are_not_fetched_again(cached: CachedProvider, inner: FakeBatch) -> None:
    cached.get_quotes([BTC])
    cached.get_quotes([BTC, ETH])
    assert inner.batches == [["bitcoin"], ["ethereum"]]
    cached.get_quotes([BTC, ETH])
    assert len(inner.batches) == 2


def test_single_quotes_and_batches_share_one_cache(
    cached: CachedProvider, inner: FakeBatch
) -> None:
    cached.get_quote("BTC", "bitcoin")
    cached.get_quotes([BTC])
    assert inner.batches == []  # served from the single quote's cache entry
    cached.get_quotes([ETH])
    assert cached.get_quote("ETH", "ethereum").price == Decimal("2500")
    assert inner.singles == ["bitcoin"]


def test_provider_failure_falls_back_to_stale_per_coin(
    cached: CachedProvider, inner: FakeBatch, clock: Clock
) -> None:
    first = cached.get_quotes([BTC])["bitcoin"]
    clock.now += 61
    inner.error = ProviderUnavailableError("down")
    results = cached.get_quotes([BTC, ETH])
    stale = results["bitcoin"]
    assert isinstance(stale, Quote) and stale.is_stale
    assert stale.as_of == first.as_of  # type: ignore[union-attr]  # the original fetch time
    # ETH was never fetched: no fallback, so the reason comes back instead of a price.
    assert isinstance(results["ethereum"], ProviderUnavailableError)


def test_rate_limit_also_falls_back(cached: CachedProvider, inner: FakeBatch, clock: Clock) -> None:
    cached.get_quotes([BTC])
    clock.now += 61
    inner.error = RateLimitedError("slow down")
    result = cached.get_quotes([BTC])["bitcoin"]
    assert isinstance(result, Quote) and result.is_stale


def test_unknown_coin_is_reported_not_masked(cached: CachedProvider, inner: FakeBatch) -> None:
    results = cached.get_quotes([BTC, NOPE])
    assert isinstance(results["nope"], SymbolNotFoundError)
    assert isinstance(results["bitcoin"], Quote)


class SingleOnly:
    """A provider that can only price one coin per call."""

    def __init__(self) -> None:
        self.fake = FakeBatch()

    def search(self, query: str) -> list[AssetMatch]:
        return []

    def get_quote(self, symbol: str, provider_id: str | None = None) -> Quote:
        return self.fake.get_quote(symbol, provider_id)

    def get_price_on(self, symbol: str, on: date, provider_id: str | None = None) -> PriceOnDate:
        raise NotImplementedError


def test_provider_without_batching_is_called_per_coin(clock: Clock) -> None:
    inner = SingleOnly()
    results = CachedProvider(inner, timer=clock).get_quotes([BTC, NOPE])
    assert inner.fake.singles == ["bitcoin", "nope"]
    assert isinstance(results["bitcoin"], Quote) and isinstance(
        results["nope"], SymbolNotFoundError
    )
