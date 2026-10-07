import threading
import time
from collections.abc import Callable, Hashable, MutableMapping, Sequence
from dataclasses import replace
from datetime import date
from typing import Any, TypeVar, cast

from cachetools import LRUCache, TTLCache

from app.market_data.provider import (
    AssetMatch,
    BatchQuoteProvider,
    CoinRef,
    MarketDataError,
    MarketDataProvider,
    PriceKind,
    PriceOnDate,
    ProviderUnavailableError,
    Quote,
    RateLimitedError,
    SymbolNotFoundError,
)

LIVE_TTL_SECONDS = 60
SEARCH_TTL_SECONDS = 60 * 60

T = TypeVar("T")
Cache = MutableMapping[Hashable, Any]


class CachedProvider:
    """Wraps a provider with two tiers: short-TTL for anything live, and a size-bounded
    no-expiry cache for final historical closes, which never change once published.

    Live quotes also keep a last-known-good copy. If a fetch fails because the provider is
    down or rate-limited, that copy is returned marked stale (with its original timestamp)
    instead of an error. A "symbol not found" is never masked this way. Errors themselves are
    never cached, so an outage with no fallback doesn't linger after the provider recovers.
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
        # Every symbol's most recent successful quote, never expired: the fallback when a live
        # fetch fails transiently. Size-bounded like the final tier.
        self._last_good: Cache = LRUCache(4096)
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
        key = ("quote", symbol.upper(), provider_id)
        with self._lock:
            if key in self._live:
                return cast(Quote, self._live[key])
        try:
            quote = self._inner.get_quote(symbol, provider_id)
        except (ProviderUnavailableError, RateLimitedError):
            with self._lock:
                last_good = self._last_good.get(key)
            if last_good is None:
                raise
            stale = replace(last_good, is_stale=True)
            # Parking the stale copy for one live TTL means a provider outage costs one timed-out
            # call per symbol per minute, not one per request; it's retried when this expires.
            with self._lock:
                self._live[key] = stale
            return stale
        with self._lock:
            self._live[key] = quote
            self._last_good[key] = quote
        return quote

    def get_quotes(self, coins: Sequence[CoinRef]) -> dict[str, Quote | MarketDataError]:
        """A quote, or the reason there is none, per coin id: one provider call for every coin
        not already cached, with the same per-coin stale fallback as get_quote."""
        results: dict[str, Quote | MarketDataError] = {}
        missing: list[CoinRef] = []
        # Same keys as get_quote, so a single quote and a batch share one cache.
        key = {c.coin_id: ("quote", c.symbol.upper(), c.coin_id) for c in coins}
        with self._lock:
            for coin in coins:
                if key[coin.coin_id] in self._live:
                    results[coin.coin_id] = cast(Quote, self._live[key[coin.coin_id]])
                else:
                    missing.append(coin)
        if not missing:
            return results
        try:
            fetched = self._fetch_batch(missing)
        except (ProviderUnavailableError, RateLimitedError) as exc:
            with self._lock:
                for coin in missing:
                    last_good = self._last_good.get(key[coin.coin_id])
                    if last_good is None:
                        results[coin.coin_id] = exc
                    else:
                        stale = replace(last_good, is_stale=True)
                        self._live[key[coin.coin_id]] = stale
                        results[coin.coin_id] = stale
            return results
        with self._lock:
            for coin in missing:
                quote = fetched.get(coin.coin_id)
                if quote is None:
                    # Unknown to the provider: never masked with an old price.
                    results[coin.coin_id] = SymbolNotFoundError(
                        f"No USD price for {coin.symbol.upper()} on this provider."
                    )
                    continue
                self._live[key[coin.coin_id]] = quote
                self._last_good[key[coin.coin_id]] = quote
                results[coin.coin_id] = quote
        return results

    def _fetch_batch(self, coins: list[CoinRef]) -> dict[str, Quote]:
        if hasattr(self._inner, "get_quotes"):
            return cast(BatchQuoteProvider, self._inner).get_quotes(coins)
        # A provider without batching: one call per coin (not used by any crypto provider today).
        quotes = {}
        for coin in coins:
            try:
                quotes[coin.coin_id] = self._inner.get_quote(coin.symbol, coin.coin_id)
            except SymbolNotFoundError:
                continue
        return quotes

    def get_price_on(self, symbol: str, on: date, provider_id: str | None = None) -> PriceOnDate:
        return self._get_or_fetch(
            ("price_on", symbol.upper(), provider_id, on),
            lambda: self._inner.get_price_on(symbol, on, provider_id),
            (self._final, self._live),
            lambda result: self._final if result.kind is PriceKind.CLOSE else self._live,
        )
