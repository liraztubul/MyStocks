import threading
import time
from collections.abc import Callable, Hashable, MutableMapping
from datetime import date
from typing import Any, TypeVar, cast

from cachetools import LRUCache, TTLCache

from app.market_data.provider import (
    AssetMatch,
    MarketDataProvider,
    PriceKind,
    PriceOnDate,
    Quote,
)

LIVE_TTL_SECONDS = 60
SEARCH_TTL_SECONDS = 60 * 60

T = TypeVar("T")
Cache = MutableMapping[Hashable, Any]


class CachedProvider:
    """Wraps a provider with two tiers: short-TTL for anything live, and a size-bounded
    no-expiry cache for final historical closes, which never change once published.

    Errors are never cached, so a provider outage doesn't linger after it recovers.
    """

    def __init__(
        self,
        inner: MarketDataProvider,
        *,
        live_ttl: float = LIVE_TTL_SECONDS,
        search_ttl: float = SEARCH_TTL_SECONDS,
        timer: Callable[[], float] = time.monotonic,
    ) -> None:
        self._inner = inner
        self._live: Cache = TTLCache(4096, ttl=live_ttl, timer=timer)
        self._search: Cache = TTLCache(1024, ttl=search_ttl, timer=timer)
        self._final: Cache = LRUCache(50_000)
        # cachetools caches aren't thread-safe, and sync FastAPI routes run in a threadpool.
        # The lock covers cache access only, never the network call.
        self._lock = threading.Lock()

    def _get_or_fetch(
        self,
        key: Hashable,
        fetch: Callable[[], T],
        read_from: tuple[Cache, ...],
        store_in: Callable[[T], Cache],
    ) -> T:
        with self._lock:
            for cache in read_from:
                if key in cache:
                    return cast(T, cache[key])
        value = fetch()
        with self._lock:
            store_in(value)[key] = value
        return value

    def search(self, query: str) -> list[AssetMatch]:
        return self._get_or_fetch(
            query.strip().lower(),
            lambda: self._inner.search(query),
            (self._search,),
            lambda _: self._search,
        )

    def get_quote(self, symbol: str, provider_id: str | None = None) -> Quote:
        return self._get_or_fetch(
            ("quote", symbol.upper(), provider_id),
            lambda: self._inner.get_quote(symbol, provider_id),
            (self._live,),
            lambda _: self._live,
        )

    def get_price_on(self, symbol: str, on: date, provider_id: str | None = None) -> PriceOnDate:
        return self._get_or_fetch(
            ("price_on", symbol.upper(), provider_id, on),
            lambda: self._inner.get_price_on(symbol, on, provider_id),
            (self._final, self._live),
            lambda result: self._final if result.kind is PriceKind.CLOSE else self._live,
        )
