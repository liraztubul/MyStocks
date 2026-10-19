"""Tiingo end-of-day stock prices, transient only (see app.market_data.stock_history).

Verified on 2026-10-16 (docs and a probe):
- GET https://api.tiingo.com/tiingo/daily/<ticker>/prices?startDate=YYYY-MM-DD&endDate=YYYY-MM-DD,
  authenticated with the header "Authorization: Token <key>" (never the token= URL parameter).
- Each row's "date" is the trading day at midnight UTC ("2020-08-26T00:00:00.000Z").
- splitFactor = splitTo / splitFrom (a 4:1 split is 4.0) and sits on the ex-date bar.
- An unknown ticker is HTTP 404 with a JSON "detail"; that text is never passed on.
- Share classes use '-' (BRK-B); "BRK.B" is a 404.
- columns=close,splitFactor narrows the response, but it isn't documented on the end-of-day
  page, so every response is checked and a missing column is IncompleteResponseError.
Only the date, close and split factor of each row are kept; everything else is dropped as it
arrives. Nothing is logged except the call counter's provider, endpoint and status.
"""

from datetime import date
from decimal import Decimal
from typing import Any

import httpx2

from app.market_data.http import get_json
from app.market_data.provider import (
    IncompleteResponseError,
    ProviderUnavailableError,
    RawStockBar,
    SymbolNotFoundError,
)

BASE_URL = "https://api.tiingo.com/tiingo/daily"
NAME = "Tiingo"
NARROW_COLUMNS = "close,splitFactor"


def _decimal(value: Any) -> Decimal | None:
    # JSON floats arrive as Decimal (get_json); an integral price can arrive as int.
    if isinstance(value, bool) or not isinstance(value, Decimal | int):
        return None
    return Decimal(value)


class TiingoProvider:
    name = "tiingo"

    def __init__(self, api_key: str, client: httpx2.Client) -> None:
        self._headers = {"Authorization": f"Token {api_key}"}
        self._client = client

    def fetch_daily(
        self, ticker: str, start: date, end: date, *, narrow: bool = True
    ) -> list[RawStockBar]:
        params = {"startDate": start.isoformat(), "endDate": end.isoformat()}
        if narrow:
            params["columns"] = NARROW_COLUMNS
        response = get_json(
            self._client,
            f"{BASE_URL}/{ticker}/prices",
            provider=NAME,
            params=params,
            headers=self._headers,
            # The ticker stays out of the usage counts.
            endpoint="/tiingo/daily/{ticker}/prices",
        )
        if response.status_code == 404:
            raise SymbolNotFoundError(f"No stock history found for {ticker}.")
        if response.status_code in (401, 403):
            raise ProviderUnavailableError(
                "Tiingo rejected the request; check TIINGO_API_KEY and the plan it's on."
            )
        if response.status_code >= 400:
            raise ProviderUnavailableError(f"Tiingo returned an error ({response.status_code}).")
        if not isinstance(response.body, list):
            raise ProviderUnavailableError("Tiingo returned an unexpected response.")
        return [self._bar(row, narrow) for row in response.body]

    @staticmethod
    def _bar(row: Any, narrow: bool) -> RawStockBar:
        if not isinstance(row, dict) or not isinstance(row.get("date"), str):
            raise ProviderUnavailableError("Tiingo returned an unexpected row.")
        close, factor = _decimal(row.get("close")), _decimal(row.get("splitFactor"))
        if close is None or factor is None:
            if narrow:
                raise IncompleteResponseError("Tiingo ignored the requested columns.")
            raise ProviderUnavailableError("Tiingo returned a row without a close or split factor.")
        try:
            day = date.fromisoformat(row["date"][:10])
        except ValueError as exc:
            raise ProviderUnavailableError("Tiingo returned an unreadable date.") from exc
        return RawStockBar(day=day, close=close, split_factor=factor)
