from collections.abc import Callable
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

import httpx2

from app.domain.enums import AssetType
from app.market_data.dates import US_MARKET_TZ, resolve_stock_price_date, us_session_start
from app.market_data.http import get_json
from app.market_data.provider import (
    AssetMatch,
    PriceKind,
    PriceOnDate,
    PriceUnavailableError,
    ProviderUnavailableError,
    Quote,
    ReferenceKind,
    SymbolNotFoundError,
)

BASE_URL = "https://finnhub.io/api/v1"
NAME = "Finnhub"
MAX_SEARCH_RESULTS = 8


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class FinnhubProvider:
    """US stocks via Finnhub's free tier: /search and /quote only.

    Historical candles (/stock/candle) are Premium, so a past date can only be priced when the
    latest quote already covers it (see dates.resolve_stock_price_date).
    """

    def __init__(
        self,
        api_key: str | None,
        client: httpx2.Client,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._api_key = api_key
        self._client = client
        self._now = now

    def _get(self, path: str, params: dict[str, str]) -> Any:
        if not self._api_key:
            raise ProviderUnavailableError(
                "Stock data isn't configured: set FINNHUB_API_KEY in .env."
            )
        response = get_json(
            self._client,
            f"{BASE_URL}{path}",
            provider=NAME,
            params=params,
            endpoint=path,
            # Header rather than the ?token= query param keeps the key out of URLs and logs.
            headers={"X-Finnhub-Token": self._api_key},
        )
        if response.status_code in (401, 403):
            raise ProviderUnavailableError(
                "Finnhub rejected the request; check FINNHUB_API_KEY and the plan it's on."
            )
        if response.status_code >= 400:
            raise ProviderUnavailableError(f"Finnhub returned an error ({response.status_code}).")
        return response.body

    def search(self, query: str) -> list[AssetMatch]:
        body = self._get("/search", {"q": query, "exchange": "US"})
        return [
            AssetMatch(
                symbol=item["symbol"],
                name=item.get("description") or item["symbol"],
                asset_type=AssetType.STOCK,
                provider_id=item["symbol"],
            )
            for item in body.get("result", [])[:MAX_SEARCH_RESULTS]
        ]

    def get_quote(self, symbol: str, provider_id: str | None = None) -> Quote:
        symbol = (provider_id or symbol).upper()
        body = self._get("/quote", {"symbol": symbol})
        price = body.get("c")
        timestamp = body.get("t")
        # Finnhub answers unknown symbols with 200 and all-zero fields rather than a 404.
        if not price or not timestamp:
            raise SymbolNotFoundError(f"No US stock quote found for {symbol}.")
        as_of = datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
        previous_close = body.get("pc")
        # A missing or zero previous close (unknown symbol, first trading day) means there's no
        # base to measure from; a 0 base would turn the whole price into a bogus "change".
        has_reference = bool(previous_close) and Decimal(previous_close) > 0
        return Quote(
            symbol=symbol,
            asset_type=AssetType.STOCK,
            price=Decimal(price),
            currency="USD",
            as_of=as_of,
            reference_price=Decimal(previous_close) if has_reference else None,
            reference_at=us_session_start(as_of) if has_reference else None,
            reference_kind=ReferenceKind.PREVIOUS_CLOSE if has_reference else None,
        )

    def get_price_on(self, symbol: str, on: date, provider_id: str | None = None) -> PriceOnDate:
        now = self._now()
        if on > now.astimezone(US_MARKET_TZ).date():
            raise PriceUnavailableError("Can't look up a price for a future date.")

        quote = self.get_quote(symbol, provider_id)
        resolved = resolve_stock_price_date(on, quote.as_of, now)
        if resolved is None:
            raise PriceUnavailableError(
                f"Historical stock prices need a paid market-data plan (Finnhub's free tier "
                f"only has the latest quote, from {quote.as_of.astimezone(US_MARKET_TZ).date()}). "
                "Enter the price manually."
            )

        if not resolved.is_final_close:
            note = "Live price: the market is still open, so this isn't the day's close yet."
        elif resolved.price_date != on:
            note = f"{on} wasn't a trading day; using the {resolved.price_date} close."
        else:
            note = None
        return PriceOnDate(
            symbol=quote.symbol,
            asset_type=AssetType.STOCK,
            price=quote.price,
            currency="USD",
            requested_date=on,
            price_date=resolved.price_date,
            kind=PriceKind.CLOSE if resolved.is_final_close else PriceKind.LIVE,
            note=note,
        )
