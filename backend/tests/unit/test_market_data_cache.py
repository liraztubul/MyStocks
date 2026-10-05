from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.domain.enums import AssetType
from app.market_data.cache import CachedProvider
from app.market_data.provider import (
    AssetMatch,
    PriceKind,
    PriceOnDate,
    ProviderUnavailableError,
    Quote,
    RateLimitedError,
    SymbolNotFoundError,
)

DAY = date(2026, 3, 13)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeProvider:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.price = Decimal("100")
        self.kind = PriceKind.CLOSE
        self.fail = False

    def _record(self, name: str) -> None:
        self.calls.append(name)
        if self.fail:
            raise ProviderUnavailableError("down")

    def search(self, query: str) -> list[AssetMatch]:
        self._record("search")
        return [AssetMatch(query.upper(), "Fake Inc", AssetType.STOCK, query.upper())]

    def get_quote(self, symbol: str, provider_id: str | None = None) -> Quote:
        self._record("quote")
        return Quote(symbol, AssetType.STOCK, self.price, "USD", datetime.now(timezone.utc))

    def get_price_on(self, symbol: str, on: date, provider_id: str | None = None) -> PriceOnDate:
        self._record("price_on")
        return PriceOnDate(symbol, AssetType.STOCK, self.price, "USD", on, on, self.kind)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def inner() -> FakeProvider:
    return FakeProvider()


@pytest.fixture
def cached(inner: FakeProvider, clock: FakeClock) -> CachedProvider:
    return CachedProvider(inner, live_ttl=60, search_ttl=3600, timer=clock)


def test_quote_is_served_from_cache_within_ttl(
    cached: CachedProvider, inner: FakeProvider, clock: FakeClock
) -> None:
    cached.get_quote("AAPL")
    clock.advance(59)
    cached.get_quote("aapl")
    assert inner.calls == ["quote"]


def test_quote_is_refetched_after_ttl(
    cached: CachedProvider, inner: FakeProvider, clock: FakeClock
) -> None:
    cached.get_quote("AAPL")
    clock.advance(61)
    inner.price = Decimal("101")
    assert cached.get_quote("AAPL").price == Decimal("101")
    assert inner.calls == ["quote", "quote"]


def test_final_close_is_cached_permanently(
    cached: CachedProvider, inner: FakeProvider, clock: FakeClock
) -> None:
    cached.get_price_on("AAPL", DAY)
    clock.advance(10 * 365 * 24 * 3600)
    cached.get_price_on("AAPL", DAY)
    assert inner.calls == ["price_on"]


def test_live_price_on_uses_the_short_ttl(
    cached: CachedProvider, inner: FakeProvider, clock: FakeClock
) -> None:
    inner.kind = PriceKind.LIVE
    cached.get_price_on("AAPL", DAY)
    clock.advance(30)
    cached.get_price_on("AAPL", DAY)
    assert inner.calls == ["price_on"]
    clock.advance(31)
    cached.get_price_on("AAPL", DAY)
    assert inner.calls == ["price_on", "price_on"]


def test_price_on_is_keyed_by_date_and_provider_id(
    cached: CachedProvider, inner: FakeProvider
) -> None:
    cached.get_price_on("AAPL", DAY)
    cached.get_price_on("AAPL", date(2026, 3, 12))
    cached.get_price_on("AAPL", DAY, provider_id="other")
    assert inner.calls == ["price_on"] * 3


def test_search_has_its_own_longer_ttl(
    cached: CachedProvider, inner: FakeProvider, clock: FakeClock
) -> None:
    cached.search("app")
    clock.advance(3599)
    cached.search(" APP ")
    assert inner.calls == ["search"]
    clock.advance(2)
    cached.search("app")
    assert inner.calls == ["search", "search"]


def test_errors_are_not_cached(cached: CachedProvider, inner: FakeProvider) -> None:
    inner.fail = True
    with pytest.raises(ProviderUnavailableError):
        cached.get_quote("AAPL")
    inner.fail = False
    assert cached.get_quote("AAPL").price == Decimal("100")
    assert inner.calls == ["quote", "quote"]


class FlakyQuotes(FakeProvider):
    """Quotes whose next fetch can be made to fail with a chosen error."""

    def __init__(self) -> None:
        super().__init__()
        self.error: Exception | None = None
        self.fetched_at = datetime(2026, 3, 13, 20, 0, tzinfo=timezone.utc)

    def get_quote(self, symbol: str, provider_id: str | None = None) -> Quote:
        self.calls.append("quote")
        if self.error:
            raise self.error
        return Quote(symbol, AssetType.STOCK, self.price, "USD", self.fetched_at)


@pytest.fixture
def flaky() -> FlakyQuotes:
    return FlakyQuotes()


@pytest.fixture
def cached_flaky(flaky: FlakyQuotes, clock: FakeClock) -> CachedProvider:
    return CachedProvider(flaky, live_ttl=60, timer=clock)


def test_fresh_quote_is_not_stale(cached_flaky: CachedProvider) -> None:
    assert cached_flaky.get_quote("AAPL").is_stale is False


@pytest.mark.parametrize(
    "error", [ProviderUnavailableError("down"), RateLimitedError("slow down", retry_after=30)]
)
def test_failed_fetch_serves_last_known_good_marked_stale(
    cached_flaky: CachedProvider, flaky: FlakyQuotes, clock: FakeClock, error: Exception
) -> None:
    original = cached_flaky.get_quote("AAPL")
    clock.advance(61)
    flaky.error = error
    flaky.price = Decimal("999")

    stale = cached_flaky.get_quote("AAPL")
    assert stale.is_stale is True
    assert (stale.price, stale.as_of) == (original.price, original.as_of)


def test_never_fetched_symbol_still_raises(
    cached_flaky: CachedProvider, flaky: FlakyQuotes
) -> None:
    flaky.error = ProviderUnavailableError("down")
    with pytest.raises(ProviderUnavailableError):
        cached_flaky.get_quote("AAPL")


def test_symbol_not_found_is_never_masked_by_a_stale_quote(
    cached_flaky: CachedProvider, flaky: FlakyQuotes, clock: FakeClock
) -> None:
    cached_flaky.get_quote("AAPL")
    clock.advance(61)
    flaky.error = SymbolNotFoundError("delisted")
    with pytest.raises(SymbolNotFoundError):
        cached_flaky.get_quote("AAPL")


def test_stale_answer_is_held_for_one_ttl_then_the_provider_is_retried(
    cached_flaky: CachedProvider, flaky: FlakyQuotes, clock: FakeClock
) -> None:
    cached_flaky.get_quote("AAPL")
    clock.advance(61)
    flaky.error = ProviderUnavailableError("down")
    cached_flaky.get_quote("AAPL")
    clock.advance(30)
    assert cached_flaky.get_quote("AAPL").is_stale
    assert flaky.calls == ["quote", "quote"]

    clock.advance(31)
    flaky.error = None
    flaky.price = Decimal("105")
    flaky.fetched_at = datetime(2026, 3, 16, 14, 0, tzinfo=timezone.utc)
    recovered = cached_flaky.get_quote("AAPL")
    assert (recovered.is_stale, recovered.price) == (False, Decimal("105"))
    assert flaky.calls == ["quote", "quote", "quote"]


def test_a_stale_copy_never_replaces_the_last_known_good(
    cached_flaky: CachedProvider, flaky: FlakyQuotes, clock: FakeClock
) -> None:
    first = cached_flaky.get_quote("AAPL")
    flaky.error = ProviderUnavailableError("down")
    for _ in range(3):
        clock.advance(61)
        assert cached_flaky.get_quote("AAPL").as_of == first.as_of
