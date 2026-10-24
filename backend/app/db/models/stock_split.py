import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.transaction import AMOUNT


class StockSplit(Base):
    """A stock split the user recorded. Its own table rather than a third trade side: it has no
    price, fee or quantity, and the trade columns keep their strict checks. The ledger replay
    applies it from `effective_date` on (see app.domain.holdings)."""

    __tablename__ = "stock_splits"
    __table_args__ = (
        CheckConstraint("numerator > 0", name="numerator_positive"),
        CheckConstraint("denominator > 0", name="denominator_positive"),
        CheckConstraint("numerator <> denominator", name="ratio_not_one"),
        # Also serves "a user's splits of one symbol".
        UniqueConstraint(
            "user_id", "symbol", "effective_date", name="uq_stock_splits_user_symbol_date"
        ),
        # Like the watchlist: the symbol's identity record can't disappear under a split
        # (asset_identity treats a split as a use of the record).
        ForeignKeyConstraint(
            ["user_id", "symbol"],
            ["user_assets.user_id", "user_assets.symbol"],
            name="fk_stock_splits_user_assets",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    symbol: Mapped[str] = mapped_column(String(32))
    # The ex-date: the first New York trading day at the new price.
    effective_date: Mapped[date] = mapped_column(Date)
    # 4:1 is 4/1; a 1:10 reverse split is 1/10.
    numerator: Mapped[Decimal] = mapped_column(AMOUNT)
    denominator: Mapped[Decimal] = mapped_column(AMOUNT)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
