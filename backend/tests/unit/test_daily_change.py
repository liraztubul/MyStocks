from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from app.domain.daily_change import daily_change, total_daily_change
from app.domain.enums import Side

D = Decimal
REF_AT = datetime(2026, 10, 5, 4, 0, tzinfo=timezone.utc)  # 00:00 New York (EDT)
BEFORE = REF_AT - timedelta(days=3)
TODAY = REF_AT + timedelta(hours=11)


@dataclass(frozen=True)
class FakeTrade:
    side: Side
    quantity: Decimal
    price: Decimal
    executed_at: datetime
    symbol: str = "AAPL"
    fee: Decimal = D(0)


def buy(qty: str, price: str, at: datetime = BEFORE, fee: str = "0") -> FakeTrade:
    return FakeTrade(Side.BUY, D(qty), D(price), at, fee=D(fee))


def sell(qty: str, price: str, at: datetime = TODAY) -> FakeTrade:
    return FakeTrade(Side.SELL, D(qty), D(price), at)


def test_worked_example_held_shares_plus_todays_buy_and_sell() -> None:
    # Held 10 from before; previous close 200. Today: buy 5 @ 204, sell 3 @ 206. Now 205.
    # change = 12*205 - 10*200 - 5*204 + 3*206 = 2460 - 2000 - 1020 + 618 = 58
    #        = 7 held through * (205-200) + 3 sold * (206-200) + 5 new * (205-204) = 35 + 18 + 5
    # base   = 10*200 + 5*204 = 3020, so pct = 58 / 3020 = 1.9205%
    trades = [buy("10", "150"), buy("5", "204", at=TODAY), sell("3", "206")]
    change = daily_change(trades, D("205"), D("200"), REF_AT)
    assert change is not None
    assert (change.amount, change.base) == (D("58"), D("3020"))
    assert change.pct is not None and change.pct.quantize(D("0.0001")) == D("1.9205")


def test_position_held_through_is_quantity_times_price_move() -> None:
    change = daily_change([buy("4", "50")], D("103"), D("100"), REF_AT)
    assert change is not None
    assert (change.amount, change.pct) == (D("12"), D("3"))


def test_position_opened_today_is_measured_from_the_buy_price_not_previous_close() -> None:
    # Previous close 100 is irrelevant: the shares didn't exist then.
    change = daily_change([buy("2", "110", at=TODAY)], D("115"), D("100"), REF_AT)
    assert change is not None
    assert (change.amount, change.base) == (D("10"), D("220"))
    assert change.pct is not None and change.pct.quantize(D("0.0001")) == D("4.5455")


def test_buy_fee_today_is_excluded() -> None:
    change = daily_change([buy("2", "110", at=TODAY, fee="9.99")], D("115"), D("100"), REF_AT)
    assert change is not None and change.amount == D("10")


def test_fully_sold_today_realizes_the_move_from_previous_close() -> None:
    change = daily_change([buy("10", "50"), sell("10", "98")], D("120"), D("100"), REF_AT)
    assert change is not None
    assert (change.amount, change.pct) == (D("-20"), D("-2"))


def test_bought_and_sold_entirely_today() -> None:
    change = daily_change([buy("3", "100", at=TODAY), sell("3", "104")], D("90"), D("95"), REF_AT)
    assert change is not None and change.amount == D("12")


def test_trade_exactly_at_reference_counts_as_since_reference() -> None:
    change = daily_change([buy("1", "101", at=REF_AT)], D("105"), D("100"), REF_AT)
    assert change is not None and change.amount == D("4")


def test_missing_inputs_degrade_to_none() -> None:
    trades = [buy("1", "100")]
    assert daily_change(trades, None, D("100"), REF_AT) is None
    assert daily_change(trades, D("100"), None, REF_AT) is None
    assert daily_change(trades, D("100"), D("100"), None) is None


def test_zero_or_negative_previous_close_degrades_to_none() -> None:
    assert daily_change([buy("1", "100")], D("100"), D("0"), REF_AT) is None
    assert daily_change([buy("1", "100")], D("100"), D("-1"), REF_AT) is None


def test_empty_history_has_zero_change_and_no_percentage() -> None:
    change = daily_change([], D("100"), D("90"), REF_AT)
    assert change is not None
    assert (change.amount, change.pct) == (D("0"), None)


def test_total_combines_amounts_and_bases() -> None:
    a = daily_change([buy("10", "1")], D("110"), D("100"), REF_AT)  # +100 on base 1000
    b = daily_change([buy("1", "1")], D("1900"), D("2000"), REF_AT)  # -100 on base 2000
    assert a is not None and b is not None
    total = total_daily_change([a, b])
    assert total is not None
    assert (total.amount, total.base, total.pct) == (D("0"), D("3000"), D("0"))


def test_total_of_nothing_is_none() -> None:
    assert total_daily_change([]) is None


# --- properties ---

amounts = st.decimals(min_value="0.0001", max_value="100000", places=4)


@st.composite
def held_before_reference(draw: st.DrawFn) -> list[FakeTrade]:
    buys = draw(st.lists(st.tuples(amounts, amounts), min_size=1, max_size=6))
    return [buy(str(q), str(p)) for q, p in buys]


@settings(max_examples=300)
@given(held_before_reference(), amounts, amounts)
def test_no_trades_since_reference_is_quantity_times_move(
    trades: list[FakeTrade], price: Decimal, reference: Decimal
) -> None:
    change = daily_change(trades, price, reference, REF_AT)
    quantity = sum((t.quantity for t in trades), D(0))
    assert change is not None
    assert change.amount == quantity * price - quantity * reference


@settings(max_examples=300)
@given(held_before_reference(), amounts)
def test_price_unchanged_since_reference_with_no_new_trades_is_zero(
    trades: list[FakeTrade], reference: Decimal
) -> None:
    change = daily_change(trades, reference, reference, REF_AT)
    assert change is not None and change.amount == 0


@settings(max_examples=300)
@given(
    held_before_reference(),
    st.lists(st.tuples(amounts, amounts), max_size=5),
    amounts,
    amounts,
)
def test_change_decomposes_into_held_new_and_sold_parts(
    held: list[FakeTrade],
    todays_buys: list[tuple[Decimal, Decimal]],
    price: Decimal,
    reference: Decimal,
) -> None:
    # Sell part of the held position today at the current price, plus some fresh buys.
    held_qty = sum((t.quantity for t in held), D(0))
    sold_qty = (held_qty / 2).quantize(D("0.0001"))
    trades = held + [buy(str(q), str(p), at=TODAY) for q, p in todays_buys]
    if sold_qty > 0:
        trades.append(sell(str(sold_qty), str(price)))

    change = daily_change(trades, price, reference, REF_AT)
    expected = held_qty * (price - reference) + sum((q * (price - p) for q, p in todays_buys), D(0))
    assert change is not None and change.amount == expected
