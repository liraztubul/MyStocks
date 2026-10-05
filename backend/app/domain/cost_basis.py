"""Cost-basis strategies: how a position's cost is tracked across buys and sells.

A strategy instance tracks one symbol. The P/L engine feeds it trades in replay order and asks
it, on each sell, how much cost basis leaves the position. That's the only thing that differs
between methods (average cost vs FIFO lots), so swapping one in is a new class, not an engine
change. Only average cost exists today.
"""

from collections.abc import Callable
from decimal import Decimal
from typing import Protocol

from app.domain.precision import exact

ZERO = Decimal(0)


class CostBasisStrategy(Protocol):
    @property
    def quantity(self) -> Decimal: ...

    @property
    def total_cost(self) -> Decimal:
        """Cost basis of the units still held, fees included."""
        ...

    @property
    def average_cost(self) -> Decimal: ...

    def buy(self, quantity: Decimal, price: Decimal, fee: Decimal) -> None: ...

    def sell(self, quantity: Decimal) -> Decimal:
        """Remove `quantity` units and return the cost basis that left with them."""
        ...


CostBasisFactory = Callable[[], CostBasisStrategy]


class AverageCost:
    """Weighted average cost; the average moves only on buys.

    State is (quantity, total cost) rather than a stored average: a buy is then exact
    addition, average = total / quantity reproduces
    new_avg = (held * avg + qty * price + fee) / (held + qty), and selling the whole position
    removes exactly the total, so a later re-buy starts from a clean zero.
    """

    def __init__(self) -> None:
        self._quantity = ZERO
        self._total_cost = ZERO

    @property
    def quantity(self) -> Decimal:
        return self._quantity

    @property
    def total_cost(self) -> Decimal:
        return self._total_cost

    @property
    def average_cost(self) -> Decimal:
        with exact():
            return self._total_cost / self._quantity if self._quantity else ZERO

    def buy(self, quantity: Decimal, price: Decimal, fee: Decimal) -> None:
        with exact():
            self._quantity += quantity
            self._total_cost += quantity * price + fee

    def sell(self, quantity: Decimal) -> Decimal:
        if quantity > self._quantity:
            raise ValueError(f"cannot sell {quantity}: only {self._quantity} held")
        with exact():
            if quantity == self._quantity:
                removed = self._total_cost
            else:
                # Proportional removal leaves total/quantity (the average) unchanged.
                removed = self._total_cost * quantity / self._quantity
            self._quantity -= quantity
            self._total_cost -= removed
        return removed
