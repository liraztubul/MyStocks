"""Two requests filling the same series at once: no lock, idempotent upserts, no error.

Commits for real (two sessions on two connections) and cleans up after itself.
"""

import threading
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session

from app.db.models import DailyClose, PriceHistoryCoverage
from app.domain.enums import AssetType
from app.market_data.history import DailyBar
from app.market_data.price_history import PriceHistoryService

START = date(2026, 9, 1)
NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


class SlowHistory:
    """Both callers get past the cache check before either has written anything."""

    name = "race-test"

    def __init__(self) -> None:
        self.rendezvous = threading.Barrier(2)

    def earliest_available(self, now: datetime) -> date | None:
        return None

    def last_final_date(self, now: datetime) -> date:
        return now.date() - timedelta(days=1)

    def get_daily_closes(self, provider_id: str, start: date, end: date) -> list[DailyBar]:
        self.rendezvous.wait(timeout=5)
        return [DailyBar(START + timedelta(days=n), Decimal(n + 1)) for n in range(10)]


def test_concurrent_fills_of_one_series_both_succeed(engine: Engine) -> None:
    service = PriceHistoryService({AssetType.CRYPTO: SlowHistory()}, clock=lambda: NOW)
    errors: list[BaseException] = []

    def fill() -> None:
        try:
            with Session(engine) as db:
                result = service.closes(
                    db, AssetType.CRYPTO, "coin", START, START + timedelta(days=9)
                )
                assert len(result.bars) == 10
        except BaseException as exc:  # surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=fill) for _ in range(2)]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        assert errors == []
        with Session(engine) as check:
            rows = check.scalar(
                select(func.count())
                .select_from(DailyClose)
                .where(DailyClose.provider == "race-test")
            )
            coverage = check.scalars(
                select(PriceHistoryCoverage).where(PriceHistoryCoverage.provider == "race-test")
            ).all()
        assert rows == 10
        assert [(c.covered_from, c.covered_to) for c in coverage] == [
            (START, START + timedelta(days=9))
        ]
    finally:
        with Session(engine) as cleanup:
            cleanup.execute(delete(DailyClose).where(DailyClose.provider == "race-test"))
            cleanup.execute(
                delete(PriceHistoryCoverage).where(PriceHistoryCoverage.provider == "race-test")
            )
            cleanup.commit()
