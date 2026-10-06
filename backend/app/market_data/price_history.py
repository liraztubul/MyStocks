"""Daily closes on demand, cached in the database and shared by every user.

The first view of a series backfills the requested range in one provider call; later views read
the cache and fetch only what's missing (older days, or days that have closed since). When the
provider fails, whatever is cached is served marked stale, with the time it was last fetched.

No request budget and no lock (M6a): writes are idempotent upserts, so two requests filling the
same series at once just write the same rows. A 429 starts a short in-process cooldown for that
provider so one rate limit doesn't turn into a burst of failing calls. ROADMAP notes when the
budget has to come back.
"""

import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import DailyClose, PriceHistoryCoverage
from app.domain.enums import AssetType
from app.market_data.history import (
    STALE_RATE_LIMITED,
    STALE_UNAVAILABLE,
    DailyBar,
    DailyHistoryProvider,
)
from app.market_data.provider import MarketDataError, RateLimitedError, SymbolNotFoundError
from app.market_data.service import coingecko_provider

# After a 429 (when the provider doesn't say how long to wait).
DEFAULT_COOLDOWN = timedelta(seconds=60)
# A close that wasn't published yet is asked for again at most this often.
TAIL_RECHECK = timedelta(minutes=15)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class HistoryResult:
    # The provider's key (daily_closes.provider), e.g. "coingecko".
    provider: str
    bars: list[DailyBar]
    # The range actually served, after clamping to what the provider can return.
    start: date
    end: date
    earliest_available: date | None
    # When this series was last fetched successfully (None: never).
    as_of: datetime | None
    is_stale: bool
    stale_reason: str | None


@dataclass(frozen=True)
class _Gap:
    start: date
    end: date
    # "head": older days (an absence there is final); "tail": newer days (may still appear).
    kind: str


class PriceHistoryService:
    def __init__(
        self,
        providers: Mapping[AssetType, DailyHistoryProvider],
        *,
        clock: Callable[[], datetime] = _utc_now,
        cooldown: timedelta = DEFAULT_COOLDOWN,
        tail_recheck: timedelta = TAIL_RECHECK,
    ) -> None:
        self._providers = providers
        self._now = clock
        self._cooldown = cooldown
        self._tail_recheck = tail_recheck
        self._cooling_until: dict[str, datetime] = {}
        self._lock = threading.Lock()

    def supports(self, asset_type: AssetType) -> bool:
        return asset_type in self._providers

    def now(self) -> datetime:
        # The service clock, so callers computing date ranges agree with it (tests can fix it).
        return self._now()

    def closes(
        self, db: Session, asset_type: AssetType, provider_id: str, start: date, end: date
    ) -> HistoryResult:
        """Final daily closes for start..end. Raises SymbolNotFoundError for an unknown series."""
        provider = self._providers[asset_type]
        now = self._now()
        earliest = provider.earliest_available(now)
        if earliest is not None:
            start = max(start, earliest)
        end = min(end, provider.last_final_date(now))

        stale_reason = None
        if start <= end:
            coverage = db.get(PriceHistoryCoverage, (provider.name, provider_id))
            gaps, held_back = self._gaps(coverage, start, end, now)
            if gaps:
                stale_reason = self._fill(db, provider, provider_id, gaps, now)
            elif held_back and coverage is not None and coverage.last_error:
                # Not retried yet (recheck window), and the last attempt failed.
                stale_reason = self._cooling_reason(provider.name, now) or STALE_UNAVAILABLE

        rows = db.scalars(
            select(DailyClose)
            .where(
                DailyClose.provider == provider.name,
                DailyClose.provider_id == provider_id,
                DailyClose.day.between(start, end),
            )
            .order_by(DailyClose.day)
        ).all()
        coverage = db.get(PriceHistoryCoverage, (provider.name, provider_id))
        return HistoryResult(
            provider=provider.name,
            bars=[DailyBar(r.day, r.close, r.split_factor, r.dividend) for r in rows],
            start=start,
            end=end,
            earliest_available=earliest,
            as_of=coverage.last_success_at if coverage else None,
            is_stale=stale_reason is not None,
            stale_reason=stale_reason,
        )

    def _gaps(
        self, coverage: PriceHistoryCoverage | None, start: date, end: date, now: datetime
    ) -> tuple[list[_Gap], bool]:
        """The ranges to fetch, and whether a needed range was held back by the recheck window."""
        if coverage is None or coverage.covered_from is None:
            return [_Gap(start, end, "tail")], False
        gaps = []
        if start < coverage.covered_from:
            gaps.append(_Gap(start, coverage.covered_from - timedelta(days=1), "head"))
        covered_to = coverage.covered_to or coverage.covered_from - timedelta(days=1)
        held_back = False
        if end > covered_to:
            # Days nobody asked for before are fetched now; days already asked for that had no
            # close yet (not published, or the attempt failed) wait for the recheck window.
            new_days = coverage.checked_to is None or end > coverage.checked_to
            recently_tried = (
                coverage.last_attempt_at is not None
                and now - coverage.last_attempt_at < self._tail_recheck
            )
            if new_days or not recently_tried:
                gaps.append(_Gap(max(start, covered_to + timedelta(days=1)), end, "tail"))
            else:
                held_back = True
        return gaps, held_back

    def _cooling_reason(self, provider: str, now: datetime) -> str | None:
        with self._lock:
            return STALE_RATE_LIMITED if self._cooling_until.get(provider, now) > now else None

    def _fill(
        self,
        db: Session,
        provider: DailyHistoryProvider,
        provider_id: str,
        gaps: list[_Gap],
        now: datetime,
    ) -> str | None:
        """Fetch the gaps and cache them; returns a stale reason if the provider failed."""
        if reason := self._cooling_reason(provider.name, now):
            return reason
        checked_to = max(g.end for g in gaps)
        try:
            for gap in gaps:
                bars = provider.get_daily_closes(provider_id, gap.start, gap.end)
                self._store(db, provider.name, provider_id, bars, now)
                newest = bars[-1].day if bars else None
                self._cover(
                    db,
                    provider.name,
                    provider_id,
                    now,
                    # Older days with no close are a final answer; newer ones may still appear.
                    covered_from=gap.start,
                    covered_to=newest if gap.kind == "tail" else gap.end,
                    checked_to=gap.end,
                )
                # Per gap, so an older range already fetched survives a failure on a newer one.
                db.commit()
            return None
        except SymbolNotFoundError:
            db.rollback()
            raise
        except MarketDataError as exc:
            db.rollback()
            if isinstance(exc, RateLimitedError):
                wait = timedelta(seconds=exc.retry_after) if exc.retry_after else self._cooldown
                with self._lock:
                    self._cooling_until[provider.name] = now + wait
            self._record_failure(db, provider.name, provider_id, now, exc.message, checked_to)
            db.commit()
            return STALE_RATE_LIMITED if isinstance(exc, RateLimitedError) else STALE_UNAVAILABLE

    @staticmethod
    def _store(
        db: Session, provider: str, provider_id: str, bars: list[DailyBar], now: datetime
    ) -> None:
        if not bars:
            return
        statement = insert(DailyClose).values(
            [
                {
                    "provider": provider,
                    "provider_id": provider_id,
                    "day": bar.day,
                    "close": bar.close,
                    "split_factor": bar.split_factor,
                    "dividend": bar.dividend,
                    "fetched_at": now,
                }
                for bar in bars
            ]
        )
        # Idempotent: a concurrent fill of the same series writes the same final values.
        db.execute(
            statement.on_conflict_do_update(
                index_elements=["provider", "provider_id", "day"],
                set_={
                    "close": statement.excluded.close,
                    "split_factor": statement.excluded.split_factor,
                    "dividend": statement.excluded.dividend,
                    "fetched_at": statement.excluded.fetched_at,
                },
            )
        )

    @staticmethod
    def _cover(
        db: Session,
        provider: str,
        provider_id: str,
        now: datetime,
        covered_from: date,
        covered_to: date | None,
        checked_to: date,
    ) -> None:
        statement = insert(PriceHistoryCoverage).values(
            provider=provider,
            provider_id=provider_id,
            covered_from=covered_from,
            covered_to=covered_to,
            checked_to=checked_to,
            last_attempt_at=now,
            last_success_at=now,
            last_error=None,
        )
        table = PriceHistoryCoverage.__table__.c
        # Coverage only ever widens: LEAST/GREATEST ignore NULLs, so a concurrent fill can't
        # shrink what another one recorded.
        db.execute(
            statement.on_conflict_do_update(
                index_elements=["provider", "provider_id"],
                set_={
                    "covered_from": func.least(table.covered_from, statement.excluded.covered_from),
                    "covered_to": func.greatest(table.covered_to, statement.excluded.covered_to),
                    "checked_to": func.greatest(table.checked_to, statement.excluded.checked_to),
                    "last_attempt_at": statement.excluded.last_attempt_at,
                    "last_success_at": statement.excluded.last_success_at,
                    "last_error": None,
                },
            )
        )

    @staticmethod
    def _record_failure(
        db: Session,
        provider: str,
        provider_id: str,
        now: datetime,
        message: str,
        checked_to: date,
    ) -> None:
        statement = insert(PriceHistoryCoverage).values(
            provider=provider,
            provider_id=provider_id,
            last_attempt_at=now,
            last_error=message,
            checked_to=checked_to,
        )
        table = PriceHistoryCoverage.__table__.c
        db.execute(
            statement.on_conflict_do_update(
                index_elements=["provider", "provider_id"],
                set_={
                    "last_attempt_at": now,
                    "last_error": message,
                    "checked_to": func.greatest(table.checked_to, statement.excluded.checked_to),
                },
            )
        )


# Ungated, like shared_market_data: stock history (Tiingo, later) must reach users only through
# app.market_data.access. Crypto only for now. Routers must never depend on this directly
# (tests/unit/test_market_data_boundary.py).
@lru_cache
def shared_price_history() -> PriceHistoryService:
    return PriceHistoryService({AssetType.CRYPTO: coingecko_provider()})
