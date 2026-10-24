"""Stock splits in the ledger replay. Synthetic trades; every expected value is worked by hand."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from app.domain.daily_change import daily_change
from app.domain.enums import Side
from app.domain.holdings import find_oversell, held_before, held_quantity, ledger
from app.domain.pnl import position_pnl, positions_by_symbol

D = Decimal


@dataclass(frozen=True)
class FakeTrade:
    side: Side
    quantity: Decimal
    price: Decimal
    executed_at: datetime
    fee: Decimal = D(0)
    symbol: str = "AAPL"


@dataclass(frozen=True)
class FakeSplit:
    effective_date: date
    numerator: Decimal
    denominator: Decimal
    symbol: str = "AAPL"


def at(day: date, hour_utc: int = 15) -> datetime:
    # 15:00 UTC is 10:00 or 11:00 in New York: the same New York date.
    return datetime(day.year, day.month, day.day, hour_utc, tzinfo=UTC)


def buy(qty: str, price: str, day: date, fee: str = "0") -> FakeTrade:
    return FakeTrade(Side.BUY, D(qty), D(price), at(day), D(fee))


def sell(qty: str, price: str, day: date, fee: str = "0") -> FakeTrade:
    return FakeTrade(Side.SELL, D(qty), D(price), at(day), D(fee))


def split(day: date, ratio: str) -> FakeSplit:
    numerator, denominator = ratio.split(":")
    return FakeSplit(day, D(numerator), D(denominator))


JAN5, FEB2, MAR2, APR1 = date(2026, 1, 5), date(2026, 2, 2), date(2026, 3, 2), date(2026, 4, 1)


def test_one_forward_split() -> None:
    # 10 @ 400 = 4000. 4:1 -> 40 shares, cost still 4000, average 4000 / 40 = 100.
    p = position_pnl("AAPL", [buy("10", "400", JAN5)], splits=[split(FEB2, "4:1")])
    assert (p.quantity, p.cost_basis, p.average_cost, p.realized) == (D(40), D(4000), D(100), 0)


def test_two_splits_with_a_buy_between() -> None:
    # 3 @ 600 = 1800. 2:1 -> 6 shares, average 300. Buy 4 @ 310 = 1240 -> 10 shares, cost 3040,
    # average 304. 3:1 -> 30 shares, cost 3040, average 3040 / 30 = 101.333...
    p = position_pnl(
        "AAPL",
        [buy("3", "600", JAN5), buy("4", "310", MAR2)],
        splits=[split(FEB2, "2:1"), split(APR1, "3:1")],
    )
    assert (p.quantity, p.cost_basis) == (D(30), D(3040))
    assert p.average_cost.quantize(D("0.0001")) == D("101.3333")


def test_reverse_split() -> None:
    # 250 @ 2 = 500. 1:10 -> 25 shares, cost 500, average 20.
    p = position_pnl("AAPL", [buy("250", "2", JAN5)], splits=[split(FEB2, "1:10")])
    assert (p.quantity, p.cost_basis, p.average_cost) == (D(25), D(500), D(20))


def test_split_on_the_first_trades_day_comes_before_it() -> None:
    # The buy on the ex-date is already in post-split shares: the split finds nothing to convert.
    p = position_pnl("AAPL", [buy("10", "100", FEB2)], splits=[split(FEB2, "4:1")])
    assert (p.quantity, p.average_cost) == (D(10), D(100))
    assert held_before([buy("10", "100", FEB2)], [], FEB2) == 0


def test_split_on_the_last_trades_day_lets_a_same_day_sell_use_it() -> None:
    # Held 1 before; the ex-date's sell of 4 is in post-split shares (1 * 4 = 4).
    trades = [buy("1", "400", JAN5), sell("4", "110", FEB2)]
    splits = [split(FEB2, "4:1")]
    assert find_oversell(trades, splits) is None
    p = position_pnl("AAPL", trades, splits=splits)
    # Average 400 / 4 = 100; realized (110 - 100) * 4 = 40.
    assert (p.quantity, p.cost_basis, p.realized) == (D(0), D(0), D(40))


def test_a_split_comes_before_trades_of_its_day_even_before_midnight_utc() -> None:
    # 03:00 UTC on 3 Feb is 22:00 on 2 Feb in New York: the ex-date's trade, after the split.
    late = FakeTrade(Side.SELL, D(4), D(110), datetime(2026, 2, 3, 3, tzinfo=UTC))
    steps = ledger([late, buy("1", "400", JAN5)], [split(FEB2, "4:1")])
    assert [type(s).__name__ for s in steps] == ["TradeStep", "SplitStep", "TradeStep"]


def test_sell_after_the_split() -> None:
    # 10 @ 400 = 4000 -> 4:1 -> 40 @ 100. Sell 20 @ 120, fee 5: proceeds 2400 - 5 = 2395,
    # cost out 20 * 100 = 2000, realized 395. Left 20, cost 2000.
    p = position_pnl(
        "AAPL",
        [buy("10", "400", JAN5), sell("20", "120", MAR2, fee="5")],
        splits=[split(FEB2, "4:1")],
    )
    assert (p.quantity, p.cost_basis, p.realized) == (D(20), D(2000), D(395))
    assert p.sales[0].average_cost == D(100)


def test_a_sell_before_the_split_keeps_its_realized_pl() -> None:
    # 10 @ 400; sell 5 @ 500: realized (500 - 400) * 5 = 500, cost left 2000.
    # 4:1 -> 20 shares, cost 2000, average 100; realized still 500.
    trades = [buy("10", "400", JAN5), sell("5", "500", JAN5 + timedelta(days=7))]
    p = position_pnl("AAPL", trades, splits=[split(FEB2, "4:1")])
    assert (p.quantity, p.cost_basis, p.average_cost, p.realized) == (
        D(20),
        D(2000),
        D(100),
        D(500),
    )


def test_fractional_shares_round_down_and_sell_all_closes() -> None:
    # 10 @ 9 = 90. 1:3 -> 10 / 3 = 3.3333333333 (down to 10 places); cost stays 90.
    trades = [buy("10", "9", JAN5)]
    splits = [split(FEB2, "1:3")]
    p = position_pnl("AAPL", trades, splits=splits)
    assert (p.quantity, p.cost_basis) == (D("3.3333333333"), D(90))
    # Selling exactly that closes the position: realized 3.3333333333 * 30 - 90 = 9.999999999.
    closed = position_pnl("AAPL", [*trades, sell("3.3333333333", "30", MAR2)], splits=splits)
    assert (closed.quantity, closed.cost_basis) == (D(0), D(0))
    assert closed.realized == D("9.999999999")


def test_oversell_counts_through_splits() -> None:
    splits = [split(FEB2, "4:1")]
    assert find_oversell([buy("1", "400", JAN5), sell("4", "100", MAR2)], splits) is None
    too_many = find_oversell([buy("1", "400", JAN5), sell("5", "100", MAR2)], splits)
    assert too_many is not None and too_many.held_before == D(4)
    # Dated the day before the ex-date, the sell is in pre-split shares: only 1 held.
    early = find_oversell(
        [buy("1", "400", JAN5), sell("4", "100", FEB2 - timedelta(days=1))], splits
    )
    assert early is not None and early.held_before == D(1)


def test_a_reverse_split_can_make_a_later_sell_an_oversell() -> None:
    trades = [buy("50", "2", JAN5), sell("10", "30", MAR2)]
    assert find_oversell(trades, [split(FEB2, "1:10")]) is not None  # 50 -> 5 < 10


def test_held_quantity_and_held_before() -> None:
    trades = [buy("10", "400", JAN5), buy("2", "100", MAR2)]
    splits = [split(FEB2, "4:1")]
    assert held_quantity(trades, splits) == D(42)
    assert held_before(trades, splits, FEB2) == D(10)
    assert held_before(trades, splits, MAR2) == D(40)


def test_positions_by_symbol_keeps_splits_to_their_symbol() -> None:
    msft = FakeTrade(Side.BUY, D(1), D(300), at(JAN5), symbol="MSFT")
    positions = positions_by_symbol([buy("1", "400", JAN5), msft], splits=[split(FEB2, "4:1")])
    assert (positions["AAPL"].quantity, positions["MSFT"].quantity) == (D(4), D(1))


REF_AT = datetime(2026, 3, 2, 5, tzinfo=UTC)  # 00:00 New York (EST) on MAR2


def test_daily_change_counts_post_split_shares() -> None:
    # Held 10 bought 5 Jan; 4:1 on 2 Feb -> 40 at the reference. Previous close 100, now 103.
    # change = 40 * 103 - 40 * 100 = 120; base 4000; pct 3.
    change = daily_change([buy("10", "400", JAN5)], D(103), D(100), REF_AT, [split(FEB2, "4:1")])
    assert change is not None and (change.amount, change.pct) == (D(120), D(3))


def test_no_daily_change_on_the_session_a_split_takes_effect_or_later() -> None:
    trades = [buy("10", "400", JAN5)]
    assert daily_change(trades, D(103), D(400), REF_AT, [split(MAR2, "4:1")]) is None
    assert daily_change(trades, D(103), D(400), REF_AT, [split(APR1, "4:1")]) is None
