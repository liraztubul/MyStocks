# Importing every model here registers it on Base.metadata, which Alembic autogenerate reads.
from app.db.models.coin_index import CoinIndexEntry
from app.db.models.price_history import DailyClose, PriceHistoryCoverage
from app.db.models.stock_split import StockSplit
from app.db.models.transaction import Transaction
from app.db.models.user import User
from app.db.models.user_asset import UserAsset
from app.db.models.watchlist import WatchlistItem

__all__ = [
    "CoinIndexEntry",
    "DailyClose",
    "PriceHistoryCoverage",
    "StockSplit",
    "Transaction",
    "User",
    "UserAsset",
    "WatchlistItem",
]
