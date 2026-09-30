from collections.abc import Callable
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

import httpx2

from app.domain.enums import AssetType
from app.market_data.dates import crypto_close_snapshot_date, within_free_crypto_history
from app.market_data.http import JsonResponse, get_json
from app.market_data.provider import (
    AssetMatch,
    PriceKind,
    PriceOnDate,
    PriceUnavailableError,
    ProviderUnavailableError,
    Quote,
    SymbolNotFoundError,
)

BASE_URL = "https://api.coingecko.com/api/v3"
NAME = "CoinGecko"
MAX_SEARCH_RESULTS = 8
# CoinGecko error_code values (returned inside the JSON body).
HISTORY_RANGE_EXCEEDED = 10012
COIN_NOT_FOUND = 10013
OLD_HISTORY_MESSAGE = (
    "Crypto prices older than 1 year aren't available on CoinGecko's free plan. "
    "Enter the price manually."
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _error_code(body: Any) -> int | None:
    # Errors come back as {"error": {"status": {...}}} or {"status": {...}} depending on endpoint.
    if not isinstance(body, dict):
        return None
    status = (body.get("error") or body).get("status") or {}
    return status.get("error_code") if isinstance(status, dict) else None


class CoinGeckoProvider:
    """Crypto via CoinGecko's public API (keyless, or a free Demo key for higher limits)."""

    def __init__(
        self,
        client: httpx2.Client,
        demo_api_key: str | None = None,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._client = client
        self._headers = {"x-cg-demo-api-key": demo_api_key} if demo_api_key else {}
        self._now = now

    def _get(self, path: str, params: dict[str, str]) -> JsonResponse:
        response = get_json(
            self._client, f"{BASE_URL}{path}", provider=NAME, params=params, headers=self._headers
        )
        code = _error_code(response.body)
        if code == HISTORY_RANGE_EXCEEDED:
            raise PriceUnavailableError(OLD_HISTORY_MESSAGE)
        if code == COIN_NOT_FOUND or response.status_code == 404:
            raise SymbolNotFoundError("CoinGecko doesn't know that coin.")
        if response.status_code >= 400:
            raise ProviderUnavailableError(f"CoinGecko returned an error ({response.status_code}).")
        return response

    def search(self, query: str) -> list[AssetMatch]:
        coins = self._get("/search", {"query": query}).body.get("coins", [])
        return [
            AssetMatch(
                symbol=coin["symbol"].upper(),
                name=coin["name"],
                asset_type=AssetType.CRYPTO,
                provider_id=coin["id"],
            )
            for coin in coins[:MAX_SEARCH_RESULTS]
        ]

    def _coin_id(self, symbol: str, provider_id: str | None) -> str:
        if provider_id:
            return provider_id
        # Tickers aren't unique across coins; take the highest-ranked exact match, which is what
        # someone typing "BTC" means. The frontend passes the picked coin's id to skip this.
        matches = [m for m in self.search(symbol) if m.symbol == symbol.upper()]
        if not matches:
            raise SymbolNotFoundError(f"No coin found with symbol {symbol.upper()}.")
        return matches[0].provider_id

    def get_quote(self, symbol: str, provider_id: str | None = None) -> Quote:
        coin_id = self._coin_id(symbol, provider_id)
        body = self._get(
            "/simple/price",
            {"ids": coin_id, "vs_currencies": "usd", "include_last_updated_at": "true"},
        ).body
        entry = body.get(coin_id)
        if not entry or "usd" not in entry:
            raise SymbolNotFoundError(f"No USD price for {symbol.upper()} on CoinGecko.")
        updated = entry.get("last_updated_at")
        return Quote(
            symbol=symbol.upper(),
            asset_type=AssetType.CRYPTO,
            price=Decimal(entry["usd"]),
            currency="USD",
            as_of=datetime.fromtimestamp(int(updated), tz=timezone.utc) if updated else self._now(),
        )

    def get_price_on(self, symbol: str, on: date, provider_id: str | None = None) -> PriceOnDate:
        today = self._now().date()
        if on > today:
            raise PriceUnavailableError("Can't look up a price for a future date.")
        if on == today:
            quote = self.get_quote(symbol, provider_id)
            return PriceOnDate(
                symbol=quote.symbol,
                asset_type=AssetType.CRYPTO,
                price=quote.price,
                currency="USD",
                requested_date=on,
                price_date=on,
                kind=PriceKind.LIVE,
                note="Live price: today's UTC day isn't over, so there's no close yet.",
            )

        snapshot = crypto_close_snapshot_date(on)
        if not within_free_crypto_history(snapshot, today):
            raise PriceUnavailableError(OLD_HISTORY_MESSAGE)

        coin_id = self._coin_id(symbol, provider_id)
        body = self._get(
            f"/coins/{coin_id}/history",
            {"date": snapshot.strftime("%d-%m-%Y"), "localization": "false"},
        ).body
        usd = ((body.get("market_data") or {}).get("current_price") or {}).get("usd")
        if usd is None:
            raise PriceUnavailableError(
                f"CoinGecko has no price for {symbol.upper()} on {on} yet. Enter it manually."
            )
        return PriceOnDate(
            symbol=symbol.upper(),
            asset_type=AssetType.CRYPTO,
            price=Decimal(usd),
            currency="USD",
            requested_date=on,
            price_date=on,
            kind=PriceKind.CLOSE,
            note="UTC daily close (CoinGecko's 00:00 UTC snapshot of the next day).",
        )
