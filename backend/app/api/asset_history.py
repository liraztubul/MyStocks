"""GET /api/assets/{symbol}/history: daily closes plus the user's own trades as chart markers.

Crypto closes come from the price-history cache. Stock history is transient: fetched per request
from Tiingo, split-adjusted in memory and never stored (app.market_data.stock_history), so it has
no stale fallback; when it can't be fetched the answer is available=false with a reason.

Works for any symbol, held or not (a watched symbol isn't a holding). It's a view, so the error
convention in app.market_data.access applies: a chart this deployment can't show is 200 with
available=false, and an ambiguous crypto ticker is 200 with the candidates to pick from. 404 is
only for an unknown symbol; 422 for an invalid range, or a type that can't be inferred.
"""

import bisect
import calendar
import uuid
from collections.abc import Callable, Sequence
from datetime import date, timezone
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.assets import Symbol
from app.core.security import CurrentUser
from app.db.models import Transaction, UserAsset
from app.db.session import DbSession
from app.domain.enums import AssetType
from app.market_data.access import (
    UserMarketDataDep,
    UserPriceHistoryDep,
    UserStockHistory,
    UserStockHistoryDep,
)
from app.market_data.dates import US_MARKET_TZ, years_back
from app.market_data.history import STALE_UNAVAILABLE
from app.market_data.provider import (
    AmbiguousSymbolError,
    MarketDataError,
    RateLimitedError,
    SymbolNotFoundError,
)
from app.schemas.history import (
    BarRead,
    CoinCandidateRead,
    HistoryRange,
    HistoryRead,
    MarkerRead,
    SplitRead,
    UndrawnReason,
    UndrawnTradeRead,
)
from app.services.asset_identity import RULE

router = APIRouter(prefix="/assets", tags=["assets"])

# "ALL" (or any range) reaching back further than the provider allows.
HISTORY_LIMIT_NOTE = (
    "Crypto history covers the past 365 days on the free data plan, so older days aren't "
    "charted. Older trades are still listed below the chart."
)
# The same, for a coin the user has no trades in (e.g. opened from the watchlist).
HISTORY_LIMIT_NOTE_NO_TRADES = (
    "Crypto history covers the past 365 days on the free data plan, so older days aren't charted."
)
# "ALL" for an asset without trades: as far back as the provider goes (it clamps the start).
_BEGINNING = date(1970, 1, 1)
# Stocks without trades: "ALL" is capped (decades of daily bars would be fetched on every view).
STOCK_ALL_YEARS = 10
STOCK_ALL_NOTE = f"You have no trades in this stock, so All shows the past {STOCK_ALL_YEARS} years."


def _months_back(day: date, months: int) -> date:
    years, month_index = divmod(day.month - 1 - months, 12)
    year, month = day.year + years, month_index + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def _range_start(range_: HistoryRange, today: date, first_trade: date | None) -> date:
    if range_ == "YTD":
        return date(today.year, 1, 1)
    if range_ == "ALL":
        return first_trade or _BEGINNING
    months = {"1M": 1, "3M": 3, "6M": 6, "1Y": 12}[range_]
    return _months_back(today, months)


def _trade_day(trade: Transaction, asset_type: AssetType) -> date:
    # Crypto trades all day, and its daily close is the UTC day's; a stock trade belongs to its
    # New York trading date (pre-market and after-hours included).
    zone = timezone.utc if asset_type is AssetType.CRYPTO else US_MARKET_TZ
    return trade.executed_at.astimezone(zone).date()


def _undrawn(trade: Transaction, day: date, reason: UndrawnReason) -> UndrawnTradeRead:
    return UndrawnTradeRead(
        transaction_id=trade.id,
        side=trade.side,
        trade_date=day,
        quantity=trade.quantity,
        price=trade.price,
        reason=reason,
    )


def _unadjusted(price: Decimal, _day: date) -> Decimal:
    return price


def _place_trades(
    trades: Sequence[Transaction],
    asset_type: AssetType,
    bar_days: Sequence[date],
    start: date,
    end: date,
    chart_price: Callable[[Decimal, date], Decimal] = _unadjusted,
) -> tuple[list[MarkerRead], list[UndrawnTradeRead]]:
    markers, undrawn = [], []
    for trade in trades:
        day = _trade_day(trade, asset_type)
        if not bar_days:
            undrawn.append(_undrawn(trade, day, "no_chart"))
        elif day < start:
            undrawn.append(_undrawn(trade, day, "before_range"))
        elif day > end:
            # Today's trades: the day hasn't closed, so there's no bar to sit on yet.
            undrawn.append(_undrawn(trade, day, "after_range"))
        else:
            # The trade's own bar, or the next one when its day has no close (a weekend).
            index = bisect.bisect_left(bar_days, day)
            if index == len(bar_days):
                undrawn.append(_undrawn(trade, day, "after_range"))
                continue
            markers.append(
                MarkerRead(
                    transaction_id=trade.id,
                    side=trade.side,
                    date=bar_days[index],
                    trade_date=day,
                    snapped=bar_days[index] != day,
                    quantity=trade.quantity,
                    price=trade.price,
                    chart_price=chart_price(trade.price, day),
                )
            )
    return markers, undrawn


def _user_trades(db: Session, user_id: uuid.UUID, symbol: str) -> list[Transaction]:
    return list(
        db.scalars(
            select(Transaction)
            .where(Transaction.user_id == user_id, Transaction.symbol == symbol)
            .order_by(Transaction.executed_at, Transaction.created_at)
        )
    )


def _rank(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


@router.get("/{symbol}/history", response_model=HistoryRead)
def get_history(
    symbol: Symbol,
    user: CurrentUser,
    db: DbSession,
    market_data: UserMarketDataDep,
    history: UserPriceHistoryDep,
    stocks: UserStockHistoryDep,
    range_: Annotated[HistoryRange, Query(alias="range")] = "1Y",
    asset_type: Annotated[AssetType | None, Query(alias="type")] = None,
    coin_id: Annotated[str | None, Query(alias="id", min_length=1, max_length=128)] = None,
) -> HistoryRead:
    symbol = symbol.strip().upper()
    record = db.get(UserAsset, (user.id, symbol))
    asset_type = asset_type or (record.asset_type if record else None)
    if asset_type is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Say whether {symbol} is a stock or a crypto (type=stock or type=crypto).",
        )
    trades = _user_trades(db, user.id, symbol)
    view = HistoryRead(symbol=symbol, asset_type=asset_type, available=True, range=range_)

    def without_chart(**fields: object) -> HistoryRead:
        undrawn = [_undrawn(t, _trade_day(t, asset_type), "no_chart") for t in trades]
        return view.model_copy(update={**fields, "undrawn_trades": undrawn})

    if asset_type is AssetType.STOCK:
        if not stocks.stock_data_available:
            # Decided before anything else, so the answer doesn't reveal whether the symbol exists.
            return without_chart(available=False, unavailable_reason="not_available_on_deployment")
        if not stocks.configured:
            return without_chart(available=False, unavailable_reason="provider_not_configured")
        return _stock_history(view, stocks, symbol, range_, trades, without_chart)
    if not history.has_provider(asset_type):
        return without_chart(available=False, unavailable_reason="provider_not_configured")

    # Which coin: the one asked for, else the user's recorded one, else the coin rules.
    auto_picked, coin_name = False, None
    if coin_id:
        series = coin_id
        # The coin asked for is the user's own, chosen by the rules: keep saying so.
        auto_picked = (
            record is not None and record.provider_id == coin_id and record.id_source == RULE
        )
    elif record is not None and record.provider_id:
        series, auto_picked = record.provider_id, record.id_source == RULE
    else:
        try:
            quote = market_data.provider(asset_type).get_quote(symbol)
        except AmbiguousSymbolError as exc:
            candidates = [
                CoinCandidateRead(
                    id=c.provider_id, symbol=c.symbol, name=c.name, rank=_rank(c.market_cap_rank)
                )
                for c in exc.candidates
            ]
            return without_chart(ambiguous=True, candidates=candidates)
        except SymbolNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=exc.message) from exc
        except MarketDataError:
            return without_chart(is_stale=True, stale_reason=STALE_UNAVAILABLE)
        series = quote.coin_id or symbol.lower()
        coin_name, auto_picked = quote.coin_name, quote.coin_auto_picked

    today = history.now().astimezone(timezone.utc).date()
    first_trade = _trade_day(trades[0], asset_type) if trades else None
    requested_start = _range_start(range_, today, first_trade)
    try:
        result = history.closes(db, asset_type, series, requested_start, today)
    except SymbolNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=exc.message) from exc

    # The user's trades are recorded under one coin; on another coin's chart they'd be wrong.
    trades_coin = record.provider_id if record is not None else None
    if (
        coin_id
        and record is not None
        and record.id_source != RULE
        and trades_coin
        not in (
            None,
            coin_id,
        )
    ):
        markers: list[MarkerRead] = []
        undrawn = [_undrawn(t, _trade_day(t, asset_type), "different_coin") for t in trades]
    else:
        markers, undrawn = _place_trades(
            trades, asset_type, [b.day for b in result.bars], result.start, result.end
        )

    cut_short = (
        result.earliest_available is not None and requested_start < result.earliest_available
    )
    return view.model_copy(
        update={
            "provider": result.provider,
            "coin_id": series,
            "coin_name": coin_name,
            "coin_auto_picked": auto_picked,
            "range_start": result.start,
            "range_end": result.end,
            "range_note": (
                (HISTORY_LIMIT_NOTE if trades else HISTORY_LIMIT_NOTE_NO_TRADES)
                if cut_short
                else None
            ),
            "bars": [BarRead(date=b.day, close=b.close) for b in result.bars],
            "splits": [
                SplitRead(date=b.day, ratio=b.split_factor)
                for b in result.bars
                if b.split_factor != 1
            ],
            "markers": markers,
            "undrawn_trades": undrawn,
            "as_of": result.as_of,
            "is_stale": result.is_stale,
            "stale_reason": result.stale_reason,
        }
    )


def _stock_history(
    view: HistoryRead,
    stocks: UserStockHistory,
    symbol: str,
    range_: HistoryRange,
    trades: Sequence[Transaction],
    without_chart: Callable[..., HistoryRead],
) -> HistoryRead:
    today = stocks.now().astimezone(US_MARKET_TZ).date()
    first_trade = _trade_day(trades[0], AssetType.STOCK) if trades else None
    start = _range_start(range_, today, first_trade)
    capped = range_ == "ALL" and first_trade is None
    if capped:
        start = years_back(today, STOCK_ALL_YEARS)
    try:
        series = stocks.series(symbol, start, today)
    except SymbolNotFoundError as exc:
        # Our own wording, never the provider's.
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"No stock history found for {symbol}."
        ) from exc
    except RateLimitedError as exc:
        return without_chart(
            available=False, unavailable_reason="rate_limited", retry_after=exc.retry_after
        )
    except MarketDataError:
        return without_chart(available=False, unavailable_reason="provider_unavailable")

    end = series.bars[-1].day if series.bars else today
    markers, undrawn = _place_trades(
        trades, AssetType.STOCK, [b.day for b in series.bars], start, end, series.chart_price
    )
    return view.model_copy(
        update={
            "provider": series.provider,
            "adjustment": "split_adjusted",
            "range_start": start,
            "range_end": end,
            "range_note": STOCK_ALL_NOTE if capped else None,
            "bars": [BarRead(date=b.day, close=b.close) for b in series.bars],
            "splits": [SplitRead(date=x.day, ratio=x.factor) for x in series.splits],
            "markers": markers,
            "undrawn_trades": undrawn,
        }
    )
