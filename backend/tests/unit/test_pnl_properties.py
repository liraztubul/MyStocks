import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from app.domain.cost_basis import AverageCost
from app.domain.enums import Side
from app.domain.holdings import held_quantity
from app.domain.pnl import portfolio_pnl, position_pnl
from app.domain.precision import exact

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
ZERO = Decimal(0)
# Only proportional cost removal on partial sells divides; at 60 significant digits its
# rounding is far below anything a ledger of Numeric(28, 10) values can show.
TOLERANCE = Decimal("1e-30")

quantities = st.decimals(min_value="0.0001", max_value="100000", places=4)
prices = st.decimals(min_value="0.0001", max_value="100000", places=4)
fees = st.decimals(min_value="0", max_value="50", places=2)


@dataclass(frozen=True)
class FakeTrade:
    symbol: str
    side: Side
    quantity: Decimal
    price: Decimal
    fee: Decimal
    executed_at: datetime


@st.composite
def symbol_history(draw: st.DrawFn, symbol: str) -> list[FakeTrade]:
    """A valid history: every sell is covered by what was held when it was generated.

    Steps of 0 days produce same-timestamp trades. The engine replays those buys-first and
    sells by quantity; that only ever raises the balance seen by each sell, so they stay valid.
    """
    trades: list[FakeTrade] = []
    held = ZERO
    day = 0
    for _ in range(draw(st.integers(min_value=1, max_value=12))):
        day += draw(st.integers(min_value=0, max_value=2))
        side = draw(st.sampled_from([Side.BUY, Side.SELL])) if held > 0 else Side.BUY
        if side is Side.BUY:
            quantity = draw(quantities)
            held += quantity
        else:
            quantity = draw(
                st.one_of(st.just(held), st.decimals(min_value="0.0001", max_value=held, places=4))
            )
            held -= quantity
        trades.append(
            FakeTrade(symbol, side, quantity, draw(prices), draw(fees), T0 + timedelta(days=day))
        )
    return trades


@st.composite
def ledgers(draw: st.DrawFn) -> list[FakeTrade]:
    symbols = draw(st.lists(st.sampled_from(["AAPL", "BTC", "ETH"]), min_size=1, unique=True))
    return [trade for symbol in symbols for trade in draw(symbol_history(symbol))]


def signed(trades: list[FakeTrade], side: Side) -> Decimal:
    return sum((t.quantity for t in trades if t.side is side), ZERO)


@settings(max_examples=300)
@given(ledgers())
def test_held_quantity_equals_buys_minus_sells(trades: list[FakeTrade]) -> None:
    for symbol, position in portfolio_pnl(trades, lambda _: None).positions.items():
        own = [t for t in trades if t.symbol == symbol]
        assert position.quantity == signed(own, Side.BUY) - signed(own, Side.SELL)
        assert position.quantity == held_quantity(own)


@settings(max_examples=300)
@given(symbol_history("AAPL"), prices)
def test_total_pnl_matches_cash_flows(trades: list[FakeTrade], current_price: Decimal) -> None:
    position = position_pnl("AAPL", trades)
    valuation = position.value_at(current_price)
    # The reference arithmetic needs the engine's precision too, or it becomes the rounding error.
    with exact():
        paid = sum((t.quantity * t.price + t.fee for t in trades if t.side is Side.BUY), ZERO)
        received = sum((t.quantity * t.price - t.fee for t in trades if t.side is Side.SELL), ZERO)

        # Realized + unrealized is everything received plus what's still held, minus all paid.
        total_pnl = position.realized + valuation.unrealized
        assert abs(total_pnl - (received + valuation.market_value - paid)) <= TOLERANCE
        # Equivalently: what's paid either left with a sale or still sits in the cost basis.
        removed = sum((s.cost_basis for s in position.sales), ZERO)
        assert abs(removed + position.cost_basis - paid) <= TOLERANCE


@settings(max_examples=300)
@given(ledgers(), st.randoms(use_true_random=False))
def test_result_does_not_depend_on_input_order(trades: list[FakeTrade], rng: random.Random) -> None:
    shuffled = trades[:]
    rng.shuffle(shuffled)
    price_of = {"AAPL": Decimal("150"), "BTC": Decimal("60000"), "ETH": Decimal("3000")}.get
    assert portfolio_pnl(shuffled, price_of) == portfolio_pnl(trades, price_of)


@settings(max_examples=300)
@given(ledgers())
def test_average_cost_and_cost_basis_are_never_negative(trades: list[FakeTrade]) -> None:
    for position in portfolio_pnl(trades, lambda _: None).positions.values():
        assert position.average_cost >= 0
        assert position.cost_basis >= 0
        assert all(sale.average_cost > 0 for sale in position.sales)
        if position.quantity == 0:
            assert (position.average_cost, position.cost_basis) == (ZERO, ZERO)


@settings(max_examples=300)
@given(
    st.lists(st.tuples(quantities, prices, fees), min_size=1, max_size=8),
    st.decimals(min_value="0.0001", max_value="1", places=4),
)
def test_a_partial_sell_never_moves_the_average(
    buys: list[tuple[Decimal, Decimal, Decimal]], fraction: Decimal
) -> None:
    strategy = AverageCost()
    for quantity, price, fee in buys:
        strategy.buy(quantity, price, fee)
    before = strategy.average_cost
    sold = min(strategy.quantity, (strategy.quantity * fraction).quantize(Decimal("0.0001")))
    if sold == 0 or sold == strategy.quantity:
        return
    strategy.sell(sold)
    with exact():
        assert abs(strategy.average_cost - before) <= TOLERANCE
