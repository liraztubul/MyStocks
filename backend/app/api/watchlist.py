"""The watchlist (W1: crypto only). Market data only through the gate (UserMarketDataDep).

Errors follow the app's conventions: 403 not_available_on_deployment (stocks for a blocked user),
409 asset_identity_conflict or watchlist_full, 422 ambiguous_symbol (with candidates) or
watchlist_crypto_only, 404 symbol_not_found, and 503 provider_unavailable / rate_limited only
when the coin had to be worked out by the provider.
"""

from typing import Annotated

from fastapi import APIRouter, Path, Response, status

from app.core.security import CurrentUser
from app.db.session import DbSession
from app.market_data.access import UserMarketDataDep
from app.schemas.watchlist import WatchlistAdd, WatchlistItemRead
from app.services import watchlist
from app.services.asset_identity import RULE

router = APIRouter(prefix="/watchlist", tags=["watchlist"])

Symbol = Annotated[str, Path(min_length=1, max_length=32)]


def _read(priced: watchlist.PricedItem) -> WatchlistItemRead:
    quote = priced.quote
    return WatchlistItemRead(
        symbol=priced.item.symbol,
        asset_type=priced.asset.asset_type,
        coin_id=priced.asset.provider_id,
        coin_auto_picked=priced.asset.id_source == RULE,
        added_at=priced.item.added_at,
        price=quote.price if quote else None,
        currency=quote.currency if quote else None,
        price_as_of=quote.as_of if quote else None,
        stale=bool(quote and quote.is_stale),
        change_pct=quote.change_24h_pct if quote else None,
        change_basis="24h_rolling" if quote and quote.change_24h_pct is not None else None,
        unavailable_code=priced.unavailable_code,
        unavailable_reason=priced.unavailable_reason,
    )


@router.get("", response_model=list[WatchlistItemRead])
def list_watchlist(
    user: CurrentUser, db: DbSession, market_data: UserMarketDataDep
) -> list[WatchlistItemRead]:
    return [_read(p) for p in watchlist.priced_items(db, market_data, user.id)]


@router.post("", response_model=WatchlistItemRead)
def add_to_watchlist(
    body: WatchlistAdd, user: CurrentUser, db: DbSession, market_data: UserMarketDataDep
) -> WatchlistItemRead:
    watchlist.add(db, market_data, user.id, body.symbol, body.type, body.id)
    priced = next(
        p for p in watchlist.priced_items(db, market_data, user.id) if p.item.symbol == body.symbol
    )
    return _read(priced)


@router.delete("/{symbol}", status_code=status.HTTP_204_NO_CONTENT)
def remove_from_watchlist(symbol: Symbol, user: CurrentUser, db: DbSession) -> Response:
    watchlist.remove(db, user.id, symbol.strip().upper())
    return Response(status_code=status.HTTP_204_NO_CONTENT)
