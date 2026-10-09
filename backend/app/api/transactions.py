import uuid
from collections.abc import Callable

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import CodedHTTPError
from app.core.security import CurrentUser
from app.db.models import Transaction
from app.db.session import DbSession
from app.domain.enums import AssetType, Side
from app.domain.holdings import find_oversell
from app.market_data.access import UserMarketData, UserMarketDataDep
from app.market_data.provider import MarketDataError
from app.schemas.decimal import format_decimal
from app.schemas.transaction import TransactionCreate, TransactionRead, TransactionUpdate
from app.services.asset_identity import (
    LookupNeeded,
    ensure_asset_identity,
    look_up_coin,
    needs_lookup,
)
from app.services.asset_identity import lock_user_writes as _lock_ledger

router = APIRouter(prefix="/transactions", tags=["transactions"])

CHANGED_CODE = "ledger_changed"


def _get_owned(db: Session, user_id: uuid.UUID, transaction_id: uuid.UUID) -> Transaction:
    transaction = db.scalar(
        select(Transaction).where(Transaction.id == transaction_id, Transaction.user_id == user_id)
    )
    if transaction is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    return transaction


def _ensure_no_oversell(db: Session, user_id: uuid.UUID, symbol: str) -> None:
    # Runs after the pending change is flushed, so the query already sees the ledger as it
    # would be if the write were committed.
    trades = db.scalars(
        select(Transaction).where(Transaction.user_id == user_id, Transaction.symbol == symbol)
    ).all()
    oversell = find_oversell(trades)
    if oversell is not None:
        sell = oversell.sell
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cannot sell {format_decimal(sell.quantity)} {symbol} on "
                f"{sell.executed_at.date().isoformat()}: only "
                f"{format_decimal(oversell.held_before)} held at that point"
            ),
        )


def _commit_if_valid(db: Session, user_id: uuid.UUID, symbols: set[str]) -> None:
    db.flush()
    try:
        for symbol in symbols:
            _ensure_no_oversell(db, user_id, symbol)
    except HTTPException:
        db.rollback()
        raise
    db.commit()


def _lock_with_identity(
    db: Session,
    market_data: UserMarketData,
    user_id: uuid.UUID,
    target: Callable[[], tuple[str, AssetType]],
    picked_id: str | None,
    editing: uuid.UUID | None = None,
) -> None:
    """Takes the ledger lock with `target()`'s (symbol, asset type) identity recorded or checked.

    A coin lookup the write needs runs first, with no lock and no open transaction, so the lock
    is never held across a provider call. Everything is checked again under the lock; if the
    state changed in between so that the lookup no longer applies, the flow restarts once.
    """
    for attempt in range(2):
        symbol, asset_type = target()
        # On the restart, look up whenever the rules could be asked, whatever the record says now.
        needed = needs_lookup(db, user_id, symbol, asset_type, picked_id, editing) or (
            attempt > 0 and asset_type is AssetType.CRYPTO and not picked_id
        )
        db.rollback()
        lookup = look_up_coin(market_data, symbol) if needed else None
        _lock_ledger(db, user_id)
        symbol, asset_type = target()
        try:
            ensure_asset_identity(db, user_id, symbol, asset_type, picked_id, editing, lookup)
            return
        except LookupNeeded:
            db.rollback()
        except (CodedHTTPError, MarketDataError):
            # A refused identity must leave nothing half-written.
            db.rollback()
            raise
    raise CodedHTTPError(
        status.HTTP_409_CONFLICT,
        CHANGED_CODE,
        "Your ledger changed while this was being saved. Please try again.",
    )


@router.post("", response_model=TransactionRead, status_code=status.HTTP_201_CREATED)
def create_transaction(
    body: TransactionCreate, user: CurrentUser, db: DbSession, market_data: UserMarketDataDep
) -> Transaction:
    _lock_with_identity(
        db, market_data, user.id, lambda: (body.symbol, body.asset_type), body.provider_id
    )
    transaction = Transaction(user_id=user.id, **body.model_dump(exclude={"provider_id"}))
    db.add(transaction)
    # A buy can only ever add to holdings, so only sells need the ledger check.
    _commit_if_valid(db, user.id, {transaction.symbol} if body.side is Side.SELL else set())
    db.refresh(transaction)
    return transaction


@router.get("", response_model=list[TransactionRead])
def list_transactions(
    user: CurrentUser, db: DbSession, symbol: str | None = None
) -> list[Transaction]:
    query = select(Transaction).where(Transaction.user_id == user.id)
    if symbol is not None:
        query = query.where(Transaction.symbol == symbol.strip().upper())
    query = query.order_by(Transaction.executed_at.desc(), Transaction.created_at.desc())
    return list(db.scalars(query))


@router.get("/{transaction_id}", response_model=TransactionRead)
def get_transaction(transaction_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Transaction:
    return _get_owned(db, user.id, transaction_id)


@router.patch("/{transaction_id}", response_model=TransactionRead)
def update_transaction(
    transaction_id: uuid.UUID,
    body: TransactionUpdate,
    user: CurrentUser,
    db: DbSession,
    market_data: UserMarketDataDep,
) -> Transaction:
    changes = body.model_dump(exclude_unset=True, exclude={"provider_id"})

    def target() -> tuple[str, AssetType]:
        current = _get_owned(db, user.id, transaction_id)
        return changes.get("symbol", current.symbol), changes.get("asset_type", current.asset_type)

    if {"symbol", "asset_type"} & changes.keys() or body.provider_id:
        _lock_with_identity(
            db, market_data, user.id, target, body.provider_id, editing=transaction_id
        )
    else:
        _lock_ledger(db, user.id)
    transaction = _get_owned(db, user.id, transaction_id)
    old_symbol = transaction.symbol
    for field, value in changes.items():
        setattr(transaction, field, value)
    # Any edit (a smaller buy, a later date, a new symbol) can break a sell elsewhere in the
    # history, so re-check the old symbol's ledger too when the symbol changes.
    _commit_if_valid(db, user.id, {old_symbol, transaction.symbol})
    db.refresh(transaction)
    return transaction


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(transaction_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Response:
    db.delete(_get_owned(db, user.id, transaction_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
