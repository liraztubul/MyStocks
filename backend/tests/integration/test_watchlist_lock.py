"""Adding a coin that the rules must resolve calls the provider without holding the user's write
lock: another connection can take the lock during the call.

Commits for real (the lock check needs a second connection), and cleans up after itself.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import Engine, delete, select, text
from sqlalchemy.orm import Session

from app.db.models import User, UserAsset, WatchlistItem
from app.domain.enums import AssetType
from app.market_data.access import UserMarketData
from app.market_data.provider import Quote
from app.market_data.service import MarketData
from app.services import watchlist


class LockProbe:
    def __init__(self, engine: Engine, user_id: uuid.UUID) -> None:
        self.engine, self.user_id = engine, user_id
        self.lock_free: list[bool] = []

    def get_quote(self, symbol: str, provider_id: str | None = None) -> Quote:
        with self.engine.connect() as other:
            row = other.execute(
                text("SELECT id FROM users WHERE id = :id FOR UPDATE SKIP LOCKED"),
                {"id": self.user_id},
            ).first()
            self.lock_free.append(row is not None)
            other.rollback()
        return Quote(
            symbol,
            AssetType.CRYPTO,
            Decimal("1"),
            "USD",
            datetime(2026, 10, 7, tzinfo=UTC),
            coin_id="bitcoin",
            coin_auto_picked=True,
        )

    def search(self, query: str):  # type: ignore[no-untyped-def]
        raise AssertionError("unexpected provider call")

    get_price_on = get_quotes = search


def test_rules_lookup_runs_without_the_write_lock(engine: Engine) -> None:
    with Session(engine) as setup:
        user = User(email=f"lock-{uuid.uuid4().hex}@example.com", password_hash="x")
        setup.add(user)
        setup.commit()
        user_id = user.id
    probe = LockProbe(engine, user_id)
    market_data = UserMarketData(
        MarketData({AssetType.STOCK: probe, AssetType.CRYPTO: probe}), stock_data_available=True
    )
    try:
        with Session(engine) as db:
            watchlist.add(db, market_data, user_id, "BTC", AssetType.CRYPTO, None)
        assert probe.lock_free == [True]
        with Session(engine) as check:
            assert check.get(WatchlistItem, (user_id, "BTC")) is not None
            asset = check.scalar(select(UserAsset).where(UserAsset.user_id == user_id))
            assert asset is not None and (asset.provider_id, asset.id_source) == ("bitcoin", "rule")
    finally:
        with Session(engine) as cleanup:
            cleanup.execute(delete(User).where(User.id == user_id))
            cleanup.commit()
