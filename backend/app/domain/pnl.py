"""P/L engine: replays a ledger into positions, realized P/L and (given prices) unrealized P/L.

Assumptions:
- Cost basis is average cost by default (see cost_basis.py); the strategy is swappable.
- Fees: a buy's fee is added to its cost basis; a sell's fee is subtracted from its proceeds.
  So realized P/L per sell = (sell_price - average_cost) * quantity - sell_fee.
- Unrealized P/L = (current_price - average_cost) * held_quantity; its % is relative to the
  cost basis of what's held (fees included).
- Everything is USD; there is no currency conversion.
- No rounding: all arithmetic runs in a 60-significant-digit context, wide enough that
  products of Numeric(28, 10) values are exact. Round only when presenting.

Pure functions over already-fetched trades and a price lookup; no DB, HTTP or framework code.
"""

from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import Generic, Protocol, TypeVar

from app.domain.cost_basis import AverageCost, CostBasisFactory
from app.domain.enums import Side
from app.domain.holdings import Trade, chronological
from app.domain.precision import exact

ZERO = Decimal(0)
HUNDRED = Decimal(100)


class PnlTrade(Trade, Protocol):
    symbol: str
    price: Decimal
    fee: Decimal


T = TypeVar("T", bound=PnlTrade)


class OversoldLedgerError(ValueError):
    """A symbol's history sells more than it held at some point (e.g. a buy was deleted)."""

    def __init__(self, symbol: str) -> None:
        super().__init__(f"{symbol} history sells more than it held")
        self.symbol = symbol


@dataclass(frozen=True)
class RealizedSale(Generic[T]):
    trade: T
    average_cost: Decimal
    cost_basis: Decimal
    proceeds: Decimal
    realized: Decimal


@dataclass(frozen=True)
class Valuation:
    price: Decimal
    market_value: Decimal
    unrealized: Decimal
    unrealized_pct: Decimal | None


@dataclass(frozen=True)
class Position(Generic[T]):
    symbol: str
    quantity: Decimal
    average_cost: Decimal
    cost_basis: Decimal
    realized: Decimal
    sales: tuple[RealizedSale[T], ...]

    def value_at(self, price: Decimal) -> Valuation:
        with exact():
            market_value = price * self.quantity
            unrealized = market_value - self.cost_basis
            pct = unrealized / self.cost_basis * HUNDRED if self.cost_basis else None
        return Valuation(price, market_value, unrealized, pct)


def position_pnl(
    symbol: str, trades: Iterable[T], cost_basis: CostBasisFactory = AverageCost
) -> Position[T]:
    """Replay one symbol's trades. All trades must belong to `symbol`."""
    strategy = cost_basis()
    sales: list[RealizedSale[T]] = []
    with exact():
        # Price and fee complete the tiebreak, so identical-timestamp trades always replay in
        # the same order whatever order they were loaded in.
        for trade in chronological(trades, tiebreak=lambda t: (t.price, t.fee)):
            if trade.side is Side.BUY:
                strategy.buy(trade.quantity, trade.price, trade.fee)
                continue
            if trade.quantity > strategy.quantity:
                raise OversoldLedgerError(symbol)
            average = strategy.average_cost
            removed = strategy.sell(trade.quantity)
            proceeds = trade.quantity * trade.price - trade.fee
            sales.append(RealizedSale(trade, average, removed, proceeds, proceeds - removed))
        return Position(
            symbol=symbol,
            quantity=strategy.quantity,
            average_cost=strategy.average_cost,
            cost_basis=strategy.total_cost,
            realized=sum((s.realized for s in sales), ZERO),
            sales=tuple(sales),
        )


def positions_by_symbol(
    trades: Iterable[T], cost_basis: CostBasisFactory = AverageCost
) -> dict[str, Position[T]]:
    grouped: dict[str, list[T]] = defaultdict(list)
    for trade in trades:
        grouped[trade.symbol].append(trade)
    return {symbol: position_pnl(symbol, grouped[symbol], cost_basis) for symbol in sorted(grouped)}


@dataclass(frozen=True)
class Holding(Generic[T]):
    position: Position[T]
    # None when no price was available; the holding still counts toward cost basis.
    valuation: Valuation | None
    allocation_pct: Decimal | None


@dataclass(frozen=True)
class Portfolio(Generic[T]):
    holdings: tuple[Holding[T], ...]
    positions: dict[str, Position[T]]
    total_cost_basis: Decimal
    # Market value and unrealized cover priced holdings only; see unpriced_symbols.
    total_market_value: Decimal
    total_unrealized: Decimal
    total_unrealized_pct: Decimal | None
    total_realized: Decimal
    unpriced_symbols: tuple[str, ...]


def total_realized(positions: Iterable[Position[T]]) -> Decimal:
    with exact():
        return sum((p.realized for p in positions), ZERO)


def _allocation(valuation: Valuation | None, total_market_value: Decimal) -> Decimal | None:
    if valuation is None or not total_market_value:
        return None
    return valuation.market_value / total_market_value * HUNDRED


def portfolio_pnl(
    trades: Iterable[T],
    price_of: Callable[[str], Decimal | None],
    cost_basis: CostBasisFactory = AverageCost,
) -> Portfolio[T]:
    return value_portfolio(positions_by_symbol(trades, cost_basis), price_of)


def value_portfolio(
    positions: dict[str, Position[T]], price_of: Callable[[str], Decimal | None]
) -> Portfolio[T]:
    """Value already-replayed positions; price_of is asked only about open positions."""
    open_positions = [p for p in positions.values() if p.quantity > 0]

    with exact():
        valuations: dict[str, Valuation | None] = {}
        for position in open_positions:
            price = price_of(position.symbol)
            valuations[position.symbol] = None if price is None else position.value_at(price)

        priced = {s: v for s, v in valuations.items() if v is not None}
        total_market_value = sum((v.market_value for v in priced.values()), ZERO)
        total_unrealized = sum((v.unrealized for v in priced.values()), ZERO)
        priced_cost_basis = sum((positions[s].cost_basis for s in priced), ZERO)

        holdings = tuple(
            Holding(
                position=p,
                valuation=valuations[p.symbol],
                allocation_pct=_allocation(valuations[p.symbol], total_market_value),
            )
            for p in open_positions
        )
        return Portfolio(
            holdings=holdings,
            positions=positions,
            total_cost_basis=sum((p.cost_basis for p in open_positions), ZERO),
            total_market_value=total_market_value,
            total_unrealized=total_unrealized,
            total_unrealized_pct=(
                total_unrealized / priced_cost_basis * HUNDRED if priced_cost_basis else None
            ),
            total_realized=total_realized(positions.values()),
            unpriced_symbols=tuple(s for s, v in valuations.items() if v is None),
        )
