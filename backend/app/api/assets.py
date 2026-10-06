from datetime import date
from typing import Annotated

from fastapi import APIRouter, Path, Query, Request, status
from fastapi.responses import JSONResponse

from app.domain.enums import AssetType
from app.market_data.access import StockDataNotAvailableError, UserMarketDataDep
from app.market_data.provider import (
    AmbiguousSymbolError,
    MarketDataError,
    PriceOnDate,
    PriceUnavailableError,
    Quote,
    RateLimitedError,
    SymbolNotFoundError,
)
from app.schemas.assets import (
    AssetSearchResponse,
    PriceOnDateRead,
    QuoteRead,
    UnavailableSource,
)

router = APIRouter(prefix="/assets", tags=["assets"])

Symbol = Annotated[str, Path(min_length=1, max_length=32)]
ProviderId = Annotated[str | None, Query(max_length=128)]


def _status_for(exc: MarketDataError) -> int:
    # An action on data this deployment may not show (see app.market_data.access).
    if isinstance(exc, StockDataNotAvailableError):
        return status.HTTP_403_FORBIDDEN
    # The request is fine but needs a choice from the user (which coin), not a retry.
    if isinstance(exc, AmbiguousSymbolError):
        return status.HTTP_422_UNPROCESSABLE_CONTENT
    if isinstance(exc, SymbolNotFoundError | PriceUnavailableError):
        return status.HTTP_404_NOT_FOUND
    # Rate limits are ours with the upstream provider, not the caller's, so 503 rather than 429.
    return status.HTTP_503_SERVICE_UNAVAILABLE


async def market_data_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, MarketDataError)
    headers = {}
    if isinstance(exc, RateLimitedError) and exc.retry_after:
        headers["Retry-After"] = str(exc.retry_after)
    content: dict[str, object] = {"detail": exc.message, "code": exc.code}
    if isinstance(exc, AmbiguousSymbolError):
        content["candidates"] = candidates_payload(exc)
    return JSONResponse(status_code=_status_for(exc), content=content, headers=headers)


def candidates_payload(exc: AmbiguousSymbolError) -> list[dict[str, object]]:
    return [
        {"symbol": c.symbol, "name": c.name, "provider_id": c.provider_id} for c in exc.candidates
    ]


@router.get("/search", response_model=AssetSearchResponse)
def search_assets(
    market_data: UserMarketDataDep,
    q: Annotated[str, Query(min_length=1, max_length=64)],
) -> AssetSearchResponse:
    result = market_data.search(q.strip())
    return AssetSearchResponse.model_validate(
        {
            "results": result.matches,
            "unavailable": [
                UnavailableSource(
                    asset_type=f.asset_type, code=f.error.code, detail=f.error.message
                )
                for f in result.failures
            ],
            "stock_data_available": market_data.stock_data_available,
        },
        from_attributes=True,
    )


@router.get("/{symbol}/quote", response_model=QuoteRead)
def get_quote(
    symbol: Symbol,
    asset_type: AssetType,
    market_data: UserMarketDataDep,
    provider_id: ProviderId = None,
) -> Quote:
    return market_data.provider(asset_type).get_quote(symbol.strip(), provider_id)


@router.get("/{symbol}/price-on", response_model=PriceOnDateRead)
def get_price_on(
    symbol: Symbol,
    asset_type: AssetType,
    market_data: UserMarketDataDep,
    on: Annotated[date, Query(alias="date")],
    provider_id: ProviderId = None,
) -> PriceOnDate:
    return market_data.provider(asset_type).get_price_on(symbol.strip(), on, provider_id)
