import logging
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from functools import lru_cache

import httpx2

from app.core.config import settings
from app.domain.enums import AssetType
from app.market_data.cache import CachedProvider
from app.market_data.coingecko_provider import CoinGeckoProvider, KeyCheck
from app.market_data.finnhub_provider import FinnhubProvider
from app.market_data.provider import AssetMatch, MarketDataError, MarketDataProvider


@dataclass(frozen=True)
class SourceFailure:
    asset_type: AssetType
    error: MarketDataError


@dataclass(frozen=True)
class SearchResult:
    matches: list[AssetMatch]
    failures: list[SourceFailure] = field(default_factory=list)


class MarketData:
    """Routes calls to the provider for an asset type, and merges search across all of them."""

    def __init__(self, providers: Mapping[AssetType, MarketDataProvider]) -> None:
        self._providers = providers

    def provider(self, asset_type: AssetType) -> MarketDataProvider:
        return self._providers[asset_type]

    def search(self, query: str, asset_types: Collection[AssetType] | None = None) -> SearchResult:
        sources = {
            t: p for t, p in self._providers.items() if asset_types is None or t in asset_types
        }
        matches: list[AssetMatch] = []
        failures: list[SourceFailure] = []
        for asset_type, provider in sources.items():
            try:
                matches.extend(provider.search(query))
            except MarketDataError as exc:
                failures.append(SourceFailure(asset_type, exc))
        # One source down still yields useful results; only fail outright if every source did.
        if failures and len(failures) == len(sources):
            raise failures[0].error
        return SearchResult(matches=matches, failures=failures)


# Ungated, shared by every user. Routers must never depend on this directly: they take
# app.market_data.access.UserMarketDataDep, which applies the stock-data allowlist before any
# provider or cache is touched (enforced by tests/unit/test_market_data_boundary.py).
@lru_cache
def http_client() -> httpx2.Client:
    return httpx2.Client(timeout=settings.market_data_timeout_seconds)


@lru_cache
def coingecko_provider() -> CoinGeckoProvider:
    # One instance for quotes and history, so they share its coin-resolution cache.
    return CoinGeckoProvider(http_client(), demo_api_key=settings.coingecko_demo_api_key)


@lru_cache
def shared_market_data() -> MarketData:
    return MarketData(
        {
            AssetType.STOCK: CachedProvider(
                FinnhubProvider(settings.finnhub_api_key, http_client())
            ),
            AssetType.CRYPTO: CachedProvider(
                coingecko_provider(), live_ttl=settings.crypto_quote_ttl_seconds
            ),
        }
    )


logger = logging.getLogger(__name__)


def check_coingecko_key() -> None:
    """Logs whether CoinGecko accepts the configured Demo key, never the key itself. Meant for a
    background thread at startup: it must not raise, and a failure only means "couldn't tell"."""
    try:
        provider = coingecko_provider()
        if not provider.has_demo_key:
            logger.info("CoinGecko: no Demo key configured; using the keyless API.")
            return
        result = provider.check_demo_key()
    except Exception:
        logger.warning("CoinGecko: the Demo key check failed unexpectedly; key status unknown.")
        return
    if result is KeyCheck.ACCEPTED:
        logger.info("CoinGecko: Demo key configured and accepted.")
    elif result is KeyCheck.REJECTED:
        logger.warning(
            "CoinGecko: COINGECKO_DEMO_API_KEY is configured but was REJECTED; uncached crypto "
            "requests will fail until it is fixed or removed."
        )
    else:
        logger.warning(
            "CoinGecko: Demo key configured, but CoinGecko couldn't be reached to check it."
        )
