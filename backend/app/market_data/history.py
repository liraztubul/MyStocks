"""Daily closing prices from a provider: the interface the price-history cache fills from."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Protocol

from app.domain.precision import exact

# daily_closes.close is Numeric(38, 18): enough places that micro-priced coins (0.000004...) keep
# their significant digits. Every close is rounded to it once, on the way in.
CLOSE_PLACES = 18
_CLOSE_STEP = Decimal(1).scaleb(-CLOSE_PLACES)


def round_close(value: Decimal) -> Decimal:
    # Wide context: quantizing a large value in the default 28-digit context raises instead.
    with exact():
        return value.quantize(_CLOSE_STEP, rounding=ROUND_HALF_EVEN)


@dataclass(frozen=True)
class DailyBar:
    # The trading day (stocks, exchange time) or UTC day (crypto) this close belongs to.
    day: date
    # Raw, as traded (never split- or dividend-adjusted), rounded with round_close.
    close: Decimal
    # Stocks (Tiingo, later): the split ratio taking effect that day, and cash dividend paid.
    split_factor: Decimal = Decimal(1)
    dividend: Decimal = Decimal(0)


class DailyHistoryProvider(Protocol):
    # Stable key stored with every cached close, e.g. "coingecko".
    name: str

    def earliest_available(self, now: datetime) -> date | None:
        """The oldest day this plan can return, or None when there's no limit."""
        ...

    def last_final_date(self, now: datetime) -> date:
        """The most recent day whose close is final (later days can still change)."""
        ...

    def get_daily_closes(self, provider_id: str, start: date, end: date) -> list[DailyBar]:
        """Final closes for start..end inclusive; days without trading are simply absent."""
        ...
