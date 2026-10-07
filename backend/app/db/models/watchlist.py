import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WatchlistItem(Base):
    """A symbol the user watches. What the symbol means (asset type, coin) lives only in
    user_assets, which this row points to; it's never copied here."""

    __tablename__ = "watchlist_items"
    __table_args__ = (
        # No ON DELETE: a watched symbol's identity record can't disappear under the watchlist.
        # (asset_identity also treats a watched record as in use, so it never tries.)
        ForeignKeyConstraint(
            ["user_id", "symbol"],
            ["user_assets.user_id", "user_assets.symbol"],
            name="fk_watchlist_items_user_assets",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
