"""Two first writes for the same symbol at once: one record, both trades, no IntegrityError.

Unlike the other integration tests this one commits for real (two sessions on two connections,
which the per-test rollback fixture can't give), and cleans up after itself.
"""

import threading
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session

from app.api.transactions import _lock_ledger
from app.db.models import Transaction, User, UserAsset
from app.domain.enums import AssetType, Side
from app.market_data.access import UserMarketData
from app.market_data.service import MarketData
from app.services import asset_identity
from app.services.asset_identity import ensure_asset_identity


class NoNetwork:
    """Every write here names its coin, so nothing may be looked up."""

    def search(self, query: str):  # type: ignore[no-untyped-def]
        raise AssertionError("unexpected provider call")

    get_quote = get_price_on = search


def test_concurrent_first_writes_make_one_record(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Hold each writer between "no record yet" and the insert until the other arrives (or 1 s
    # passes). With the ledger lock the second writer can't get here, so the first times out and
    # carries on; without it both would insert at once and one would hit the primary key.
    rendezvous = threading.Barrier(2)
    real_identify = asset_identity._identify

    def identify_after_rendezvous(*args, **kwargs):  # type: ignore[no-untyped-def]
        try:
            rendezvous.wait(timeout=1)
        except threading.BrokenBarrierError:
            pass
        return real_identify(*args, **kwargs)

    monkeypatch.setattr(asset_identity, "_identify", identify_after_rendezvous)

    market_data = UserMarketData(
        MarketData({AssetType.STOCK: NoNetwork(), AssetType.CRYPTO: NoNetwork()}),
        stock_data_available=True,
    )
    with Session(engine) as setup:
        user = User(email=f"race-{uuid.uuid4().hex}@example.com", password_hash="x")
        setup.add(user)
        setup.commit()
        user_id = user.id

    start = threading.Barrier(2)
    errors: list[BaseException] = []

    def first_write() -> None:
        try:
            with Session(engine) as db:
                start.wait()
                _lock_ledger(db, user_id)
                ensure_asset_identity(db, market_data, user_id, "BTC", AssetType.CRYPTO, "bitcoin")
                db.add(
                    Transaction(
                        user_id=user_id,
                        symbol="BTC",
                        asset_type=AssetType.CRYPTO,
                        side=Side.BUY,
                        quantity=Decimal("1"),
                        price=Decimal("100"),
                        executed_at=datetime(2026, 9, 1, tzinfo=UTC),
                    )
                )
                db.commit()
        except BaseException as exc:  # surfaced in the main thread below
            errors.append(exc)

    threads = [threading.Thread(target=first_write) for _ in range(2)]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        assert errors == []
        with Session(engine) as check:
            records = check.scalars(select(UserAsset).where(UserAsset.user_id == user_id)).all()
            trades = check.scalar(
                select(func.count()).select_from(Transaction).where(Transaction.user_id == user_id)
            )
        assert [(r.symbol, r.provider_id, r.id_source) for r in records] == [
            ("BTC", "bitcoin", "user")
        ]
        assert trades == 2
    finally:
        with Session(engine) as cleanup:
            cleanup.execute(delete(User).where(User.id == user_id))
            cleanup.commit()
