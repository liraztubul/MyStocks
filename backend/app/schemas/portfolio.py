import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.domain.enums import AssetType
from app.schemas.decimal import Money, Percent

# Stocks: change since the previous session's close. Crypto: CoinGecko's rolling 24h change,
# which is not "since a close" (crypto never closes). The two aren't directly comparable.
DayChangeBasis = Literal["since_previous_close", "rolling_24h"]


class HoldingRead(BaseModel):
    symbol: str
    asset_type: AssetType
    quantity: Money
    average_cost: Money
    cost_basis: Money
    # The fields below are null when no price could be found (see price_unavailable_reason).
    current_price: Money | None
    market_value: Money | None
    unrealized_pl: Money | None
    unrealized_pl_pct: Percent | None
    allocation_pct: Percent | None
    price_as_of: datetime | None
    price_is_stale: bool
    price_unavailable_reason: str | None
    # Price-only change since the reference (fees excluded); null when there's no reference.
    day_change: Money | None
    day_change_pct: Percent | None
    day_change_basis: DayChangeBasis | None
    day_change_reference_price: Money | None
    # Stocks: 00:00 New York on the session the change covers (which before the open can be
    # days back). Crypto: the start of the 24h window.
    day_change_reference_at: datetime | None


class AllocationRead(BaseModel):
    symbol: str
    market_value: Money
    allocation_pct: Percent


class PortfolioSummaryRead(BaseModel):
    currency: str
    total_cost_basis: Money
    # Market value and unrealized cover priced holdings only; unpriced ones are listed.
    total_market_value: Money
    total_unrealized_pl: Money
    total_unrealized_pl_pct: Percent | None
    total_realized_pl: Money
    allocation: list[AllocationRead]
    unpriced_symbols: list[str]
    has_stale_prices: bool
    # Open holdings only; a position fully closed since the reference isn't included.
    total_day_change: Money | None
    total_day_change_pct: Percent | None
    # Which bases the total mixes, so the UI can label a stock+crypto total honestly.
    day_change_bases: list[DayChangeBasis]
    day_change_unavailable_symbols: list[str]


class RealizedSaleRead(BaseModel):
    transaction_id: uuid.UUID
    symbol: str
    executed_at: datetime
    quantity: Money
    price: Money
    fee: Money
    average_cost: Money
    cost_basis: Money
    proceeds: Money
    realized_pl: Money


class RealizedPlRead(BaseModel):
    currency: str
    total_realized_pl: Money
    sales: list[RealizedSaleRead]
