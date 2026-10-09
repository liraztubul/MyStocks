from fastapi import APIRouter

from app.api import asset_history, assets, auth, coins, health, portfolio, transactions, watchlist

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(transactions.router)
api_router.include_router(assets.router)
api_router.include_router(coins.router)
api_router.include_router(asset_history.router)
api_router.include_router(portfolio.router)
api_router.include_router(watchlist.router)
