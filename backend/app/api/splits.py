"""/api/splits: stock splits the user records.

A split is ledger data, not market data: from its ex-date on it converts the shares held (see
app.domain.holdings). Writes take the user write lock and never call a provider; like trade
writes, every check runs under the lock, and the oversell check after the change is flushed.
"""

import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import date, datetime

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import CodedHTTPError
from app.core.security import CurrentUser
from app.db.models import StockSplit, Transaction, UserAsset
from app.db.session import DbSession
from app.domain.enums import AssetType
from app.domain.holdings import NEW_YORK, find_oversell, held_before, split_quantity
from app.schemas.decimal import format_decimal
from app.schemas.split import SplitCreate, SplitRead, SplitUpdate, check_ratio
from app.services.asset_identity import lock_user_writes
from app.services.ledger import symbol_ledger

router = APIRouter(prefix="/splits", tags=["splits"])

DUPLICATE_CODE = "split_exists"


def today() -> date:
    return datetime.now(NEW_YORK).date()


def _get_owned(db: Session, user_id: uuid.UUID, split_id: uuid.UUID) -> StockSplit:
    split = db.scalar(
        select(StockSplit).where(StockSplit.id == split_id, StockSplit.user_id == user_id)
    )
    if split is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Split not found")
    return split


def _read(
    split: StockSplit, trades: Sequence[Transaction], splits: Sequence[StockSplit]
) -> SplitRead:
    before = held_before(trades, splits, split.effective_date)
    return SplitRead(
        id=split.id,
        symbol=split.symbol,
        effective_date=split.effective_date,
        numerator=split.numerator,
        denominator=split.denominator,
        shares_before=before,
        shares_after=split_quantity(before, split),
        created_at=split.created_at,
    )


def _check_stock(db: Session, user_id: uuid.UUID, symbol: str) -> None:
    # No record means no trades: the holdings check says so in the user's terms.
    record = db.get(UserAsset, (user_id, symbol))
    if record is not None and record.asset_type is not AssetType.STOCK:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Splits are for stocks only, and your {symbol} entries are crypto.",
        )


def _check_date(day: date) -> None:
    # The replay doesn't know what day it is, so a future split would apply at once.
    if day > today():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A split can't be in the future. Add it once its ex-date has come.",
        )


def _check_unique(
    db: Session, user_id: uuid.UUID, symbol: str, day: date, editing: uuid.UUID | None = None
) -> None:
    query = select(StockSplit.id).where(
        StockSplit.user_id == user_id, StockSplit.symbol == symbol, StockSplit.effective_date == day
    )
    if editing is not None:
        query = query.where(StockSplit.id != editing)
    if db.scalar(query) is not None:
        raise CodedHTTPError(
            status.HTTP_409_CONFLICT,
            DUPLICATE_CODE,
            f"You already recorded a {symbol} split on {day.isoformat()}.",
        )


def _check_held(
    trades: Sequence[Transaction], others: Sequence[StockSplit], symbol: str, day: date
) -> None:
    if held_before(trades, others, day) <= 0:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=(
                f"You held no {symbol} shares before {day.isoformat()}, so there's nothing to "
                "split. Use the ex-date: the first day the stock traded at the new price."
            ),
        )


def _commit_if_no_oversell(db: Session, user_id: uuid.UUID, symbol: str, change: str) -> None:
    db.flush()
    trades, splits = symbol_ledger(db, user_id, symbol)
    oversell = find_oversell(trades, splits)
    if oversell is not None:
        db.rollback()
        sell = oversell.sell
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=(
                f"{change}, your sell of {format_decimal(sell.quantity)} {symbol} on "
                f"{sell.executed_at.astimezone(NEW_YORK).date().isoformat()} would be more than "
                f"the {format_decimal(oversell.held_before)} shares held then. Edit or delete that "
                "sell first."
            ),
        )
    db.commit()


def _read_saved(db: Session, user_id: uuid.UUID, split: StockSplit) -> SplitRead:
    db.refresh(split)
    trades, splits = symbol_ledger(db, user_id, split.symbol)
    return _read(split, trades, splits)


@router.post("", response_model=SplitRead, status_code=status.HTTP_201_CREATED)
def create_split(body: SplitCreate, user: CurrentUser, db: DbSession) -> SplitRead:
    lock_user_writes(db, user.id)
    _check_stock(db, user.id, body.symbol)
    _check_date(body.effective_date)
    _check_unique(db, user.id, body.symbol, body.effective_date)
    trades, splits = symbol_ledger(db, user.id, body.symbol)
    _check_held(trades, splits, body.symbol, body.effective_date)
    split = StockSplit(user_id=user.id, **body.model_dump())
    db.add(split)
    # A reverse split can leave a later sell larger than what's held.
    _commit_if_no_oversell(db, user.id, body.symbol, "With this split")
    return _read_saved(db, user.id, split)


@router.get("", response_model=list[SplitRead])
def list_splits(user: CurrentUser, db: DbSession, symbol: str | None = None) -> list[SplitRead]:
    splits_query = select(StockSplit).where(StockSplit.user_id == user.id)
    trades_query = select(Transaction).where(Transaction.user_id == user.id)
    if symbol is not None:
        symbol = symbol.strip().upper()
        splits_query = splits_query.where(StockSplit.symbol == symbol)
        trades_query = trades_query.where(Transaction.symbol == symbol)
    splits = list(
        db.scalars(splits_query.order_by(StockSplit.effective_date.desc(), StockSplit.symbol))
    )
    if not splits:
        return []
    trades_of: dict[str, list[Transaction]] = defaultdict(list)
    for trade in db.scalars(trades_query):
        trades_of[trade.symbol].append(trade)
    splits_of: dict[str, list[StockSplit]] = defaultdict(list)
    for split in splits:
        splits_of[split.symbol].append(split)
    return [_read(s, trades_of[s.symbol], splits_of[s.symbol]) for s in splits]


@router.patch("/{split_id}", response_model=SplitRead)
def update_split(
    split_id: uuid.UUID, body: SplitUpdate, user: CurrentUser, db: DbSession
) -> SplitRead:
    lock_user_writes(db, user.id)
    split = _get_owned(db, user.id, split_id)
    day = body.effective_date or split.effective_date
    numerator = body.numerator or split.numerator
    denominator = body.denominator or split.denominator
    try:
        check_ratio(numerator, denominator)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    _check_date(day)
    _check_unique(db, user.id, split.symbol, day, editing=split.id)
    trades, splits = symbol_ledger(db, user.id, split.symbol)
    _check_held(trades, [s for s in splits if s.id != split.id], split.symbol, day)
    split.effective_date, split.numerator, split.denominator = day, numerator, denominator
    _commit_if_no_oversell(db, user.id, split.symbol, "With this change")
    return _read_saved(db, user.id, split)


@router.delete("/{split_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_split(split_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Response:
    lock_user_writes(db, user.id)
    split = _get_owned(db, user.id, split_id)
    symbol = split.symbol
    db.delete(split)
    _commit_if_no_oversell(db, user.id, symbol, "Without this split")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
