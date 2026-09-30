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
