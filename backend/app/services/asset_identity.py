"""Keeps each user's ticker meaning one thing: one asset type and, for crypto, one coin.

Every transaction write for a symbol goes through ensure_asset_identity, with the user's ledger
lock held, so two concurrent first writes can't create conflicting records. The one step that
needs the provider (letting the coin rules pick a coin) is look_up_coin, which callers run
before taking the lock, never under it.
"""

import uuid
from dataclasses import dataclass

from fastapi import status
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.core.errors import CodedHTTPError
from app.db.models import Transaction, User, UserAsset, WatchlistItem
from app.domain.enums import AssetType
from app.market_data.access import UserMarketData
from app.market_data.provider import AmbiguousSymbolError, MarketDataError

CONFLICT_CODE = "asset_identity_conflict"
USER = "user"
RULE = "rule"


def _conflict(detail: str) -> CodedHTTPError:
    return CodedHTTPError(status.HTTP_409_CONFLICT, CONFLICT_CODE, detail)


def lock_user_writes(db: Session, user_id: uuid.UUID) -> None:
    """Serializes one user's ledger and watchlist writes (a row lock on the user), so checks such
    as oversell, identity and the watchlist cap can't race with a concurrent write."""
    db.execute(select(User.id).where(User.id == user_id).with_for_update())


def asset_in_use(
    db: Session, user_id: uuid.UUID, symbol: str, excluding: uuid.UUID | None = None
) -> bool:
    """Whether anything still relies on the symbol's recorded meaning: a trade (other than the
    one being edited) or a watchlist entry, which points at the record and has no trades."""
    trades = select(Transaction.id).where(
        Transaction.user_id == user_id, Transaction.symbol == symbol
    )
    if excluding is not None:
        trades = trades.where(Transaction.id != excluding)
    watched = select(WatchlistItem.symbol).where(
        WatchlistItem.user_id == user_id, WatchlistItem.symbol == symbol
    )
    return bool(db.scalar(select(exists(trades)))) or bool(db.scalar(select(exists(watched))))


class LookupNeeded(Exception):
    """The state changed after the unlocked check: the coin has to be looked up after all."""


@dataclass(frozen=True)
class CoinLookup:
    """What the coin rules said about a ticker, looked up before the lock was taken."""

    symbol: str
    provider_id: str | None
    id_source: str | None


def needs_lookup(
    db: Session,
    user_id: uuid.UUID,
    symbol: str,
    asset_type: AssetType,
    picked_id: str | None,
    editing: uuid.UUID | None = None,
) -> bool:
    """Whether recording `symbol` would need the coin rules (a provider call): crypto without a
    pick, and no record that something else still uses."""
    if asset_type is not AssetType.CRYPTO or picked_id:
        return False
    record = db.get(UserAsset, (user_id, symbol))
    return record is None or not asset_in_use(db, user_id, symbol, editing)


def look_up_coin(market_data: UserMarketData, symbol: str) -> CoinLookup:
    """The coin rules' pick for an unpicked crypto ticker. Calls the provider: never call it with
    the write lock held. Raises AmbiguousSymbolError when the user has to choose."""
    try:
        quote = market_data.provider(AssetType.CRYPTO).get_quote(symbol)
    except AmbiguousSymbolError:
        raise
    except MarketDataError:
        # Unknown ticker or provider down: don't block the write on CoinGecko. The coin stays
        # unknown and is resolved at read time, with the "picked automatically" disclosure.
        return CoinLookup(symbol, None, None)
    if quote.coin_auto_picked and quote.coin_id:
        return CoinLookup(symbol, quote.coin_id, RULE)
    return CoinLookup(symbol, None, None)


def _identify(
    symbol: str, asset_type: AssetType, picked_id: str | None, lookup: CoinLookup | None
) -> tuple[str | None, str | None]:
    """(provider_id, id_source) for a symbol seen for the first time. No provider call."""
    if asset_type is AssetType.STOCK:
        return None, None
    if picked_id:
        return picked_id, USER
    if lookup is None or lookup.symbol != symbol:
        raise LookupNeeded()
    return lookup.provider_id, lookup.id_source


def ensure_asset_identity(
    db: Session,
    user_id: uuid.UUID,
    symbol: str,
    asset_type: AssetType,
    picked_id: str | None,
    editing: uuid.UUID | None = None,
    lookup: CoinLookup | None = None,
) -> None:
    """Record or check what `symbol` means for this user. Raises 409 on a conflict.

    `picked_id` is a coin the user chose in search (None: typed by hand, or a sell). `editing`
    is the transaction being changed, which doesn't count as an existing use of the symbol.
    `lookup` is look_up_coin's answer when needs_lookup said so; if the state has changed since
    and a lookup is now needed that wasn't done, this raises LookupNeeded (nothing written).
    """
    record = db.get(UserAsset, (user_id, symbol))
    if record is not None and not asset_in_use(db, user_id, symbol, editing):
        # Nothing uses the old meaning any more (no trades, not watched), so it
        # binds nothing: this is also how a wrong asset type or coin gets fixed for now.
        db.delete(record)
        db.flush()
        record = None

    if record is None:
        provider_id, id_source = _identify(symbol, asset_type, picked_id, lookup)
        db.add(
            UserAsset(
                user_id=user_id,
                symbol=symbol,
                asset_type=asset_type,
                provider_id=provider_id,
                id_source=id_source,
            )
        )
        return

    if record.asset_type is not asset_type:
        raise _conflict(
            f"Your {symbol} entries are recorded as {record.asset_type.value}, so this one can't "
            f"be {asset_type.value}. To change it, delete your {symbol} entries and add them again."
        )
    if asset_type is AssetType.STOCK or not picked_id or picked_id == record.provider_id:
        # Inherit the recorded coin. Picking the same coin explicitly confirms an automatic pick.
        if picked_id and record.id_source == RULE:
            record.id_source = USER
        return
    if record.id_source == USER:
        raise _conflict(
            f"Your {symbol} entries track the coin '{record.provider_id}', not '{picked_id}'. One "
            f"ticker can only track one coin; to switch, delete your {symbol} entries and add "
            "them again with the right coin."
        )
    # An automatic (or unknown) coin gives way to one the user explicitly picked.
    record.provider_id = picked_id
    record.id_source = USER
