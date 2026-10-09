from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CoinIndexEntry(Base):
    """One of the top coins by market cap, for search-as-you-type without a provider call.

    Public market data shared by every user. The whole table is replaced on each refresh, so
    every row carries the same updated_at: the index's age.
    """

    __tablename__ = "coin_index"

    # The CoinGecko coin id.
    provider_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    # Upper-cased. Not unique: different coins share tickers.
    symbol: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(256))
    market_cap_rank: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
