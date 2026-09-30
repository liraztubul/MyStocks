import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domain.currency import DEFAULT_BASE_CURRENCY
from app.domain.enums import AssetType, Side

# 18 integer digits, 10 fractional: covers satoshi-level crypto quantities and sub-cent prices.
AMOUNT = Numeric(28, 10, asdecimal=True)


def _str_enum(enum_cls: type[AssetType] | type[Side], name: str) -> Enum:
    # VARCHAR + CHECK instead of a native Postgres ENUM: adding a value later (e.g. "etf")
    # is then a plain constraint swap rather than an ALTER TYPE.
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=16,
        values_callable=lambda cls: [member.value for member in cls],
    )


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("price > 0", name="price_positive"),
        CheckConstraint("fee >= 0", name="fee_non_negative"),
        # Serves both "all of a user's trades" and the per-symbol oversell lookup.
        Index("ix_transactions_user_id_symbol", "user_id", "symbol"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    symbol: Mapped[str] = mapped_column(String(32))
    asset_type: Mapped[AssetType] = mapped_column(_str_enum(AssetType, "asset_type"))
    side: Mapped[Side] = mapped_column(_str_enum(Side, "side"))
    quantity: Mapped[Decimal] = mapped_column(AMOUNT)
    price: Mapped[Decimal] = mapped_column(AMOUNT)
    fee: Mapped[Decimal] = mapped_column(AMOUNT, default=Decimal(0), server_default="0")
    currency: Mapped[str] = mapped_column(
        String(3), default=DEFAULT_BASE_CURRENCY, server_default=DEFAULT_BASE_CURRENCY
    )
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
