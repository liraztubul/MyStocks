"""The watchlist: symbols a user follows without holding them (W1: crypto only).

What a symbol means stays in user_assets; a watch only points at it. Writes take the same
per-user lock as trades, so the cap and the identity checks can't race.
"""

import uuid
from dataclasses import dataclass

from fastapi import status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.errors import CodedHTTPError
from app.db.models import UserAsset, WatchlistItem
from app.domain.enums import AssetType
from app.market_data.access import StockDataNotAvailableError, UserMarketData
from app.market_data.provider import CoinRef, MarketDataError, Quote
from app.services.asset_identity import (
    CONFLICT_CODE,
    RULE,
    USER,
    asset_in_use,
    ensure_asset_identity,
    lock_user_writes,
)

MAX_ITEMS = 50
FULL_CODE = "watchlist_full"
CRYPTO_ONLY_CODE = "watchlist_crypto_only"
NO_COIN_CODE = "coin_not_identified"


@dataclass(frozen=True)
class PricedItem:
    item: WatchlistItem
    asset: UserAsset
    quote: Quote | None
    # Why there is no quote: a MarketDataError code (provider_unavailable, symbol_not_found...).
    unavailable_code: str | None
    unavailable_reason: str | None


def _resolve_by_rules(market_data: UserMarketData, symbol: str) -> str:
    """The coin for a ticker the user didn't pick, by the coin rules. Raises MarketDataError:
    ambiguous (422, with candidates), unknown (404), or provider down (503); never guesses."""
    quote = market_data.provider(AssetType.CRYPTO).get_quote(symbol)
    if not quote.coin_id:
        raise CodedHTTPError(
            status.HTTP_422_UNPROCESSABLE_CONTENT, NO_COIN_CODE, "Pick the coin from search."
        )
    return quote.coin_id


def add(
    db: Session,
    market_data: UserMarketData,
    user_id: uuid.UUID,
    symbol: str,
    asset_type: AssetType,
    picked_id: str | None,
) -> WatchlistItem:
    if asset_type is AssetType.STOCK:
        if not market_data.stock_data_available:
            raise StockDataNotAvailableError()
        raise CodedHTTPError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            CRYPTO_ONLY_CODE,
            "Only crypto can be watched for now.",
        )
    lock_user_writes(db, user_id)

    existing = db.get(WatchlistItem, (user_id, symbol))
    record = db.get(UserAsset, (user_id, symbol))
    if existing is not None and (
        picked_id is None or record is None or picked_id == record.provider_id
    ):
        # Adding twice is a no-op, except that picking the coin the rules chose confirms it.
        if picked_id and record is not None and record.id_source == RULE:
            record.id_source = USER
            db.commit()
        return existing
    if existing is None:
        count = db.scalar(select(func.count()).where(WatchlistItem.user_id == user_id)) or 0
        if count >= MAX_ITEMS:
            raise CodedHTTPError(
                status.HTTP_409_CONFLICT,
                FULL_CODE,
                f"The watchlist holds up to {MAX_ITEMS} coins. Remove one to add another.",
            )

    stock_conflict = CodedHTTPError(
        status.HTTP_409_CONFLICT,
        CONFLICT_CODE,
        f"Your {symbol} entries are recorded as a stock, so it can't be watched as a coin.",
    )
    if record is not None and record.asset_type is not AssetType.CRYPTO:
        if asset_in_use(db, user_id, symbol):
            raise stock_conflict
        # An old stock meaning nothing uses any more binds nothing (the asset_identity rule).
        db.delete(record)
        db.flush()
        record = None

    if picked_id:
        # An explicit pick: no provider call. 409 if it contradicts the user's own earlier pick.
        ensure_asset_identity(db, market_data, user_id, symbol, AssetType.CRYPTO, picked_id)
    elif record is not None and record.provider_id:
        pass  # The coin is already known: no provider call, even if CoinGecko is down.
    else:
        # Nothing says which coin yet: the rules decide, which needs the provider.
        coin_id = _resolve_by_rules(market_data, symbol)
        if record is None:
            db.add(
                UserAsset(
                    user_id=user_id,
                    symbol=symbol,
                    asset_type=AssetType.CRYPTO,
                    provider_id=coin_id,
                    id_source=RULE,
                )
            )
        else:
            record.provider_id, record.id_source = coin_id, RULE
    db.flush()

    item = existing or WatchlistItem(user_id=user_id, symbol=symbol)
    if existing is None:
        db.add(item)
    db.commit()
    db.refresh(item)
    return item


def remove(db: Session, user_id: uuid.UUID, symbol: str) -> None:
    lock_user_writes(db, user_id)
    db.execute(
        delete(WatchlistItem).where(
            WatchlistItem.user_id == user_id, WatchlistItem.symbol == symbol
        )
    )
    db.flush()
    # The identity record goes too, unless trades still rely on it.
    record = db.get(UserAsset, (user_id, symbol))
    if record is not None and not asset_in_use(db, user_id, symbol):
        db.delete(record)
    db.commit()


def priced_items(db: Session, market_data: UserMarketData, user_id: uuid.UUID) -> list[PricedItem]:
    rows = db.execute(
        select(WatchlistItem, UserAsset)
        .join(
            UserAsset,
            (UserAsset.user_id == WatchlistItem.user_id)
            & (UserAsset.symbol == WatchlistItem.symbol),
        )
        .where(WatchlistItem.user_id == user_id)
        .order_by(WatchlistItem.added_at, WatchlistItem.symbol)
    ).all()
    coins = [
        CoinRef(asset.provider_id, item.symbol)
        for item, asset in rows
        if asset.asset_type is AssetType.CRYPTO and asset.provider_id
    ]
    quotes: dict[str, Quote | MarketDataError] = {}
    if coins:
        try:
            # One batched call for every coin not already cached.
            quotes = market_data.get_quotes(AssetType.CRYPTO, coins)
        except MarketDataError as exc:
            quotes = {c.coin_id: exc for c in coins}

    result = []
    for item, asset in rows:
        outcome = quotes.get(asset.provider_id) if asset.provider_id else None
        if isinstance(outcome, Quote):
            result.append(PricedItem(item, asset, outcome, None, None))
        elif isinstance(outcome, MarketDataError):
            result.append(PricedItem(item, asset, None, outcome.code, outcome.message))
        else:
            result.append(
                PricedItem(item, asset, None, NO_COIN_CODE, "No coin is recorded for this ticker.")
            )
    return result
