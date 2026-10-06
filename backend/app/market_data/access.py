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

from datetime import date
from typing import Annotated

from fastapi import Depends

from app.core.config import settings
from app.core.emails import normalize_email
from app.core.security import CurrentUser
from app.domain.enums import AssetType
from app.market_data.provider import (
    AssetMatch,
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
