from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

US_MARKET_TZ = ZoneInfo("America/New_York")
US_MARKET_CLOSE = time(16, 0)
# Longest real run of non-trading days is ~4 (a holiday beside a weekend); a quote older than
# this relative to the requested date is stale (halted/delisted), not a holiday fallback.
MAX_STOCK_FALLBACK_DAYS = 5
COINGECKO_FREE_HISTORY_DAYS = 365


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
