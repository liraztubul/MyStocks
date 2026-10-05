"""Daily change: P/L since a reference point (a stock's previous close, or crypto's price 24h ago).

    change = qty_now * price - qty_at_ref * ref_price - bought_since_ref + sold_since_ref

That is: value now, minus value at the reference, minus net cash put in since. So shares
bought after the reference are measured from their buy price (not the reference), and shares
sold after it contribute (sell_price - ref_price) * quantity.

    pct = change / (qty_at_ref * ref_price + bought_since_ref)

i.e. relative to the capital exposed since the reference.

Assumptions: fees are excluded (this measures price movement; fees live in cost basis and
realized P/L). Missing or non-positive inputs give None, never a guessed number.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.domain.enums import Side
from app.domain.holdings import held_quantity
from app.domain.pnl import PnlTrade
from app.domain.precision import exact

ZERO = Decimal(0)
HUNDRED = Decimal(100)


@dataclass(frozen=True)
class DailyChange:
    amount: Decimal
    pct: Decimal | None
    # Capital exposed since the reference; the denominator of pct. Kept for portfolio totals.
    base: Decimal


def daily_change(
    trades: Iterable[PnlTrade],
    price: Decimal | None,
    reference_price: Decimal | None,
    reference_at: datetime | None,
) -> DailyChange | None:
    """One symbol's change since `reference_at`. `trades` must all belong to that symbol."""
    if price is None or reference_price is None or reference_at is None or reference_price <= 0:
        return None
    trades = list(trades)
    before = [t for t in trades if t.executed_at < reference_at]
    since = [t for t in trades if t.executed_at >= reference_at]
    with exact():
        bought = sum((t.quantity * t.price for t in since if t.side is Side.BUY), ZERO)
        sold = sum((t.quantity * t.price for t in since if t.side is Side.SELL), ZERO)
        value_at_reference = held_quantity(before) * reference_price
        amount = held_quantity(trades) * price - value_at_reference - bought + sold
        base = value_at_reference + bought
        return DailyChange(amount, amount / base * HUNDRED if base > 0 else None, base)


def total_daily_change(changes: Iterable[DailyChange]) -> DailyChange | None:
    """Sum of per-symbol changes; None when no symbol has one."""
    changes = list(changes)
    if not changes:
        return None
    with exact():
        amount = sum((c.amount for c in changes), ZERO)
        base = sum((c.base for c in changes), ZERO)
        return DailyChange(amount, amount / base * HUNDRED if base > 0 else None, base)
