import uuid
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from decimal import Decimal

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.assets import MarketDataDep
from app.core.security import CurrentUser
from app.db.models import Transaction
from app.db.session import DbSession
from app.domain.enums import AssetType
from app.domain.pnl import (
    OversoldLedgerError,
    Portfolio,
    Position,
    positions_by_symbol,
    total_realized,
    value_portfolio,
)
from app.market_data.provider import MarketDataError, Quote
from app.market_data.service import MarketData
from app.schemas.portfolio import (
    AllocationRead,
    HoldingRead,
    PortfolioSummaryRead,
    RealizedPlRead,
    RealizedSaleRead,
)

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

CURRENCY = "USD"
MAX_QUOTE_WORKERS = 8


@dataclass(frozen=True)
class PriceResult:
    quote: Quote | None
    error: str | None


def _replay(db: Session, user_id: uuid.UUID) -> tuple[list[Transaction], dict[str, Position]]:
    trades = list(db.scalars(select(Transaction).where(Transaction.user_id == user_id)))
    try:
        return trades, positions_by_symbol(trades)
    except OversoldLedgerError as exc:
        # Only reachable after deleting a buy (DELETE isn't re-validated); any numbers computed
        # from such a history would be wrong, so refuse rather than guess.
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                f"Your {exc.symbol} history sells more than it held at some point, probably "
                f"after a buy was deleted. Fix or delete the {exc.symbol} sells to see P/L."
            ),
        ) from exc


def _asset_types(trades: Sequence[Transaction]) -> dict[str, AssetType]:
    # The ledger groups by symbol alone; the latest trade's type decides which provider prices it.
    latest = sorted(trades, key=lambda t: t.executed_at)
    return {t.symbol: t.asset_type for t in latest}


def _fetch_price(market_data: MarketData, symbol: str, asset_type: AssetType) -> PriceResult:
    try:
        return PriceResult(market_data.provider(asset_type).get_quote(symbol), None)
    except MarketDataError as exc:
        return PriceResult(None, exc.message)


def _fetch_prices(market_data: MarketData, symbols: dict[str, AssetType]) -> dict[str, PriceResult]:
    if not symbols:
        return {}
    # In parallel: with a provider down, each lookup waits out its timeout, and doing them in
    # sequence would make the whole response that many timeouts long.
    with ThreadPoolExecutor(max_workers=min(MAX_QUOTE_WORKERS, len(symbols))) as pool:
        futures = {
            symbol: pool.submit(_fetch_price, market_data, symbol, asset_type)
            for symbol, asset_type in symbols.items()
        }
        return {symbol: future.result() for symbol, future in futures.items()}


@dataclass(frozen=True)
class ValuedPortfolio:
    portfolio: Portfolio[Transaction]
    asset_types: dict[str, AssetType]
    prices: dict[str, PriceResult]


def _load_valued_portfolio(
    db: Session, user_id: uuid.UUID, market_data: MarketData
) -> ValuedPortfolio:
    trades, positions = _replay(db, user_id)
    asset_types = _asset_types(trades)
    open_symbols = {s: asset_types[s] for s, p in positions.items() if p.quantity > 0}
    prices = _fetch_prices(market_data, open_symbols)

    def price_of(symbol: str) -> Decimal | None:
        quote = prices[symbol].quote
        return quote.price if quote else None

    return ValuedPortfolio(value_portfolio(positions, price_of), asset_types, prices)


@router.get("/holdings", response_model=list[HoldingRead])
def get_holdings(user: CurrentUser, db: DbSession, market_data: MarketDataDep) -> list[HoldingRead]:
    valued = _load_valued_portfolio(db, user.id, market_data)
    rows = []
    for holding in valued.portfolio.holdings:
        position, valuation = holding.position, holding.valuation
        price = valued.prices[position.symbol]
        rows.append(
            HoldingRead(
                symbol=position.symbol,
                asset_type=valued.asset_types[position.symbol],
                quantity=position.quantity,
                average_cost=position.average_cost,
                cost_basis=position.cost_basis,
                current_price=valuation.price if valuation else None,
                market_value=valuation.market_value if valuation else None,
                unrealized_pl=valuation.unrealized if valuation else None,
                unrealized_pl_pct=valuation.unrealized_pct if valuation else None,
                allocation_pct=holding.allocation_pct,
                price_as_of=price.quote.as_of if price.quote else None,
                price_is_stale=bool(price.quote and price.quote.is_stale),
                price_unavailable_reason=price.error,
            )
        )
    return rows


@router.get("/summary", response_model=PortfolioSummaryRead)
def get_summary(
    user: CurrentUser, db: DbSession, market_data: MarketDataDep
) -> PortfolioSummaryRead:
    valued = _load_valued_portfolio(db, user.id, market_data)
    portfolio = valued.portfolio
    return PortfolioSummaryRead(
        currency=CURRENCY,
        total_cost_basis=portfolio.total_cost_basis,
        total_market_value=portfolio.total_market_value,
        total_unrealized_pl=portfolio.total_unrealized,
        total_unrealized_pl_pct=portfolio.total_unrealized_pct,
        total_realized_pl=portfolio.total_realized,
        allocation=[
            AllocationRead(
                symbol=h.position.symbol,
                market_value=h.valuation.market_value,
                allocation_pct=h.allocation_pct,
            )
            for h in portfolio.holdings
            if h.valuation is not None and h.allocation_pct is not None
        ],
        unpriced_symbols=list(portfolio.unpriced_symbols),
        has_stale_prices=any(p.quote and p.quote.is_stale for p in valued.prices.values()),
    )


@router.get("/realized-pl", response_model=RealizedPlRead)
def get_realized_pl(user: CurrentUser, db: DbSession) -> RealizedPlRead:
    _, positions = _replay(db, user.id)
    sales = sorted(
        (sale for position in positions.values() for sale in position.sales),
        key=lambda s: (s.trade.executed_at, s.trade.created_at),
        reverse=True,
    )
    return RealizedPlRead(
        currency=CURRENCY,
        total_realized_pl=total_realized(positions.values()),
        sales=[
            RealizedSaleRead(
                transaction_id=sale.trade.id,
                symbol=sale.trade.symbol,
                executed_at=sale.trade.executed_at,
                quantity=sale.trade.quantity,
                price=sale.trade.price,
                fee=sale.trade.fee,
                average_cost=sale.average_cost,
                cost_basis=sale.cost_basis,
                proceeds=sale.proceeds,
                realized_pl=sale.realized,
            )
            for sale in sales
        ],
    )
