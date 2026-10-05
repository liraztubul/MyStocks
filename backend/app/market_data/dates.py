from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.domain.precision import exact

US_MARKET_TZ = ZoneInfo("America/New_York")
US_MARKET_CLOSE = time(16, 0)
# Longest real run of non-trading days is ~4 (a holiday beside a weekend); a quote older than
# this relative to the requested date is stale (halted/delisted), not a holiday fallback.
MAX_STOCK_FALLBACK_DAYS = 5
COINGECKO_FREE_HISTORY_DAYS = 365
ROLLING_CHANGE_WINDOW = timedelta(hours=24)


@dataclass(frozen=True)
class StockPriceDate:
    price_date: date
    is_final_close: bool


def resolve_stock_price_date(
    requested: date, last_trade: datetime, now: datetime
) -> StockPriceDate | None:
    """Which trading day's price the latest quote gives for `requested`, if it can answer at all.

    The quote only knows the most recent session. That answers any requested date on or after
    it (a weekend or holiday falls back to the last session before it), but not an earlier one.
    """
    trade_day = last_trade.astimezone(US_MARKET_TZ).date()
    if trade_day > requested or (requested - trade_day).days > MAX_STOCK_FALLBACK_DAYS:
        return None
    market_now = now.astimezone(US_MARKET_TZ)
    is_final = trade_day < market_now.date() or market_now.time() >= US_MARKET_CLOSE
    return StockPriceDate(price_date=trade_day, is_final_close=is_final)


def crypto_close_snapshot_date(requested: date) -> date:
    # CoinGecko snapshots at 00:00 UTC, so a UTC day's close is the next day's snapshot.
    return requested + timedelta(days=1)


def within_free_crypto_history(snapshot: date, today: date) -> bool:
    return (today - snapshot).days <= COINGECKO_FREE_HISTORY_DAYS


def us_session_start(last_trade: datetime) -> datetime:
    """Midnight New York time on the trading day of `last_trade`, DST-aware.

    A Finnhub quote's change (c - pc) covers that one session, so this marks where "today"
    starts for it: trades at or after this instant are part of the same session's change.
    """
    session_day = last_trade.astimezone(US_MARKET_TZ).date()
    return datetime.combine(session_day, time(0), tzinfo=US_MARKET_TZ)


def price_before_change(price: Decimal, change_pct: Decimal) -> Decimal | None:
    """The earlier price that a `change_pct`% move turned into `price`, or None if undefined.

    CoinGecko only reports the rolling 24h change as a percentage, so the base price has to be
    derived. A change of -100% or less has no meaningful base.
    """
    with exact():
        factor = 1 + change_pct / 100
        return price / factor if factor > 0 else None
