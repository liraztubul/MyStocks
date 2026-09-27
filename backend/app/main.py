from fastapi import FastAPI

from app.api import api_router

app = FastAPI(title="MyStocks API")
app.include_router(api_router)
