from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.domain.enums import Side
from app.domain.pnl import OversoldLedgerError, portfolio_pnl, position_pnl

T0 = datetime(2026, 1, 1, 15, 0, tzinfo=timezone.utc)
D = Decimal


@dataclass
class FakeTrade:
    symbol: str
    side: Side
    quantity: Decimal
    price: Decimal
    fee: Decimal
    executed_at: datetime


def buy(qty: str, price: str, fee: str = "0", day: int = 0, symbol: str = "AAPL") -> FakeTrade:
    return FakeTrade(symbol, Side.BUY, D(qty), D(price), D(fee), T0 + timedelta(days=day))


def sell(qty: str, price: str, fee: str = "0", day: int = 0, symbol: str = "AAPL") -> FakeTrade:
    return FakeTrade(symbol, Side.SELL, D(qty), D(price), D(fee), T0 + timedelta(days=day))


def test_worked_example_two_buys_partial_sell_then_valued_at_120() -> None:
    trades = [
        # Buy 10 @ 100, fee 5 -> cost 10*100 + 5 = 1005, average 1005 / 10 = 100.50
        buy("10", "100", fee="5", day=0),
        # Buy 5 @ 130, fee 2.50 -> cost 1005 + 5*130 + 2.50 = 1657.50, average 1657.50 / 15 = 110.50
        buy("5", "130", fee="2.50", day=1),
        # Sell 6 @ 150, fee 3 -> realized (150 - 110.50) * 6 - 3 = 237 - 3 = 234.
        # The average stays 110.50; 9 left with cost basis 9 * 110.50 = 994.50.
        sell("6", "150", fee="3", day=2),
    ]
    position = position_pnl("AAPL", trades)
    assert position.quantity == D("9")
    assert position.average_cost == D("110.5")
    assert position.cost_basis == D("994.5")
    assert position.realized == D("234")
    [sale] = position.sales
    assert (sale.average_cost, sale.cost_basis, sale.proceeds) == (D("110.5"), D("663"), D("897"))

    # At 120: market value 9 * 120 = 1080, unrealized 1080 - 994.50 = 85.50,
    # which is 85.50 / 994.50 = 8.5972...% of the cost basis.
    valuation = position.value_at(D("120"))
    assert valuation.market_value == D("1080")
    assert valuation.unrealized == D("85.5")
    assert valuation.unrealized_pct is not None
    assert valuation.unrealized_pct.quantize(D("0.0001")) == D("8.5973")

    # Cross-check: total P/L 234 + 85.50 = 319.50 equals cash in minus cash out plus value:
    # sale proceeds 897 + market value 1080 - total paid 1657.50 = 319.50.
    assert position.realized + valuation.unrealized == D("897") + D("1080") - D("1657.5")


def test_empty_history() -> None:
    position = position_pnl("AAPL", [])
    assert (position.quantity, position.average_cost, position.cost_basis, position.realized) == (
        0,
        0,
        0,
        0,
    )
    assert position.sales == ()


def test_single_buy() -> None:
    position = position_pnl("AAPL", [buy("4", "25.25")])
    assert (position.quantity, position.average_cost, position.cost_basis) == (
        D("4"),
        D("25.25"),
        D("101"),
    )
    assert position.realized == 0


def test_multiple_buys_at_different_prices_weight_the_average() -> None:
    position = position_pnl("AAPL", [buy("1", "100"), buy("3", "200", day=1)])
    assert position.average_cost == D("175")


def test_buy_fee_is_part_of_cost_basis() -> None:
    position = position_pnl("AAPL", [buy("4", "100", fee="10")])
    assert (position.cost_basis, position.average_cost) == (D("410"), D("102.5"))


def test_partial_sell_keeps_average_and_realizes_the_difference() -> None:
    position = position_pnl("AAPL", [buy("10", "50"), sell("4", "60", day=1)])
    assert (position.quantity, position.average_cost, position.cost_basis) == (
        D("6"),
        D("50"),
        D("300"),
    )
    assert position.realized == D("40")


def test_sell_fee_reduces_proceeds() -> None:
    position = position_pnl("AAPL", [buy("10", "50"), sell("10", "60", fee="7", day=1)])
    assert position.realized == D("93")
    assert position.sales[0].proceeds == D("593")


def test_selling_at_a_loss_realizes_a_negative_amount() -> None:
    position = position_pnl("AAPL", [buy("2", "100"), sell("2", "80", fee="1", day=1)])
    assert position.realized == D("-41")


def test_sell_to_zero_then_rebuy_starts_a_fresh_average() -> None:
    position = position_pnl(
        "AAPL",
        [buy("10", "100"), sell("10", "120", day=1), buy("5", "200", day=2)],
    )
    assert (position.quantity, position.average_cost, position.cost_basis) == (
        D("5"),
        D("200"),
        D("1000"),
    )
    assert position.realized == D("200")


def test_average_with_repeating_decimals_sells_to_exactly_zero() -> None:
    # 100 / 3 is not representable; selling everything must still leave no cost residue.
    position = position_pnl(
        "AAPL", [buy("3", "33.33", fee="0.01"), sell("1", "40", day=1), sell("2", "40", day=2)]
    )
    assert (position.quantity, position.cost_basis) == (0, 0)
    assert position.realized == D("120") - D("100")


def test_same_timestamp_buy_is_replayed_before_sell() -> None:
    position = position_pnl("AAPL", [sell("5", "12"), buy("5", "10")])
    assert position.quantity == 0
    assert position.realized == D("10")


def test_oversold_history_is_an_explicit_error() -> None:
    with pytest.raises(OversoldLedgerError) as exc:
        position_pnl("AAPL", [buy("1", "10"), sell("2", "10", day=1)])
    assert exc.value.symbol == "AAPL"


def test_unrealized_with_price_above_average() -> None:
    valuation = position_pnl("AAPL", [buy("4", "50")]).value_at(D("60"))
    assert (valuation.market_value, valuation.unrealized, valuation.unrealized_pct) == (
        D("240"),
        D("40"),
        D("20"),
    )


def test_unrealized_with_price_below_average() -> None:
    valuation = position_pnl("AAPL", [buy("4", "50")]).value_at(D("45"))
    assert (valuation.unrealized, valuation.unrealized_pct) == (D("-20"), D("-10"))


def test_full_precision_is_kept_where_default_context_would_round() -> None:
    qty, price = D("12345678.1234567891"), D("98765.4321098765")
    # The exact product has 36 significant digits, so the default 28-digit context rounds it.
    exact = D("1219326234552.65901112639108754615")
    assert qty * price != exact
    assert position_pnl("AAPL", [buy(str(qty), str(price))]).cost_basis == exact


def test_symbols_are_independent() -> None:
    portfolio = portfolio_pnl(
        [
            buy("10", "100", symbol="AAPL"),
            buy("2", "1000", symbol="BTC"),
            sell("1", "1500", day=1, symbol="BTC"),
        ],
        price_of={"AAPL": D("110"), "BTC": D("2000")}.get,
    )
    aapl, btc = portfolio.positions["AAPL"], portfolio.positions["BTC"]
    assert (aapl.quantity, aapl.average_cost, aapl.realized) == (D("10"), D("100"), 0)
    assert (btc.quantity, btc.average_cost, btc.realized) == (D("1"), D("1000"), D("500"))


def test_portfolio_totals_and_allocation() -> None:
    portfolio = portfolio_pnl(
        [
            buy("10", "100", symbol="AAPL"),
            buy("1", "1000", symbol="BTC"),
            buy("5", "10", symbol="OLD"),
            sell("5", "12", day=1, symbol="OLD"),
        ],
        price_of={"AAPL": D("150"), "BTC": D("500")}.get,
    )
    # Fully closed positions drop out of holdings but keep their realized P/L.
    assert [h.position.symbol for h in portfolio.holdings] == ["AAPL", "BTC"]
    assert portfolio.total_market_value == D("2000")
    assert portfolio.total_cost_basis == D("2000")
    assert portfolio.total_unrealized == D("0")
    assert portfolio.total_realized == D("10")
    assert [h.allocation_pct for h in portfolio.holdings] == [D("75"), D("25")]


def test_unpriced_holding_is_reported_not_dropped() -> None:
    portfolio = portfolio_pnl(
        [buy("10", "100", symbol="AAPL"), buy("1", "1000", symbol="XYZ")],
        price_of={"AAPL": D("110")}.get,
    )
    xyz = next(h for h in portfolio.holdings if h.position.symbol == "XYZ")
    assert (xyz.valuation, xyz.allocation_pct) == (None, None)
    assert portfolio.unpriced_symbols == ("XYZ",)
    # Totals cover what could be priced; cost basis still counts everything held.
    assert (portfolio.total_market_value, portfolio.total_unrealized) == (D("1100"), D("100"))
    assert portfolio.total_unrealized_pct == D("10")
    assert portfolio.total_cost_basis == D("2000")
