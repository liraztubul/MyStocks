from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.domain.enums import AssetType
from app.schemas.decimal import DecimalString, Percent


def _normalize_symbol(symbol: str) -> str:
    symbol = symbol.strip().upper()
    if not symbol:
        raise ValueError("symbol must not be blank")
    return symbol


class WatchlistAdd(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: Annotated[str, Field(max_length=32), AfterValidator(_normalize_symbol)]
    type: AssetType
    # The coin picked in search (CoinGecko id); omitted, the user's recorded coin or the coin
    # rules decide.
    id: Annotated[str | None, Field(min_length=1, max_length=128)] = None


class WatchlistItemRead(BaseModel):
    symbol: str
    asset_type: AssetType
    coin_id: str | None
    # Chosen by the coin rules, never by the user: show "picked automatically".
    coin_auto_picked: bool
    added_at: datetime
    # Exact, as the provider sent it (micro-priced coins keep their digits).
    price: DecimalString | None
    currency: str | None
    price_as_of: datetime | None
    # Served from the last good copy because the provider failed; price_as_of is that copy's.
    stale: bool
    # The provider's rolling 24h change in percent, from the same response as the price (and
    # stale together with it). Null when the provider didn't give one.
    change_pct: Percent | None
    change_basis: Literal["24h_rolling"] | None
    # Why there's no price: a stable code and a sentence for people.
    unavailable_code: str | None
    unavailable_reason: str | None
