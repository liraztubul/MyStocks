from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from app.market_data.dates import (
    US_MARKET_TZ,
    crypto_close_snapshot_date,
    price_before_change,
    resolve_stock_price_date,
    us_session_start,
    within_free_crypto_history,
)


def ny(year: int, month: int, day: int, hour: int = 16, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=US_MARKET_TZ)


FRIDAY_CLOSE = ny(2026, 3, 13)
MONDAY_MORNING = ny(2026, 3, 16, 8)


def test_trading_day_after_close_is_the_final_close() -> None:
    resolved = resolve_stock_price_date(date(2026, 3, 13), FRIDAY_CLOSE, ny(2026, 3, 13, 17))
    assert resolved is not None
    assert (resolved.price_date, resolved.is_final_close) == (date(2026, 3, 13), True)


def test_saturday_falls_back_to_friday_close() -> None:
    resolved = resolve_stock_price_date(date(2026, 3, 14), FRIDAY_CLOSE, MONDAY_MORNING)
    assert resolved is not None
    assert (resolved.price_date, resolved.is_final_close) == (date(2026, 3, 13), True)


def test_sunday_falls_back_to_friday_close() -> None:
    resolved = resolve_stock_price_date(date(2026, 3, 15), FRIDAY_CLOSE, MONDAY_MORNING)
    assert resolved is not None
    assert resolved.price_date == date(2026, 3, 13)


def test_holiday_monday_falls_back_to_prior_friday() -> None:
    # 2026-01-19 is Martin Luther King Jr. Day; NYSE is closed.
    last_session = ny(2026, 1, 16)
    resolved = resolve_stock_price_date(date(2026, 1, 19), last_session, ny(2026, 1, 20, 8))
    assert resolved is not None
    assert resolved.price_date == date(2026, 1, 16)


def test_long_weekend_with_holiday_friday_still_falls_back() -> None:
    # Good Friday 2026-04-03: Thursday's close answers Friday, Saturday and Sunday.
    thursday_close = ny(2026, 4, 2)
    for day in (3, 4, 5):
        resolved = resolve_stock_price_date(date(2026, 4, day), thursday_close, ny(2026, 4, 6, 8))
        assert resolved is not None
        assert resolved.price_date == date(2026, 4, 2)


def test_same_day_before_close_is_live_not_final() -> None:
    resolved = resolve_stock_price_date(
        date(2026, 3, 13), ny(2026, 3, 13, 11, 30), ny(2026, 3, 13, 11, 31)
    )
    assert resolved is not None
    assert (resolved.price_date, resolved.is_final_close) == (date(2026, 3, 13), False)


def test_date_before_latest_session_cannot_be_answered() -> None:
    # Needs historical candles, which Finnhub's free tier doesn't include.
    assert resolve_stock_price_date(date(2026, 3, 12), FRIDAY_CLOSE, MONDAY_MORNING) is None


def test_stale_quote_is_not_treated_as_a_holiday_fallback() -> None:
    delisted_last_trade = ny(2026, 2, 27)
    assert resolve_stock_price_date(date(2026, 3, 13), delisted_last_trade, MONDAY_MORNING) is None


def test_trade_timestamp_is_interpreted_in_new_york_time() -> None:
    # 21:00 UTC on Friday is 17:00 in New York (EDT), still Friday's session.
    friday_utc = datetime(2026, 3, 13, 21, 0, tzinfo=timezone.utc)
    resolved = resolve_stock_price_date(date(2026, 3, 14), friday_utc, MONDAY_MORNING)
    assert resolved is not None
    assert resolved.price_date == date(2026, 3, 13)


def test_crypto_close_is_next_days_snapshot() -> None:
    assert crypto_close_snapshot_date(date(2026, 3, 14)) == date(2026, 3, 15)


def test_crypto_free_history_window_is_365_days() -> None:
    today = date(2026, 9, 30)
    assert within_free_crypto_history(today - timedelta(days=365), today)
    assert not within_free_crypto_history(today - timedelta(days=366), today)


def test_session_start_is_new_york_midnight_across_the_spring_dst_change() -> None:
    # US DST began 2026-03-08. Midnight New York is 05:00 UTC before it and 04:00 UTC after.
    friday_before = us_session_start(datetime(2026, 3, 6, 21, 0, tzinfo=timezone.utc))
    monday_after = us_session_start(datetime(2026, 3, 9, 20, 0, tzinfo=timezone.utc))
    assert friday_before == datetime(2026, 3, 6, 5, 0, tzinfo=timezone.utc)
    assert monday_after == datetime(2026, 3, 9, 4, 0, tzinfo=timezone.utc)
    assert (friday_before.utcoffset(), monday_after.utcoffset()) == (
        timedelta(hours=-5),
        timedelta(hours=-4),
    )


def test_session_start_across_the_autumn_dst_change() -> None:
    # US DST ended 2026-11-01: Friday 10-30 is EDT (04:00 UTC), Monday 11-02 is EST (05:00 UTC).
    assert us_session_start(datetime(2026, 10, 30, 20, 0, tzinfo=timezone.utc)) == datetime(
        2026, 10, 30, 4, 0, tzinfo=timezone.utc
    )
    assert us_session_start(datetime(2026, 11, 2, 21, 0, tzinfo=timezone.utc)) == datetime(
        2026, 11, 2, 5, 0, tzinfo=timezone.utc
    )


def test_late_evening_utc_trade_belongs_to_that_new_york_day() -> None:
    # 00:30 UTC Tuesday is still 20:30 Monday in New York.
    assert us_session_start(datetime(2026, 10, 6, 0, 30, tzinfo=timezone.utc)).date() == date(
        2026, 10, 5
    )


def test_price_before_change() -> None:
    assert price_before_change(Decimal("110"), Decimal("10")) == Decimal("100")
    assert price_before_change(Decimal("90"), Decimal("-10")) == Decimal("100")
    assert price_before_change(Decimal("5"), Decimal("-100")) is None
    assert price_before_change(Decimal("5"), Decimal("-150")) is None
