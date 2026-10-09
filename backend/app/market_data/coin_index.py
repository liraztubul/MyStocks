"""A local index of the top coins, so search-as-you-type never calls the provider per keystroke.

Refresh is lazy: a suggest request finds the index empty or older than MAX_AGE and starts one.
- Stale-while-revalidate: an old index is served at once while the refresh runs in the
  background. Only an empty index makes the request wait (briefly) for the refresh.
- Single-flight: a lock guards "is a refresh running? if not, start one"; the running thread is
  the flight. Concurrent requests find it alive and share it (an empty-index request joins it),
  so they cause one provider fetch. Per process only: production runs one instance.
- A failed refresh keeps the old rows and starts a cooldown, so requests don't retry every time.
- Served only while at most MAX_AGE old, or while a refresh is actually running. Older rows with
  no refresh running (e.g. during the cooldown) are kept but not served: the answer is empty
  with reason coin_index_unavailable, and the client falls back to exact tickers.
- No DB transaction is open across the provider call: the refresh fetches first, then writes in
  a short transaction of its own, and the request ends its read transaction before waiting.

CoinGecko's API terms (section 6.1, read 2026-10-09): "if you must cache or store Data: (a) You
should refresh the cache at least every 24 hours". MAX_AGE follows that, a refresh replaces the
whole table, and the serving rule above keeps data older than that from being shown.

Ungated: endpoints reach it only through app.market_data.access.CoinIndexDep.
"""

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache

from sqlalchemy import case, delete, func, select
from sqlalchemy.orm import Session

from app.db.models import CoinIndexEntry
from app.db.session import SessionLocal
from app.market_data.provider import CoinListProvider
from app.market_data.service import coingecko_provider

logger = logging.getLogger(__name__)

INDEX_SIZE = 500
MAX_AGE = timedelta(hours=24)
RETRY_COOLDOWN = timedelta(minutes=15)
# How long a request with an empty index waits for the refresh: two pages at the provider's
# 5 s timeout, plus the write.
EMPTY_INDEX_WAIT_SECONDS = 12.0
MIN_QUERY_LENGTH = 2
MAX_QUERY_LENGTH = 50
MAX_RESULTS = 8

# Why there are no suggestions, when it isn't "nothing matched".
INDEX_LOADING = "coin_index_loading"
INDEX_UNAVAILABLE = "coin_index_unavailable"


@dataclass(frozen=True)
class Suggestions:
    coins: list[CoinIndexEntry]
    reason: str | None = None


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _like_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class CoinIndexService:
    def __init__(
        self,
        source: CoinListProvider,
        session_factory: Callable[[], Session],
        *,
        now: Callable[[], datetime] = _utc_now,
        size: int = INDEX_SIZE,
        max_age: timedelta = MAX_AGE,
        cooldown: timedelta = RETRY_COOLDOWN,
        empty_wait_seconds: float = EMPTY_INDEX_WAIT_SECONDS,
    ) -> None:
        self._source = source
        self._session_factory = session_factory
        self._now = now
        self._size = size
        self._max_age = max_age
        self._cooldown = cooldown
        self._empty_wait = empty_wait_seconds
        self._lock = threading.Lock()
        self._flight: threading.Thread | None = None
        self._failed_at: datetime | None = None

    def suggest(self, db: Session, query: str) -> Suggestions:
        q = query.strip()[:MAX_QUERY_LENGTH]
        if len(q) < MIN_QUERY_LENGTH:
            return Suggestions([])
        updated_at = self._updated_at(db)
        # Nothing stays open while a refresh may be waiting on the provider.
        db.rollback()
        flight = self.refresh_if_due(updated_at)
        if updated_at is None:
            if flight is not None:
                flight.join(self._empty_wait)
            if self._updated_at(db) is None:
                running = flight is not None and flight.is_alive()
                return Suggestions([], INDEX_LOADING if running else INDEX_UNAVAILABLE)
        elif self._now() - updated_at > self._max_age and not (flight and flight.is_alive()):
            # Too old to serve, and no refresh is running; unless one just finished.
            updated_at = self._updated_at(db)
            if updated_at is None or self._now() - updated_at > self._max_age:
                return Suggestions([], INDEX_UNAVAILABLE)
        return Suggestions(self._match(db, q))

    def refresh_if_due(self, updated_at: datetime | None) -> threading.Thread | None:
        """The refresh in flight, starting one if the index is empty or too old and no failure is
        cooling down; None when no refresh is running."""
        now = self._now()
        with self._lock:
            if self._flight is not None and self._flight.is_alive():
                return self._flight
            if updated_at is not None and now - updated_at < self._max_age:
                return None
            if self._failed_at is not None and now - self._failed_at < self._cooldown:
                return None
            self._flight = threading.Thread(target=self._refresh, name="coin-index", daemon=True)
            self._flight.start()
            return self._flight

    def _refresh(self) -> None:
        try:
            coins = self._source.top_coins(self._size)
            if not coins:
                raise ValueError("the provider returned no coins")
            stamp = self._now()
            with self._session_factory() as db:
                db.execute(delete(CoinIndexEntry))
                db.add_all(
                    CoinIndexEntry(
                        provider_id=c.provider_id,
                        symbol=c.symbol,
                        name=c.name,
                        market_cap_rank=c.market_cap_rank,
                        updated_at=stamp,
                    )
                    for c in coins
                )
                db.commit()
            with self._lock:
                self._failed_at = None
            logger.info("Coin index refreshed: %d coins.", len(coins))
        except Exception as exc:
            # The old rows stay; the cooldown keeps requests from retrying every time.
            with self._lock:
                self._failed_at = self._now()
            logger.warning(
                "Coin index refresh failed (%s); keeping the old index.", type(exc).__name__
            )

    @staticmethod
    def _updated_at(db: Session) -> datetime | None:
        return db.scalar(select(func.max(CoinIndexEntry.updated_at)))

    @staticmethod
    def _match(db: Session, q: str) -> list[CoinIndexEntry]:
        """Exact ticker, ticker prefix, name prefix, a name word's prefix, name contains; ties by
        market-cap rank. User input is matched literally: % and _ are escaped."""
        text = _like_escape(q)
        symbol, name = CoinIndexEntry.symbol, CoinIndexEntry.name
        tiers = [
            func.upper(symbol) == q.upper(),
            symbol.ilike(f"{text}%", escape="\\"),
            name.ilike(f"{text}%", escape="\\"),
            name.ilike(f"% {text}%", escape="\\"),
            name.ilike(f"%{text}%", escape="\\"),
        ]
        tier = case(*((condition, i) for i, condition in enumerate(tiers)))
        rows = db.scalars(
            select(CoinIndexEntry)
            .where(tier.is_not(None))
            .order_by(tier, CoinIndexEntry.market_cap_rank.asc().nulls_last(), CoinIndexEntry.name)
            .limit(MAX_RESULTS)
        )
        return list(rows)


@lru_cache
def shared_coin_index() -> CoinIndexService:
    return CoinIndexService(coingecko_provider(), SessionLocal)
