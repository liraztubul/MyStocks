from fastapi import FastAPI

from app.api import api_router
from app.api.assets import market_data_error_handler
from app.market_data.provider import MarketDataError

app = FastAPI(title="MyStocks API")
app.include_router(api_router)
app.add_exception_handler(MarketDataError, market_data_error_handler)
