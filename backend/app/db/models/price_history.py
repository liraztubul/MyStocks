from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# 20 integer digits, 18 fractional: micro-priced coins (0.000004...) keep their significant
# digits. Values are rounded half-even to 18 places before they're written (history.round_close).
CLOSE = Numeric(38, 18, asdecimal=True)


class DailyClose(Base):
    """One final daily close per provider series, shared by every user (prices are public).

    Keyed by the provider's own series id (the CoinGecko coin id, later the Tiingo ticker), not by
    a user's ticker: two users can mean different coins by "BTC". Raw closes plus split and
    dividend facts never change once final, so rows are cached for good; adjusted prices, which
    shift every time a new split happens, are derived when read rather than stored.
    """

    __tablename__ = "daily_closes"

    provider: Mapped[str] = mapped_column(String(16), primary_key=True)
    provider_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    close: Mapped[Decimal] = mapped_column(CLOSE)
    split_factor: Mapped[Decimal] = mapped_column(CLOSE, default=Decimal(1), server_default="1")
    dividend: Mapped[Decimal] = mapped_column(CLOSE, default=Decimal(0), server_default="0")
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PriceHistoryCoverage(Base):
    """Which days of a series have been asked for, so a day without a close (a holiday, a coin
    not yet listed) is a known absence rather than a cache miss fetched again on every view."""

    __tablename__ = "price_history_coverage"

    provider: Mapped[str] = mapped_column(String(16), primary_key=True)
    provider_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    # Every day in covered_from..covered_to has been fetched; days without a row have no close.
    # covered_to only advances to the newest close actually returned, so a close that wasn't
    # published yet is asked for again later.
    covered_from: Mapped[date | None] = mapped_column(Date)
    covered_to: Mapped[date | None] = mapped_column(Date)
    # The newest day ever asked for. Days after covered_to up to here were requested but had no
    # close yet; they're rechecked at most every TAIL_RECHECK. Days after this are new requests.
    checked_to: Mapped[date | None] = mapped_column(Date)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
