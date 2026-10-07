"""watchlist_items constraints, and the identity record it relies on staying put."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Transaction, User, UserAsset, WatchlistItem
from app.domain.enums import AssetType, Side
from app.market_data.access import UserMarketData
from app.market_data.service import MarketData
from app.services.asset_identity import ensure_asset_identity


class NoNetwork:
    def search(self, query: str):  # type: ignore[no-untyped-def]
        raise AssertionError("unexpected provider call")

    get_quote = get_price_on = search


MARKET = UserMarketData(
    MarketData({AssetType.STOCK: NoNetwork(), AssetType.CRYPTO: NoNetwork()}),
    stock_data_available=True,
)


def user(db: Session, email: str = "watcher@example.com") -> User:
    row = User(email=email, password_hash="x")
    db.add(row)
    db.flush()
    return row


def watch(db: Session, owner: User, symbol: str = "BTC", coin: str = "bitcoin") -> None:
    db.add(
        UserAsset(
            user_id=owner.id,
            symbol=symbol,
            asset_type=AssetType.CRYPTO,
            provider_id=coin,
            id_source="user",
        )
    )
    db.add(WatchlistItem(user_id=owner.id, symbol=symbol))
    db.flush()


def test_a_watch_needs_the_symbols_identity_record(db_session: Session) -> None:
    owner = user(db_session)
    db_session.add(WatchlistItem(user_id=owner.id, symbol="BTC"))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_a_watched_symbols_identity_record_cannot_be_deleted(db_session: Session) -> None:
    owner = user(db_session)
    watch(db_session, owner)
    db_session.delete(db_session.get(UserAsset, (owner.id, "BTC")))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_deleting_the_user_removes_their_watchlist(db_session: Session) -> None:
    owner = user(db_session)
    watch(db_session, owner)
    db_session.delete(owner)
    db_session.flush()
    assert db_session.scalars(select(WatchlistItem)).all() == []


def test_one_row_per_user_and_symbol(db_session: Session) -> None:
    owner = user(db_session)
    watch(db_session, owner)
    db_session.add(WatchlistItem(user_id=owner.id, symbol="BTC"))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_a_watched_record_is_in_use_even_without_trades(db_session: Session) -> None:
    owner = user(db_session)
    watch(db_session, owner, coin="bitcoin")
    db_session.add(
        Transaction(
            user_id=owner.id,
            symbol="BTC",
            asset_type=AssetType.CRYPTO,
            side=Side.BUY,
            quantity=Decimal(1),
            price=Decimal(1),
            executed_at=datetime(2026, 9, 1, tzinfo=UTC),
        )
    )
    db_session.flush()
    trade = db_session.scalars(select(Transaction)).one()
    db_session.delete(trade)
    db_session.flush()
    # No trades left, but the symbol is still watched: the user's coin stays protected.
    with pytest.raises(Exception) as refused:
        ensure_asset_identity(db_session, MARKET, owner.id, "BTC", AssetType.CRYPTO, "bitcoin-cash")
    assert getattr(refused.value, "code", None) == "asset_identity_conflict"
    assert db_session.get(UserAsset, (owner.id, "BTC")).provider_id == "bitcoin"
