from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_DOWN, Decimal
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from app.domain.enums import Side
from app.domain.precision import exact

NEW_YORK = ZoneInfo("America/New_York")
# Shares after a split are rounded down to the scale amounts are stored at (Numeric(28, 10)):
# a ratio like 1:3 never terminates, and "sell all" must be able to close the position exactly.
# Down, so a split never creates shares the user didn't have.
QUANTITY_STEP = Decimal("1e-10")


class Trade(Protocol):
    # Read-only members: the replay only reads a trade, so ORM rows and frozen test doubles fit.
    @property
    def side(self) -> Side: ...
    @property
    def quantity(self) -> Decimal: ...
    @property
    def executed_at(self) -> datetime: ...


class Split(Protocol):
    """A stock split the user recorded: from `effective_date` (the ex-date, a New York date) on,
    every `denominator` shares are `numerator` shares (4:1 is 4/1, a 1:10 reverse split 1/10)."""

    @property
    def symbol(self) -> str: ...
    @property
    def effective_date(self) -> date: ...
    @property
    def numerator(self) -> Decimal: ...
    @property
    def denominator(self) -> Decimal: ...


def signed_quantity(trade: Trade) -> Decimal:
    return trade.quantity if trade.side is Side.BUY else -trade.quantity


def trading_day(trade: Trade) -> date:
    """The New York date a trade belongs to, the day a split is compared with."""
    return trade.executed_at.astimezone(NEW_YORK).date()


def split_quantity(quantity: Decimal, split: Split) -> Decimal:
    with exact():
        return (quantity * split.numerator / split.denominator).quantize(
            QUANTITY_STEP, rounding=ROUND_DOWN
        )


@dataclass(frozen=True)
class Oversell:
    sell: Trade
    held_before: Decimal


def chronological[T: Trade](
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


@dataclass(frozen=True)
class TradeStep[T: Trade]:
    trade: T


@dataclass(frozen=True)
class SplitStep[S: Split]:
    split: S


def ledger[T: Trade, S: Split](
    trades: Iterable[T],
    splits: Iterable[S] = (),
    tiebreak: Callable[[T], tuple[Any, ...]] = lambda _: (),
) -> list[TradeStep[T] | SplitStep[S]]:
    """Trades and splits in replay order: trades as chronological(), and a split before every
    trade of its New York date. On the ex-date the stock already trades at the new price, so a
    trade that day is in post-split shares (the chart's split adjustment uses the same rule)."""
    keyed: list[tuple[tuple[date, int, int], TradeStep[T] | SplitStep[S]]] = [
        ((trading_day(t), 1, i), TradeStep(t))
        for i, t in enumerate(chronological(trades, tiebreak))
    ]
    keyed += [
        ((s.effective_date, 0, i), SplitStep(s))
        for i, s in enumerate(sorted(splits, key=lambda s: s.effective_date))
    ]
    return [step for _, step in sorted(keyed, key=lambda item: item[0])]


def held_quantity(trades: Iterable[Trade], splits: Iterable[Split] = ()) -> Decimal:
    """Quantity currently held for one symbol: buys minus sells, through any splits."""
    held = Decimal(0)
    with exact():
        for step in ledger(trades, splits):
            if isinstance(step, SplitStep):
                held = split_quantity(held, step.split)
            else:
                held += signed_quantity(step.trade)
    return held


def held_before(trades: Iterable[Trade], splits: Iterable[Split], day: date) -> Decimal:
    """What was held at the start of New York date `day`: before that day's splits and trades."""
    return held_quantity(
        [t for t in trades if trading_day(t) < day], [s for s in splits if s.effective_date < day]
    )


def find_oversell(trades: Iterable[Trade], splits: Iterable[Split] = ()) -> Oversell | None:
    """First sell (in replay order) that exceeds what was held at that moment, if any.

    Checking the running balance rather than just the final total also catches a sell
    backdated to before the buys that would cover it, or to before the split it relies on.
    """
    held = Decimal(0)
    with exact():
        for step in ledger(trades, splits):
            if isinstance(step, SplitStep):
                held = split_quantity(held, step.split)
                continue
            trade = step.trade
            if trade.side is Side.SELL and trade.quantity > held:
                return Oversell(sell=trade, held_before=held)
            held += signed_quantity(trade)
    return None
