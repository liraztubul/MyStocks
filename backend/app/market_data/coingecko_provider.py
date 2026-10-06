import threading
from collections.abc import Callable
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

import httpx2
from cachetools import TTLCache

from app.domain.enums import AssetType
from app.market_data.coin_resolution import CoinChoiceNeeded, CoinPick, resolve_coin
from app.market_data.dates import (
    ROLLING_CHANGE_WINDOW,
    crypto_close_snapshot_date,
    price_before_change,
    within_free_crypto_history,
)
from app.market_data.http import JsonResponse, get_json
from app.market_data.provider import (
    AmbiguousSymbolError,
    AssetMatch,
    PriceKind,
    PriceOnDate,
    PriceUnavailableError,
    ProviderUnavailableError,
    Quote,
    ReferenceKind,
    SymbolNotFoundError,
)

BASE_URL = "https://api.coingecko.com/api/v3"
NAME = "CoinGecko"
MAX_SEARCH_RESULTS = 8
# How long a ticker -> coin resolution is reused: holdings re-price every minute, and resolving
# costs a /search call each time otherwise. A coin's rank doesn't swing within an hour.
RESOLUTION_TTL_SECONDS = 3600
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
        self._resolutions: TTLCache[str, CoinPick | CoinChoiceNeeded | None] = TTLCache(
            maxsize=512, ttl=RESOLUTION_TTL_SECONDS
        )
        self._resolutions_lock = threading.Lock()

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

    def _search_all(self, query: str) -> list[AssetMatch]:
        coins = self._get("/search", {"query": query}).body.get("coins", [])
        return [
            AssetMatch(
                symbol=coin["symbol"].upper(),
                name=coin["name"],
                asset_type=AssetType.CRYPTO,
                provider_id=coin["id"],
                market_cap_rank=coin.get("market_cap_rank"),
            )
            for coin in coins
        ]

    def search(self, query: str) -> list[AssetMatch]:
        return self._search_all(query)[:MAX_SEARCH_RESULTS]

    def resolve(self, symbol: str) -> CoinPick | CoinChoiceNeeded | None:
        """Which coin a ticker means when the user didn't pick one (see coin_resolution)."""
        key = symbol.strip().upper()
        with self._resolutions_lock:
            if key in self._resolutions:
                return self._resolutions[key]
        # The full result list: the coin the user means can sit past the search box's first 8.
        result = resolve_coin(key, self._search_all(key))
        with self._resolutions_lock:
            self._resolutions[key] = result
        return result

    def _coin(self, symbol: str, provider_id: str | None) -> tuple[str, str | None, bool]:
        """(coin id, name if known, picked automatically?)"""
        if provider_id:
            return provider_id, None, False
        result = self.resolve(symbol)
        if result is None:
            raise SymbolNotFoundError(f"No coin found with symbol {symbol.upper()}.")
        if isinstance(result, CoinChoiceNeeded):
            raise AmbiguousSymbolError(result.symbol, result.candidates)
        return result.coin_id, result.name, True

    def get_quote(self, symbol: str, provider_id: str | None = None) -> Quote:
        coin_id, coin_name, auto_picked = self._coin(symbol, provider_id)
        body = self._get(
            "/simple/price",
            {
                "ids": coin_id,
                "vs_currencies": "usd",
                "include_last_updated_at": "true",
                "include_24hr_change": "true",
            },
        ).body
        entry = body.get(coin_id)
        if not entry or "usd" not in entry:
            raise SymbolNotFoundError(f"No USD price for {symbol.upper()} on CoinGecko.")
        updated = entry.get("last_updated_at")
        price = Decimal(entry["usd"])
        as_of = datetime.fromtimestamp(int(updated), tz=timezone.utc) if updated else self._now()
        # CoinGecko returns null for the 24h change when its data is stale; no base then.
        change_pct = entry.get("usd_24h_change")
        reference = None if change_pct is None else price_before_change(price, Decimal(change_pct))
        return Quote(
            symbol=symbol.upper(),
            asset_type=AssetType.CRYPTO,
            price=price,
            currency="USD",
            as_of=as_of,
            reference_price=reference,
            reference_at=as_of - ROLLING_CHANGE_WINDOW if reference is not None else None,
            reference_kind=ReferenceKind.ROLLING_24H if reference is not None else None,
            coin_id=coin_id,
            coin_name=coin_name,
            coin_auto_picked=auto_picked,
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

        coin_id, _, _ = self._coin(symbol, provider_id)
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
