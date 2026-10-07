"""The only way endpoints get market data: per user, with the stock-data allowlist applied.

Free stock data plans (Finnhub quotes, Tiingo history) are licensed for personal use, so stock
market data is shown only to emails in STOCK_DATA_ALLOWED_EMAILS. Crypto is not gated.

The gate sits in front of the providers and their caches, so a blocked user never reaches a
cached value fetched for an allowed one (including the stale last-known-good copy).

Error convention for "not available on this deployment" (code `not_available_on_deployment`):
- Actions (a quote or price-on-date lookup the user asked for): 403 with the code in the body.
- Views that summarise data (holdings, summary, history): 200, with the price fields null and
  the code or an `available: false` flag, because a licensing limit is a fact about the
  deployment, not a failure.
"""

from collections.abc import Sequence
from datetime import date, datetime
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.emails import normalize_email
from app.core.security import CurrentUser
from app.domain.enums import AssetType
from app.market_data.price_history import HistoryResult, PriceHistoryService, shared_price_history
from app.market_data.provider import (
    AssetMatch,
    CoinRef,
    MarketDataError,
    MarketDataProvider,
    PriceOnDate,
    Quote,
)
from app.market_data.service import MarketData, SearchResult, SourceFailure, shared_market_data

STOCK_DATA_NOT_AVAILABLE = "Stock prices aren't available on this deployment."


class StockDataNotAvailableError(MarketDataError):
    code = "not_available_on_deployment"

    def __init__(self) -> None:
        super().__init__(STOCK_DATA_NOT_AVAILABLE)


def stock_data_allowed(email: str) -> bool:
    allowlist = settings.stock_data_allowlist
    if not allowlist:
        # Nothing configured: open in development, closed in production (as the invite code).
        return not settings.is_production
    return normalize_email(email) in allowlist


class _StocksNotAvailable:
    """Stands in for the stock provider for a blocked user; never touches the network or cache."""

    def search(self, query: str) -> list[AssetMatch]:
        raise StockDataNotAvailableError()

    def get_quote(self, symbol: str, provider_id: str | None = None) -> Quote:
        raise StockDataNotAvailableError()

    def get_price_on(self, symbol: str, on: date, provider_id: str | None = None) -> PriceOnDate:
        raise StockDataNotAvailableError()


class UserMarketData:
    def __init__(self, shared: MarketData, *, stock_data_available: bool) -> None:
        self._shared = shared
        self.stock_data_available = stock_data_available

    def provider(self, asset_type: AssetType) -> MarketDataProvider:
        if asset_type is AssetType.STOCK and not self.stock_data_available:
            return _StocksNotAvailable()
        return self._shared.provider(asset_type)

    def get_quotes(
        self, asset_type: AssetType, coins: Sequence[CoinRef]
    ) -> dict[str, Quote | MarketDataError]:
        """Batch quotes, keyed by provider id, each a quote or the reason there is none."""
        if asset_type is AssetType.STOCK and not self.stock_data_available:
            # Before any provider or cache is touched, like single quotes.
            raise StockDataNotAvailableError()
        provider = self._shared.provider(asset_type)
        if hasattr(provider, "get_quotes"):
            return provider.get_quotes(coins)  # type: ignore[no-any-return]
        results: dict[str, Quote | MarketDataError] = {}
        for coin in coins:
            try:
                results[coin.coin_id] = provider.get_quote(coin.symbol, coin.coin_id)
            except MarketDataError as exc:
                results[coin.coin_id] = exc
        return results

    def search(self, query: str) -> SearchResult:
        if self.stock_data_available:
            return self._shared.search(query)
        others = [t for t in AssetType if t is not AssetType.STOCK]
        result = self._shared.search(query, asset_types=others)
        # Reported like any unavailable source, so the search box explains the missing stocks.
        stock = SourceFailure(AssetType.STOCK, StockDataNotAvailableError())
        return SearchResult(matches=result.matches, failures=[*result.failures, stock])


def user_market_data(
    user: CurrentUser, shared: Annotated[MarketData, Depends(shared_market_data)]
) -> UserMarketData:
    return UserMarketData(shared, stock_data_available=stock_data_allowed(user.email))


UserMarketDataDep = Annotated[UserMarketData, Depends(user_market_data)]


class UserPriceHistory:
    """The price-history cache, with the same stock-data allowlist as quotes."""

    def __init__(self, shared: PriceHistoryService, *, stock_data_available: bool) -> None:
        self._shared = shared
        self.stock_data_available = stock_data_available

    def now(self) -> datetime:
        return self._shared.now()

    def has_provider(self, asset_type: AssetType) -> bool:
        return self._shared.supports(asset_type)

    def closes(
        self, db: Session, asset_type: AssetType, provider_id: str, start: date, end: date
    ) -> HistoryResult:
        if asset_type is AssetType.STOCK and not self.stock_data_available:
            raise StockDataNotAvailableError()
        return self._shared.closes(db, asset_type, provider_id, start, end)


def user_price_history(
    user: CurrentUser, shared: Annotated[PriceHistoryService, Depends(shared_price_history)]
) -> UserPriceHistory:
    return UserPriceHistory(shared, stock_data_available=stock_data_allowed(user.email))


UserPriceHistoryDep = Annotated[UserPriceHistory, Depends(user_price_history)]
