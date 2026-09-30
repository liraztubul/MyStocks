from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.domain.enums import Side
from app.domain.holdings import find_oversell, held_quantity

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


@dataclass
class FakeTrade:
    side: Side
    quantity: Decimal
    executed_at: datetime


def buy(qty: str, day: int = 0) -> FakeTrade:
    return FakeTrade(Side.BUY, Decimal(qty), T0 + timedelta(days=day))


def sell(qty: str, day: int = 0) -> FakeTrade:
    return FakeTrade(Side.SELL, Decimal(qty), T0 + timedelta(days=day))


def test_empty_list_holds_zero() -> None:
    assert held_quantity([]) == Decimal(0)
    assert find_oversell([]) is None


def test_multiple_buys_sum() -> None:
    assert held_quantity([buy("10"), buy("2.5", 1), buy("0.25", 2)]) == Decimal("12.75")


def test_multiple_sells_subtract() -> None:
    trades = [buy("10"), sell("3", 1), sell("1.5", 2)]
    assert held_quantity(trades) == Decimal("5.5")
    assert find_oversell(trades) is None


def test_sell_exactly_down_to_zero_is_allowed() -> None:
    trades = [buy("4"), sell("4", 1)]
    assert held_quantity(trades) == Decimal(0)
    assert find_oversell(trades) is None


def test_sell_more_than_held_is_an_oversell() -> None:
    too_big = sell("5", 1)
    oversell = find_oversell([buy("4"), too_big])
    assert oversell is not None
    assert oversell.sell is too_big
    assert oversell.held_before == Decimal(4)


def test_decimal_arithmetic_is_exact() -> None:
    # With floats 0.1 + 0.2 = 0.30000000000000004 and this sell would be rejected.
    assert find_oversell([buy("0.1"), buy("0.2", 1), sell("0.3", 2)]) is None


def test_sell_backdated_before_its_covering_buy_is_an_oversell() -> None:
    # The final total is fine (0), but on day 0 nothing was held yet.
    trades = [buy("5", 1), sell("5", 0)]
    assert held_quantity(trades) == Decimal(0)
    assert find_oversell(trades) is not None


def test_same_timestamp_buy_is_applied_before_sell() -> None:
    assert find_oversell([sell("5", 0), buy("5", 0)]) is None


def test_input_order_does_not_matter() -> None:
    assert find_oversell([sell("2", 2), buy("3", 0), sell("1", 1)]) is None
