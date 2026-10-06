from fastapi import APIRouter

from app.api import asset_history, assets, auth, health, portfolio, transactions

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(transactions.router)
api_router.include_router(assets.router)
api_router.include_router(asset_history.router)
api_router.include_router(portfolio.router)
