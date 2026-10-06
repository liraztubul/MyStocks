import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from app.domain.enums import AssetType, Side
from app.schemas.decimal import DecimalString

HistoryRange = Literal["1M", "3M", "6M", "YTD", "1Y", "ALL"]
# Why there is no chart: stock data isn't shown to this user here, or no stock history provider
# is configured on this deployment yet.
UnavailableReason = Literal["not_available_on_deployment", "provider_not_configured"]
# Why a trade isn't drawn: older than the chart, its day hasn't closed yet, there's no chart, or
# the chart shows another coin than the one the user's trades are recorded under.
UndrawnReason = Literal["before_range", "after_range", "no_chart", "different_coin"]


class BarRead(BaseModel):
    date: date
    # Unrounded Decimal string: closes are stored with 18 decimal places.
    close: DecimalString


class SplitRead(BaseModel):
    date: date
    ratio: DecimalString


class MarkerRead(BaseModel):
    transaction_id: uuid.UUID
    side: Side
    # The bar the marker is drawn on. Differs from trade_date only when snapped: the trade's day
    # has no close (e.g. a weekend), so the marker sits on the next bar.
    date: date
    trade_date: date
    snapped: bool
    quantity: DecimalString
    price: DecimalString


class UndrawnTradeRead(BaseModel):
    transaction_id: uuid.UUID
    side: Side
    trade_date: date
    quantity: DecimalString
    price: DecimalString
    reason: UndrawnReason


class CoinCandidateRead(BaseModel):
    id: str
    symbol: str
    name: str
    rank: int | None


class HistoryRead(BaseModel):
    symbol: str
    asset_type: AssetType
    available: bool
    unavailable_reason: UnavailableReason | None = None
    # Crypto: several coins share the ticker and none was chosen; pick one (then pass ?id=).
    ambiguous: bool = False
    candidates: list[CoinCandidateRead] = []
    provider: str | None = None
    coin_id: str | None = None
    coin_name: str | None = None
    # Chosen by the coin rules rather than the user: show "Showing <coin>, not this one?".
    coin_auto_picked: bool = False
    range: HistoryRange
    range_start: date | None = None
    range_end: date | None = None
    # Set when the requested range was cut short, e.g. crypto history covers 365 days.
    range_note: str | None = None
    bars: list[BarRead] = []
    splits: list[SplitRead] = []
    markers: list[MarkerRead] = []
    # The user's trades for this symbol that aren't drawn, so the UI can still list them.
    undrawn_trades: list[UndrawnTradeRead] = []
    as_of: datetime | None = None
    is_stale: bool = False
    stale_reason: str | None = None
