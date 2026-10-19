"""Daily stock history, transient: fetched per request, adjusted in memory, never stored.

Tiingo's free (Starter) plan forbids persistent storage of its data and of anything derived from
it (terms §1.6(a) and §1.6(c), read 2026-10-09 and 2026-10-16). So this module keeps no cache of
any kind: no table, no coverage, no stale fallback, no in-memory reuse between requests. Each
call fetches the range, computes the split-adjusted series, and lets it go with the response.
The only state kept is a count of our own request attempts (RequestBudget), which holds no data.

Financial assumptions, stated wherever the series is shown:
- Split-adjusted closing prices: a close is divided by every split factor that takes effect on
  a later bar. Dividends are not included (Tiingo's adjClose is never used: it also adjusts for
  dividends). A factor that isn't 1 because of another distribution (e.g. a spin-off) is
  treated like a split.
- End-of-day data, by US trading day; it may be delayed. Tiingo sends no bar for the day in
  progress (a probe during market hours on 2026-10-19 returned the previous trading day as the
  latest), so every bar is a finished day.

Ungated: endpoints reach it only through app.market_data.access.UserStockHistoryDep.
"""

import re
import threading
import time
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from datetime import time as clock_time
from decimal import ROUND_HALF_EVEN, Decimal
from functools import lru_cache

from app.core.config import settings
from app.domain.precision import exact
from app.market_data.dates import US_MARKET_TZ
from app.market_data.provider import (
    IncompleteResponseError,
    ProviderUnavailableError,
    RateLimitedError,
    RawStockBar,
    SymbolNotFoundError,
    TransientHistoryProvider,
)
from app.market_data.service import http_client
from app.market_data.tiingo_provider import TiingoProvider

ADJUSTED_PLACES = 10
_ADJUSTED_STEP = Decimal(1).scaleb(-ADJUSTED_PLACES)

# Below Tiingo's Starter limits (50 requests an hour, 1,000 a day), to fail fast with a clear
# reason instead of spending real 429s. Every attempt counts, errors and 404s included: we can't
# tell which of them Tiingo counts.
HOURLY_BUDGET = 45
DAILY_BUDGET = 950
# After a 429 without Retry-After.
RATE_LIMIT_COOLDOWN_SECONDS = 15 * 60

_TICKER = re.compile(r"[A-Z0-9][A-Z0-9-]{0,19}")


@dataclass(frozen=True)
class AdjustedBar:
    day: date
    close: Decimal


@dataclass(frozen=True)
class Split:
    day: date
    factor: Decimal


@dataclass(frozen=True)
class StockSeries:
    provider: str
    bars: list[AdjustedBar]
    splits: list[Split]

    def chart_price(self, price: Decimal, day: date) -> Decimal:
        """A price paid on `day` in the series' terms: divided by the splits that took effect
        after that day, like the closes."""
        with exact():
            factor = Decimal(1)
            for split in self.splits:
                if split.day > day:
                    factor *= split.factor
            return (price / factor).quantize(_ADJUSTED_STEP, rounding=ROUND_HALF_EVEN)


def provider_ticker(symbol: str) -> str:
    """The provider's spelling of a user's ticker: share classes use '-' (BRK.B -> BRK-B)."""
    return symbol.strip().upper().replace(".", "-")


def split_adjust(bars: Sequence[RawStockBar]) -> list[AdjustedBar]:
    """a_i = c_i / product of f_j over later bars j > i. A split's own (ex-date) bar already
    trades after the split, so it isn't divided by its own factor. Bars must be oldest first."""
    adjusted: list[AdjustedBar] = []
    with exact():
        later = Decimal(1)
        for bar in reversed(bars):
            if bar.split_factor <= 0 or bar.close <= 0:
                raise ProviderUnavailableError("The price provider sent an invalid bar.")
            close = (bar.close / later).quantize(_ADJUSTED_STEP, rounding=ROUND_HALF_EVEN)
            adjusted.append(AdjustedBar(bar.day, close))
            later *= bar.split_factor
    adjusted.reverse()
    return adjusted


def _new_york_day(now: datetime) -> date:
    return now.astimezone(US_MARKET_TZ).date()


def _seconds_to_next_new_york_day(now: datetime) -> int:
    local = now.astimezone(US_MARKET_TZ)
    midnight = datetime.combine(local.date() + timedelta(days=1), clock_time(0), US_MARKET_TZ)
    return int((midnight - local).total_seconds()) + 1


class RequestBudget:
    """Counts our own provider request attempts (timestamps only, no data): a rolling hour, and
    the America/New_York calendar day. Also holds the pause after a 429."""

    def __init__(
        self,
        now: Callable[[], datetime],
        *,
        hourly: int = HOURLY_BUDGET,
        daily: int = DAILY_BUDGET,
        timer: Callable[[], float] = time.monotonic,
    ) -> None:
        self._now = now
        self._timer = timer
        self._hourly = hourly
        self._daily = daily
        self._lock = threading.Lock()
        self._recent: deque[float] = deque()
        self._day: date | None = None
        self._today = 0
        self._paused_until = 0.0

    def take(self) -> None:
        """Records one attempt, or raises RateLimitedError (with seconds to wait) instead."""
        with self._lock:
            moment = self._timer()
            if moment < self._paused_until:
                raise RateLimitedError(
                    "Stock history is paused after the provider's rate limit.",
                    retry_after=int(self._paused_until - moment) + 1,
                )
            while self._recent and moment - self._recent[0] >= 3600:
                self._recent.popleft()
            if len(self._recent) >= self._hourly:
                wait = int(3600 - (moment - self._recent[0])) + 1
                raise RateLimitedError("Stock history request limit reached.", retry_after=wait)
            day = _new_york_day(self._now())
            if day != self._day:
                self._day, self._today = day, 0
            if self._today >= self._daily:
                raise RateLimitedError(
                    "Stock history daily request limit reached.",
                    retry_after=_seconds_to_next_new_york_day(self._now()),
                )
            self._recent.append(moment)
            self._today += 1

    def pause(self, seconds: int | None) -> None:
        with self._lock:
            self._paused_until = self._timer() + (seconds or RATE_LIMIT_COOLDOWN_SECONDS)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class StockHistoryService:
    def __init__(
        self,
        provider: TransientHistoryProvider | None,
        *,
        now: Callable[[], datetime] = _utc_now,
        budget: RequestBudget | None = None,
    ) -> None:
        self._provider = provider
        self._now = now
        self._budget = budget or RequestBudget(now)

    @property
    def configured(self) -> bool:
        return self._provider is not None

    def now(self) -> datetime:
        return self._now()

    def series(self, symbol: str, start: date, end: date) -> StockSeries:
        """The split-adjusted daily series for start..end, fetched now and kept nowhere.
        Raises SymbolNotFoundError, RateLimitedError or ProviderUnavailableError."""
        if self._provider is None:
            raise ProviderUnavailableError("Stock history isn't configured on this deployment.")
        ticker = provider_ticker(symbol)
        if not _TICKER.fullmatch(ticker):
            raise SymbolNotFoundError(f"No stock history found for {symbol.strip().upper()}.")
        try:
            raw = self._fetch(ticker, start, end, narrow=True)
        except IncompleteResponseError:
            # The narrowing parameter is undocumented; once without it (a second attempt).
            raw = self._fetch(ticker, start, end, narrow=False)
        return StockSeries(
            provider=self._provider.name,
            bars=split_adjust(raw),
            splits=[Split(b.day, b.split_factor) for b in raw if b.split_factor != 1],
        )

    def _fetch(self, ticker: str, start: date, end: date, *, narrow: bool) -> list[RawStockBar]:
        assert self._provider is not None
        self._budget.take()
        try:
            return self._provider.fetch_daily(ticker, start, end, narrow=narrow)
        except RateLimitedError as exc:
            self._budget.pause(exc.retry_after)
            raise


@lru_cache
def shared_stock_history() -> StockHistoryService:
    key = settings.tiingo_api_key
    return StockHistoryService(TiingoProvider(key, http_client()) if key else None)
