"""Transient stock history: split math, the request budget and the
service. Every bar here is synthetic; expected values are worked out by hand in the comments."""

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from app.market_data.provider import (
    IncompleteResponseError,
    ProviderUnavailableError,
    RateLimitedError,
    RawStockBar,
    SymbolNotFoundError,
)
from app.market_data.stock_history import (
    RATE_LIMIT_COOLDOWN_SECONDS,
    AdjustedBar,
    RequestBudget,
    Split,
    StockHistoryService,
    StockSeries,
    provider_ticker,
    split_adjust,
)

D = date(2026, 3, 2)  # a Monday


def bars(*rows: tuple[str, str]) -> list[RawStockBar]:
    """(close, split factor) per consecutive day."""
    return [
        RawStockBar(D + timedelta(days=i), Decimal(close), Decimal(factor))
        for i, (close, factor) in enumerate(rows)
    ]


def closes(adjusted: Sequence[AdjustedBar]) -> list[Decimal]:
    return [b.close for b in adjusted]


def dec(*values: str) -> list[Decimal]:
    return [Decimal(v) for v in values]


# --- Split math: a_i = c_i / product of f_j for later bars j > i ---------------------------------


def test_no_split_leaves_closes_as_they_are() -> None:
    assert closes(split_adjust(bars(("10.5", "1"), ("11", "1"), ("12.25", "1")))) == dec(
        "10.5", "11", "12.25"
    )


def test_ex_date_bar_is_not_divided_by_its_own_factor() -> None:
    # 4:1 on the third bar: the two earlier bars / 4 (400 -> 100, 404 -> 101); the ex-date bar
    # (already post-split) and the one after stay.
    adjusted = split_adjust(bars(("400", "1"), ("404", "1"), ("101", "4"), ("102", "1")))
    assert closes(adjusted) == dec("100", "101", "101", "102")
    assert [b.day for b in adjusted] == [D + timedelta(days=i) for i in range(4)]


def test_two_splits_multiply() -> None:
    # 2:1 on bar 3, 3:1 on bar 5. Bars 1-2 / (2 * 3) = / 6 (600 -> 100, 612 -> 102); bars 3-4 / 3
    # (306 -> 102, 300 -> 100); bars 5-6 unchanged.
    adjusted = split_adjust(
        bars(("600", "1"), ("612", "1"), ("306", "2"), ("300", "1"), ("100", "3"), ("101", "1"))
    )
    assert closes(adjusted) == dec("100", "102", "102", "100", "100", "101")


def test_reverse_split_raises_earlier_closes() -> None:
    # 1:10 reverse split (factor 0.1) on bar 3: earlier bars / 0.1 = * 10 (10 -> 100, 11 -> 110).
    adjusted = split_adjust(bars(("10", "1"), ("11", "1"), ("100", "0.1"), ("102", "1")))
    assert closes(adjusted) == dec("100", "110", "100", "102")


def test_split_on_the_first_bar_adjusts_nothing_in_range() -> None:
    # Nothing earlier in the range to divide; the factor is still reported as a split.
    raw = bars(("50", "2"), ("51", "1"))
    assert closes(split_adjust(raw)) == dec("50", "51")


def test_split_on_the_last_bar_divides_every_earlier_bar() -> None:
    # 2:1 on the last bar: 200 -> 100, 204 -> 102; the last bar stays 103.
    assert closes(split_adjust(bars(("200", "1"), ("204", "1"), ("103", "2")))) == dec(
        "100", "102", "103"
    )


def test_results_are_exact_decimals_rounded_half_even_to_ten_places() -> None:
    # 3:1: 100 / 3 = 33.333... -> 33.3333333333; 200 / 3 -> 66.6666666667.
    adjusted = split_adjust(bars(("100", "1"), ("200", "1"), ("70", "3")))
    assert closes(adjusted) == dec("33.3333333333", "66.6666666667", "70")
    assert all(isinstance(c, Decimal) for c in closes(adjusted))
    assert str(adjusted[0].close) == "33.3333333333"


@pytest.mark.parametrize("bad", [("10", "0"), ("10", "-2"), ("0", "1"), ("-5", "1")])
def test_a_zero_or_negative_factor_or_close_is_a_provider_error(bad: tuple[str, str]) -> None:
    with pytest.raises(ProviderUnavailableError):
        split_adjust(bars(("20", "1"), bad, ("21", "1")))


def test_marker_prices_are_adjusted_like_the_line() -> None:
    series = StockSeries(
        "fake",
        [],
        [Split(D + timedelta(days=2), Decimal(2)), Split(D + timedelta(days=4), Decimal(3))],
    )
    # Before both splits: / 6. On the first ex-date (already post-split): / 3 only.
    # After both: as is.
    assert series.chart_price(Decimal("600"), D) == Decimal("100")
    assert series.chart_price(Decimal("306"), D + timedelta(days=2)) == Decimal("102")
    assert series.chart_price(Decimal("101"), D + timedelta(days=5)) == Decimal("101")


def test_tickers_use_dashes_for_share_classes() -> None:
    assert provider_ticker(" brk.b ") == "BRK-B"
    assert provider_ticker("AAPL") == "AAPL"


# --- Request budget (counts only) ----------------------------------------------------------------


class Ticker:
    def __init__(self) -> None:
        self.seconds = 0.0

    def __call__(self) -> float:
        return self.seconds


def test_hourly_budget_is_a_rolling_hour() -> None:
    timer = Ticker()
    budget = RequestBudget(lambda: datetime(2026, 3, 6, 15, tzinfo=UTC), hourly=3, timer=timer)
    for at in (0, 100, 200):
        timer.seconds = at
        budget.take()
    timer.seconds = 3599
    with pytest.raises(RateLimitedError) as refused:
        budget.take()
    assert refused.value.retry_after == 2  # the first attempt leaves the window at 3600
    timer.seconds = 3600
    budget.take()


def test_daily_budget_follows_the_new_york_calendar_day() -> None:
    now = [datetime(2026, 3, 7, 4, 58, tzinfo=UTC)]  # 23:58 New York (EST), still 6 March there
    budget = RequestBudget(lambda: now[0], hourly=100, daily=2)
    budget.take()
    budget.take()
    with pytest.raises(RateLimitedError) as refused:
        budget.take()
    assert refused.value.retry_after == 121  # until 00:00 New York, rounded up
    now[0] = datetime(2026, 3, 7, 4, 59, 59, tzinfo=UTC)  # 23:59:59 New York, same day
    with pytest.raises(RateLimitedError):
        budget.take()
    now[0] = datetime(2026, 3, 7, 5, 0, tzinfo=UTC)  # 00:00 New York, 7 March: a new day
    budget.take()


def test_a_pause_after_a_429_uses_retry_after_or_the_default() -> None:
    timer = Ticker()
    budget = RequestBudget(lambda: datetime(2026, 3, 6, 15, tzinfo=UTC), timer=timer)
    budget.pause(30)
    with pytest.raises(RateLimitedError):
        budget.take()
    timer.seconds = 30
    budget.take()
    budget.pause(None)
    timer.seconds = 30 + RATE_LIMIT_COOLDOWN_SECONDS - 1
    with pytest.raises(RateLimitedError):
        budget.take()
    timer.seconds = 30 + RATE_LIMIT_COOLDOWN_SECONDS
    budget.take()


# --- Service -------------------------------------------------------------------------------------


class FakeProvider:
    name = "fake"

    def __init__(self) -> None:
        self.calls: list[tuple[str, date, date, bool]] = []
        self.ignore_columns = False
        self.error: Exception | None = None

    def fetch_daily(
        self, ticker: str, start: date, end: date, *, narrow: bool = True
    ) -> list[RawStockBar]:
        self.calls.append((ticker, start, end, narrow))
        if self.error:
            raise self.error
        if narrow and self.ignore_columns:
            raise IncompleteResponseError("columns ignored")
        return bars(("400", "1"), ("101", "4"))


NOW = datetime(2026, 3, 9, 22, tzinfo=UTC)


def service(
    provider: FakeProvider | None, budget: RequestBudget | None = None
) -> StockHistoryService:
    return StockHistoryService(provider, now=lambda: NOW, budget=budget)


def test_series_is_split_adjusted_and_lists_the_split() -> None:
    provider = FakeProvider()
    series = service(provider).series("brk.b", D, D + timedelta(days=1))
    assert provider.calls == [("BRK-B", D, D + timedelta(days=1), True)]
    assert closes(series.bars) == dec("100", "101")
    assert series.splits == [Split(D + timedelta(days=1), Decimal(4))]


def test_ignored_columns_fall_back_once_and_both_attempts_count() -> None:
    provider = FakeProvider()
    provider.ignore_columns = True
    budget = RequestBudget(lambda: NOW, hourly=2)
    series = service(provider, budget).series("AAPL", D, D)
    assert [call[3] for call in provider.calls] == [True, False]
    assert closes(series.bars) == dec("100", "101")
    with pytest.raises(RateLimitedError):  # the budget of 2 was spent by the fallback
        budget.take()


def test_a_429_pauses_the_next_requests_without_calling_the_provider() -> None:
    provider = FakeProvider()
    provider.error = RateLimitedError("slow down", retry_after=60)
    svc = service(provider)
    with pytest.raises(RateLimitedError):
        svc.series("AAPL", D, D)
    provider.error = None
    with pytest.raises(RateLimitedError):
        svc.series("AAPL", D, D)
    assert len(provider.calls) == 1


def test_a_budget_spent_refuses_before_any_call() -> None:
    provider = FakeProvider()
    svc = service(provider, RequestBudget(lambda: NOW, hourly=1))
    svc.series("AAPL", D, D)
    with pytest.raises(RateLimitedError):
        svc.series("AAPL", D, D)
    assert len(provider.calls) == 1


@pytest.mark.parametrize("symbol", ["AA PL", "../X", "", "A" * 30])
def test_a_ticker_that_cant_exist_is_unknown_without_a_call(symbol: str) -> None:
    provider = FakeProvider()
    with pytest.raises(SymbolNotFoundError):
        service(provider).series(symbol, D, D)
    assert provider.calls == []


def test_without_a_provider_it_is_not_configured() -> None:
    svc = service(None)
    assert not svc.configured
    with pytest.raises(ProviderUnavailableError):
        svc.series("AAPL", D, D)


def test_nothing_is_kept_between_requests() -> None:
    provider = FakeProvider()
    svc = service(provider)
    first = svc.series("AAPL", D, D)
    second = svc.series("AAPL", D, D)
    assert first == second and len(provider.calls) == 2  # fetched again: no cache
    # The service holds its provider, clock and request counts, and no data.
    assert set(vars(svc)) == {"_provider", "_now", "_budget"}
    assert set(vars(svc._budget)) == {
        "_now",
        "_timer",
        "_hourly",
        "_daily",
        "_lock",
        "_recent",
        "_day",
        "_today",
        "_paused_until",
    }
