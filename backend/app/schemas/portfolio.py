import uuid
from datetime import datetime

from pydantic import BaseModel

from app.domain.enums import AssetType
from app.schemas.decimal import Money, Percent


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
