import logging
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import api_router, probes
from app.api.assets import market_data_error_handler
from app.core.config import settings
from app.core.edge import EdgeGuardMiddleware
from app.core.errors import CodedHTTPError, coded_http_error_handler
from app.market_data.provider import MarketDataError
from app.market_data.service import check_coingecko_key

# uvicorn configures only its own loggers; give the app's a handler in the same style.
_app_logger = logging.getLogger("app")
if not _app_logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(levelname)s:     %(name)s: %(message)s"))
    _app_logger.addHandler(_handler)
    _app_logger.setLevel(settings.log_level)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # In the background: a slow or unreachable CoinGecko must never delay or break startup.
    threading.Thread(target=check_coingecko_key, name="coingecko-key-check", daemon=True).start()
    yield


app = FastAPI(
    title="MyStocks API",
    lifespan=lifespan,
    # Interactive docs are a dev convenience; in production they'd only map the API for attackers.
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None,
    openapi_url=None if settings.is_production else "/openapi.json",
)
app.add_middleware(EdgeGuardMiddleware)
app.include_router(probes.router)
app.include_router(api_router)
app.add_exception_handler(MarketDataError, market_data_error_handler)
app.add_exception_handler(CodedHTTPError, coded_http_error_handler)
