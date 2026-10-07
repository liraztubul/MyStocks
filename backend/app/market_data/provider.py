from collections.abc import Sequence
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
    # As the provider sent it (CoinGecko: an int or null). Kept raw on purpose:
    # coin_resolution checks it and asks the user rather than trusting an unexpected value.
    market_cap_rank: object = None


class ReferenceKind(str, Enum):
    # Stocks: the last session's official close (Finnhub `pc`).
    PREVIOUS_CLOSE = "previous_close"
    # Crypto: the price 24h before as_of, derived from CoinGecko's rolling 24h change %.
    ROLLING_24H = "rolling_24h"


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
    # The price daily change is measured from, and when it applied. All three are None when
    # the provider didn't supply a usable one, which makes daily change null, not zero.
    reference_price: Decimal | None = None
    reference_at: datetime | None = None
    reference_kind: ReferenceKind | None = None
    # Crypto: which coin was priced. coin_auto_picked means coin_resolution chose it (the user
    # never picked one), so the UI must say "Showing <name>, not this one?".
    coin_id: str | None = None
    coin_name: str | None = None
    coin_auto_picked: bool = False


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


class AmbiguousSymbolError(MarketDataError):
    """Several coins share the ticker and none is a clear choice; the user has to pick."""

    code = "ambiguous_symbol"

    def __init__(self, symbol: str, candidates: Sequence[AssetMatch]) -> None:
        super().__init__(
            f"Several coins use the ticker {symbol}. Pick the one you mean from the search."
        )
        self.candidates = tuple(candidates)


class RateLimitedError(MarketDataError):
    code = "rate_limited"


class ProviderUnavailableError(MarketDataError):
    code = "provider_unavailable"


@dataclass(frozen=True)
class CoinRef:
    """A coin to price in a batch: the provider's id, and the user's ticker for display."""

    coin_id: str
    symbol: str


class BatchQuoteProvider(Protocol):
    """Many quotes in one provider call (CoinGecko /simple/price takes up to 515 ids)."""

    def get_quotes(self, coins: Sequence[CoinRef]) -> dict[str, Quote]:
        """Quotes keyed by coin id. An id the provider doesn't know is simply absent; a failure
        of the whole call raises MarketDataError."""
        ...


class MarketDataProvider(Protocol):
    def search(self, query: str) -> list[AssetMatch]: ...

    def get_quote(self, symbol: str, provider_id: str | None = None) -> Quote: ...

    def get_price_on(
        self, symbol: str, on: date, provider_id: str | None = None
    ) -> PriceOnDate: ...
