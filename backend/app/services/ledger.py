"""One symbol's ledger as the checks replay it: its trades and the splits the user recorded."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import StockSplit, Transaction


def symbol_ledger(
    db: Session, user_id: uuid.UUID, symbol: str
) -> tuple[list[Transaction], list[StockSplit]]:
    trades = db.scalars(
        select(Transaction).where(Transaction.user_id == user_id, Transaction.symbol == symbol)
    ).all()
    splits = db.scalars(
        select(StockSplit).where(StockSplit.user_id == user_id, StockSplit.symbol == symbol)
    ).all()
    return list(trades), list(splits)
