import uuid

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import CurrentUser
from app.db.models import Transaction, User
from app.db.session import DbSession
from app.domain.enums import Side
from app.domain.holdings import find_oversell
from app.schemas.decimal import format_decimal
from app.schemas.transaction import TransactionCreate, TransactionRead, TransactionUpdate

router = APIRouter(prefix="/transactions", tags=["transactions"])


def _lock_ledger(db: Session, user_id: uuid.UUID) -> None:
    # Serializes a user's writes so two concurrent sells can't both pass the oversell check
    # against the same holdings.
    db.execute(select(User.id).where(User.id == user_id).with_for_update())


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


@router.post("", response_model=TransactionRead, status_code=status.HTTP_201_CREATED)
def create_transaction(body: TransactionCreate, user: CurrentUser, db: DbSession) -> Transaction:
    _lock_ledger(db, user.id)
    transaction = Transaction(user_id=user.id, **body.model_dump())
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
    transaction_id: uuid.UUID, body: TransactionUpdate, user: CurrentUser, db: DbSession
) -> Transaction:
    _lock_ledger(db, user.id)
    transaction = _get_owned(db, user.id, transaction_id)
    old_symbol = transaction.symbol
    for field, value in body.model_dump(exclude_unset=True).items():
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
