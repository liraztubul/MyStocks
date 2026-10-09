"""Writes that need the coin rules call the provider without holding the user's write lock, and
start over once when the state changes between that lookup and the lock.

The lock tests commit for real (checking the lock needs a second connection) and clean up after
themselves; the restart tests run in the usual rolled-back test transaction.
"""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session

from app.api import transactions as transactions_api
from app.db.models import Transaction, User, UserAsset, WatchlistItem
from app.domain.enums import AssetType, Side
from app.market_data.access import UserMarketData
from app.market_data.provider import Quote
from app.market_data.service import MarketData
from app.schemas.transaction import TransactionCreate, TransactionUpdate
from app.services import watchlist
from tests.integration.test_watchlist_lock import LockProbe

WHEN = datetime(2026, 9, 1, 12, tzinfo=UTC)


def market(provider: Any) -> UserMarketData:
    return UserMarketData(
        MarketData({AssetType.STOCK: provider, AssetType.CRYPTO: provider}),
        stock_data_available=True,
    )


def buy(symbol: str, asset_type: AssetType = AssetType.CRYPTO) -> TransactionCreate:
    return TransactionCreate(
        symbol=symbol,
        asset_type=asset_type,
        side=Side.BUY,
        quantity=Decimal("1"),
        price=Decimal("100"),
        executed_at=WHEN,
    )


def committed_user(engine: Engine) -> uuid.UUID:
    with Session(engine) as setup:
        user = User(email=f"lock-{uuid.uuid4().hex}@example.com", password_hash="x")
        setup.add(user)
        setup.commit()
        return user.id


def remove_user(engine: Engine, user_id: uuid.UUID) -> None:
    with Session(engine) as cleanup:
        cleanup.execute(delete(User).where(User.id == user_id))
        cleanup.commit()


def record(db: Session, user_id: uuid.UUID, symbol: str) -> tuple[str | None, str | None] | None:
    row = db.get(UserAsset, (user_id, symbol), populate_existing=True)
    return None if row is None else (row.provider_id, row.id_source)


# --- No lock across the provider call ------------------------------------------------------------


def test_create_looks_up_the_coin_without_the_lock(engine: Engine) -> None:
    user_id = committed_user(engine)
    probe = LockProbe(engine, user_id)
    try:
        with Session(engine) as db:
            transactions_api.create_transaction(
                buy("BTC"),
                SimpleNamespace(id=user_id),
                db,
                market(probe),  # type: ignore[arg-type]
            )
        assert probe.lock_free == [True]
        with Session(engine) as check:
            assert record(check, user_id, "BTC") == ("bitcoin", "rule")
    finally:
        remove_user(engine, user_id)


def test_update_to_a_new_coin_looks_it_up_without_the_lock(engine: Engine) -> None:
    user_id = committed_user(engine)
    probe = LockProbe(engine, user_id)
    try:
        with Session(engine) as db:
            created = transactions_api.create_transaction(
                buy("AAPL", AssetType.STOCK),
                SimpleNamespace(id=user_id),
                db,
                market(probe),  # type: ignore[arg-type]
            )
            assert probe.lock_free == []  # a stock needs no lookup
            transactions_api.update_transaction(
                created.id,
                TransactionUpdate(symbol="BTC", asset_type=AssetType.CRYPTO),
                SimpleNamespace(id=user_id),  # type: ignore[arg-type]
                db,
                market(probe),
            )
        assert probe.lock_free == [True]
        with Session(engine) as check:
            assert record(check, user_id, "BTC") == ("bitcoin", "rule")
    finally:
        remove_user(engine, user_id)


# --- The state changes between the unlocked check and the lock: restart once ---------------------


class RuleProvider:
    """Answers a ticker lookup with an automatic pick, and counts the lookups."""

    def __init__(self, coin_id: str) -> None:
        self.coin_id = coin_id
        self.lookups: list[str] = []

    def get_quote(self, symbol: str, provider_id: str | None = None) -> Quote:
        assert provider_id is None
        self.lookups.append(symbol)
        return Quote(
            symbol,
            AssetType.CRYPTO,
            Decimal("1"),
            "USD",
            WHEN,
            coin_id=self.coin_id,
            coin_auto_picked=True,
        )


def concurrent_removal_on_first_lock(
    db: Session, real_lock: Callable[[Session, uuid.UUID], None], symbol: str
) -> tuple[Callable[[Session, uuid.UUID], None], list[int]]:
    """A lock function that, the first time, lets "another request" delete the symbol's trades and
    identity record and commit, right before the lock is taken."""
    calls: list[int] = []

    def lock(session: Session, user_id: uuid.UUID) -> None:
        calls.append(1)
        if len(calls) == 1:
            session.execute(
                delete(Transaction).where(
                    Transaction.user_id == user_id, Transaction.symbol == symbol
                )
            )
            session.execute(
                delete(UserAsset).where(UserAsset.user_id == user_id, UserAsset.symbol == symbol)
            )
            session.commit()
        real_lock(session, user_id)

    return lock, calls


@pytest.fixture
def owner(db_session: Session) -> User:
    user = User(email="restart@example.com", password_hash="x")
    db_session.add(user)
    db_session.flush()
    return user


def held(db: Session, owner: User, symbol: str, coin: str) -> None:
    """A trade with its identity record: the coin is known, so no lookup looks needed."""
    db.add(
        UserAsset(
            user_id=owner.id,
            symbol=symbol,
            asset_type=AssetType.CRYPTO,
            provider_id=coin,
            id_source="user",
        )
    )
    db.add(
        Transaction(
            user_id=owner.id,
            symbol=symbol,
            asset_type=AssetType.CRYPTO,
            side=Side.BUY,
            quantity=Decimal("1"),
            price=Decimal("100"),
            executed_at=WHEN,
        )
    )
    db.commit()


def test_transaction_restarts_when_the_recorded_coin_vanishes(
    db_session: Session, owner: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    held(db_session, owner, "ETH", "ethereum")
    provider = RuleProvider("ethereum")
    lock, calls = concurrent_removal_on_first_lock(db_session, transactions_api._lock_ledger, "ETH")
    monkeypatch.setattr(transactions_api, "_lock_ledger", lock)

    created = transactions_api.create_transaction(
        buy("ETH"),
        SimpleNamespace(id=owner.id),
        db_session,
        market(provider),  # type: ignore[arg-type]
    )

    # First pass: the record was in use, so no lookup; it vanished before the lock, so the flow
    # started over and looked the coin up (once) before locking again.
    assert len(calls) == 2
    assert provider.lookups == ["ETH"]
    assert record(db_session, owner.id, "ETH") == ("ethereum", "rule")
    trades = db_session.scalars(select(Transaction).where(Transaction.user_id == owner.id)).all()
    assert [t.id for t in trades] == [created.id]


def test_watchlist_add_restarts_when_the_recorded_coin_vanishes(
    db_session: Session, owner: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    held(db_session, owner, "BTC", "bitcoin")
    provider = RuleProvider("bitcoin")
    lock, calls = concurrent_removal_on_first_lock(db_session, watchlist.lock_user_writes, "BTC")
    monkeypatch.setattr(watchlist, "lock_user_writes", lock)

    watchlist.add(db_session, market(provider), owner.id, "BTC", AssetType.CRYPTO, None)

    assert len(calls) == 2
    assert provider.lookups == ["BTC"]
    assert record(db_session, owner.id, "BTC") == ("bitcoin", "rule")
    assert db_session.get(WatchlistItem, (owner.id, "BTC")) is not None
