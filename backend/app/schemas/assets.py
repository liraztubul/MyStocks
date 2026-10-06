from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.domain.enums import AssetType
from app.market_data.provider import PriceKind
from app.schemas.decimal import Money

# Providers can quote more decimals than Numeric(28, 10) stores (tiny-cap coins); rounding to
# 10 places means an auto-filled price is always one the transaction endpoint will accept.
MarketPrice = Money


class _FromAttributes(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class AssetMatchRead(_FromAttributes):
    symbol: str
    name: str
    asset_type: AssetType
    provider_id: str


class UnavailableSource(BaseModel):
    asset_type: AssetType
    code: str
    detail: str


class AssetSearchResponse(BaseModel):
    results: list[AssetMatchRead]
    # Sources that failed while others answered, so the UI can say "crypto search is down".
    unavailable: list[UnavailableSource]
    stock_data_available: bool


class QuoteRead(_FromAttributes):
    symbol: str
    asset_type: AssetType
    price: MarketPrice
    currency: str
    as_of: datetime
    is_stale: bool


class PriceOnDateRead(_FromAttributes):
    symbol: str
    asset_type: AssetType
    price: MarketPrice
    currency: str
    requested_date: date
    price_date: date
    is_fallback: bool
    kind: PriceKind
    note: str | None
