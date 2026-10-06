import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.transaction import str_enum
from app.domain.enums import AssetType


class UserAsset(Base):
    """What a user's ticker means: one row per (user, symbol), the single source of truth.

    Stored once rather than on every transaction (normalization), so a position can't mix two
    asset types or two coins that share a ticker; either would corrupt the average cost.
    """

    __tablename__ = "user_assets"
    __table_args__ = (
        CheckConstraint("id_source IN ('user', 'rule')", name="id_source"),
        # A coin id is either chosen (by the user or a rule) or unknown, never half of each.
        CheckConstraint("(provider_id IS NULL) = (id_source IS NULL)", name="provider_id_source"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    asset_type: Mapped[AssetType] = mapped_column(str_enum(AssetType, "asset_type"))
    # Crypto: the CoinGecko coin id. Null for stocks (the ticker is the id) and for crypto whose
    # coin isn't known yet (rows from before this table, or a provider outage at write time).
    provider_id: Mapped[str | None] = mapped_column(String(128))
    # "user": picked by the user, protected. "rule": chosen automatically, replaceable by a pick.
    id_source: Mapped[str | None] = mapped_column(String(8))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
