"""PriceHistoryService against the real database, with a fake provider and a controllable clock."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DailyClose, PriceHistoryCoverage
from app.domain.enums import AssetType
from app.market_data.history import DailyBar
from app.market_data.price_history import (
    STALE_RATE_LIMITED,
    STALE_UNAVAILABLE,
    PriceHistoryService,
)
from app.market_data.provider import ProviderUnavailableError, RateLimitedError, SymbolNotFoundError

D = date(2026, 9, 1)


def day(n: int) -> date:
    return D + timedelta(days=n)


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


class FakeHistory:
    """Closes for days 0..N of September, like a 24/7 crypto series; failures on demand."""

    name = "fake"

    def __init__(self, clock: Clock) -> None:
        self.clock = clock
        self.closes = {day(n): Decimal(100 + n) for n in range(0, 35)}
        self.calls: list[tuple[str, date, date]] = []
        self.error: Exception | None = None
        self.earliest: date | None = date(2025, 10, 6)

    def earliest_available(self, now: datetime) -> date | None:
        return self.earliest

    def last_final_date(self, now: datetime) -> date:
        return now.date() - timedelta(days=1)

    def get_daily_closes(self, provider_id: str, start: date, end: date) -> list[DailyBar]:
        self.calls.append((provider_id, start, end))
        if self.error:
            raise self.error
        return [DailyBar(d, c) for d, c in sorted(self.closes.items()) if start <= d <= end]


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def fake(clock: Clock) -> FakeHistory:
    return FakeHistory(clock)


@pytest.fixture
def service(fake: FakeHistory, clock: Clock) -> PriceHistoryService:
    return PriceHistoryService({AssetType.CRYPTO: fake}, clock=clock)


def closes(service: PriceHistoryService, db: Session, start: date, end: date):  # type: ignore[no-untyped-def]
    return service.closes(db, AssetType.CRYPTO, "coin", start, end)


def test_first_view_backfills_and_the_second_reads_the_cache(
    service: PriceHistoryService, fake: FakeHistory, db_session: Session
) -> None:
    first = closes(service, db_session, day(0), day(9))
    assert [b.day for b in first.bars] == [day(n) for n in range(10)]
    assert (first.is_stale, first.as_of is not None) == (False, True)
    assert fake.calls == [("coin", day(0), day(9))]

    again = closes(service, db_session, day(2), day(5))
    assert [b.close for b in again.bars] == [Decimal(102), Decimal(103), Decimal(104), Decimal(105)]
    assert len(fake.calls) == 1


def test_extending_the_range_fetches_only_what_is_missing(
    service: PriceHistoryService, fake: FakeHistory, clock: Clock, db_session: Session
) -> None:
    closes(service, db_session, day(5), day(9))
    closes(service, db_session, day(0), day(9))
    assert fake.calls[1] == ("coin", day(0), day(4))  # only the older days
    clock.now += timedelta(minutes=20)  # past the tail recheck window
    closes(service, db_session, day(0), day(14))
    assert fake.calls[2] == ("coin", day(10), day(14))  # only the newer days


def test_days_without_a_close_are_not_refetched(
    service: PriceHistoryService, fake: FakeHistory, db_session: Session
) -> None:
    # A coin listed on day 5: days 0..4 have no close, and that's a final answer.
    for n in range(5):
        del fake.closes[day(n)]
    assert [b.day for b in closes(service, db_session, day(0), day(9)).bars][0] == day(5)
    closes(service, db_session, day(0), day(9))
    assert len(fake.calls) == 1


def test_a_close_not_yet_published_is_asked_for_again_but_not_on_every_view(
    service: PriceHistoryService, fake: FakeHistory, clock: Clock, db_session: Session
) -> None:
    clock.now = datetime(2026, 9, 11, 0, 5, tzinfo=UTC)  # day 9 just closed
    del fake.closes[day(9)]  # ...but its close isn't out yet
    assert closes(service, db_session, day(0), day(9)).bars[-1].day == day(8)
    closes(service, db_session, day(0), day(9))
    assert len(fake.calls) == 1  # within the recheck window: no new call
    fake.closes[day(9)] = Decimal(109)
    clock.now += timedelta(minutes=16)
    assert closes(service, db_session, day(0), day(9)).bars[-1].day == day(9)
    assert fake.calls[-1] == ("coin", day(9), day(9))


def test_provider_failure_serves_the_cache_marked_stale(
    service: PriceHistoryService, fake: FakeHistory, clock: Clock, db_session: Session
) -> None:
    closes(service, db_session, day(0), day(4))
    fetched_at = closes(service, db_session, day(0), day(4)).as_of
    fake.error = ProviderUnavailableError("down")
    result = closes(service, db_session, day(0), day(9))
    assert [b.day for b in result.bars] == [day(n) for n in range(5)]
    assert (result.is_stale, result.stale_reason) == (True, STALE_UNAVAILABLE)
    assert result.as_of == fetched_at  # when the cached data was fetched, not now
    coverage = db_session.get(PriceHistoryCoverage, ("fake", "coin"))
    assert coverage is not None and coverage.last_error == "down"


def test_nothing_cached_and_provider_down_is_an_empty_stale_result(
    service: PriceHistoryService, fake: FakeHistory, db_session: Session
) -> None:
    fake.error = ProviderUnavailableError("down")
    result = closes(service, db_session, day(0), day(4))
    assert (result.bars, result.is_stale, result.as_of) == ([], True, None)


def test_a_429_starts_a_cooldown(
    service: PriceHistoryService, fake: FakeHistory, clock: Clock, db_session: Session
) -> None:
    fake.error = RateLimitedError("slow down", retry_after=30)
    assert closes(service, db_session, day(0), day(4)).stale_reason == STALE_RATE_LIMITED
    fake.error = None
    # Within the 30 s the provider asked for: no call at all, still stale.
    clock.now += timedelta(seconds=20)
    assert closes(service, db_session, day(0), day(4)).stale_reason == STALE_RATE_LIMITED
    assert len(fake.calls) == 1
    clock.now += timedelta(seconds=15)
    result = closes(service, db_session, day(0), day(4))
    assert (result.is_stale, len(result.bars), len(fake.calls)) == (False, 5, 2)


def test_429_without_retry_after_uses_the_default_cooldown(
    fake: FakeHistory, clock: Clock, db_session: Session
) -> None:
    service = PriceHistoryService(
        {AssetType.CRYPTO: fake}, clock=clock, cooldown=timedelta(seconds=60)
    )
    fake.error = RateLimitedError("slow down")
    closes(service, db_session, day(0), day(4))
    fake.error = None
    clock.now += timedelta(seconds=59)
    closes(service, db_session, day(0), day(4))
    assert len(fake.calls) == 1
    clock.now += timedelta(seconds=2)
    closes(service, db_session, day(0), day(4))
    assert len(fake.calls) == 2


def test_unknown_series_raises(
    service: PriceHistoryService, fake: FakeHistory, db_session: Session
) -> None:
    fake.error = SymbolNotFoundError("no such coin")
    with pytest.raises(SymbolNotFoundError):
        closes(service, db_session, day(0), day(4))


def test_range_is_clamped_to_the_provider_window_and_final_days(
    service: PriceHistoryService, fake: FakeHistory, clock: Clock, db_session: Session
) -> None:
    fake.earliest = day(3)
    clock.now = datetime(2026, 9, 9, 15, 0, tzinfo=UTC)  # day 7 is the last final close
    result = closes(service, db_session, day(0), day(30))
    assert (result.start, result.end, result.earliest_available) == (day(3), day(7), day(3))
    assert fake.calls == [("coin", day(3), day(7))]


def test_closes_keep_18_decimal_places(
    service: PriceHistoryService, fake: FakeHistory, db_session: Session
) -> None:
    fake.closes = {day(0): Decimal("0.000004361234567891")}
    closes(service, db_session, day(0), day(0))
    stored = db_session.scalar(select(DailyClose.close).where(DailyClose.provider == "fake"))
    assert stored == Decimal("0.000004361234567891")


def test_a_failed_recheck_stays_stale_until_it_is_retried(
    service: PriceHistoryService, fake: FakeHistory, clock: Clock, db_session: Session
) -> None:
    closes(service, db_session, day(0), day(9))
    clock.now += timedelta(minutes=20)
    fake.error = ProviderUnavailableError("down")
    # Day 10 has closed since: the attempt fails.
    clock.now = datetime(2026, 10, 6, 12, 30, tzinfo=UTC)
    assert closes(service, db_session, day(0), day(10)).is_stale
    fake.error = None
    calls = len(fake.calls)
    # Same range again within the recheck window: not retried, but still reported as stale.
    result = closes(service, db_session, day(0), day(10))
    assert (result.is_stale, len(fake.calls)) == (True, calls)
