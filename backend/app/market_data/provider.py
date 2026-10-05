from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Protocol

from app.domain.enums import AssetType


@dataclass(frozen=True)
class AssetMatch:
    symbol: str
    name: str
    asset_type: AssetType
    # What the provider needs to price it: the ticker for stocks, the CoinGecko coin id for crypto.
    provider_id: str


@dataclass(frozen=True)
class Quote:
    symbol: str
    asset_type: AssetType
    price: Decimal
    currency: str
    as_of: datetime
    # True when served from the last-known-good copy because the provider failed; as_of is
    # still the original fetch's timestamp.
    is_stale: bool = False


class PriceKind(str, Enum):
    CLOSE = "close"
    LIVE = "live"


@dataclass(frozen=True)
class PriceOnDate:
    symbol: str
    asset_type: AssetType
    price: Decimal
    currency: str
    requested_date: date
    price_date: date
    # CLOSE means final and safe to cache forever; LIVE can still move.
    kind: PriceKind
    note: str | None = None

    @property
    def is_fallback(self) -> bool:
        return self.price_date != self.requested_date


class MarketDataError(Exception):
    code = "market_data_error"

    def __init__(self, message: str, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.retry_after = retry_after


class SymbolNotFoundError(MarketDataError):
    code = "symbol_not_found"


class PriceUnavailableError(MarketDataError):
    code = "price_unavailable"


class RateLimitedError(MarketDataError):
    code = "rate_limited"


class ProviderUnavailableError(MarketDataError):
    code = "provider_unavailable"


class MarketDataProvider(Protocol):
    def search(self, query: str) -> list[AssetMatch]: ...

    def get_quote(self, symbol: str, provider_id: str | None = None) -> Quote: ...

    def get_price_on(
        self, symbol: str, on: date, provider_id: str | None = None
    ) -> PriceOnDate: ...
