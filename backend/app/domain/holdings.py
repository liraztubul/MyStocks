from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol, TypeVar

from app.domain.enums import Side


class Trade(Protocol):
    side: Side
    quantity: Decimal
    executed_at: datetime


def signed_quantity(trade: Trade) -> Decimal:
    return trade.quantity if trade.side is Side.BUY else -trade.quantity


def held_quantity(trades: Iterable[Trade]) -> Decimal:
    """Quantity currently held for one symbol: buys minus sells."""
    return sum((signed_quantity(t) for t in trades), Decimal(0))


@dataclass(frozen=True)
class Oversell:
    sell: Trade
    held_before: Decimal


T = TypeVar("T", bound=Trade)


def chronological(
    trades: Iterable[T], tiebreak: Callable[[T], tuple[Any, ...]] = lambda _: ()
) -> list[T]:
    """Trades in the order the ledger replays them: by executed_at, buys before sells.

    Buys go first at the same timestamp because trades logged with only a date all land on
    midnight, and a same-day buy-then-sell must not count as an oversell. Quantity, then any
    caller-supplied fields, break remaining ties so a replay never depends on load order.
    """
    return sorted(
        trades, key=lambda t: (t.executed_at, t.side is Side.SELL, t.quantity, *tiebreak(t))
    )


def find_oversell(trades: Iterable[Trade]) -> Oversell | None:
    """First sell (in executed_at order) that exceeds what was held at that moment, if any.

    Checking the running balance rather than just the final total also catches a sell
    backdated to before the buys that would cover it.
    """
    held = Decimal(0)
    for trade in chronological(trades):
        if trade.side is Side.SELL and trade.quantity > held:
            return Oversell(sell=trade, held_before=held)
        held += signed_quantity(trade)
    return None
