from fastapi import FastAPI

from app.api import api_router, probes
from app.api.assets import market_data_error_handler
from app.core.config import settings
from app.core.edge import EdgeGuardMiddleware
from app.market_data.provider import MarketDataError

app = FastAPI(
    title="MyStocks API",
    # Interactive docs are a dev convenience; in production they'd only map the API for attackers.
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None,
    openapi_url=None if settings.is_production else "/openapi.json",
)
app.add_middleware(EdgeGuardMiddleware)
app.include_router(probes.router)
app.include_router(api_router)
app.add_exception_handler(MarketDataError, market_data_error_handler)
