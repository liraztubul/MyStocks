import json
import logging
import threading
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx2

from app.market_data.provider import ProviderUnavailableError, RateLimitedError

logger = logging.getLogger(__name__)

REPORT_INTERVAL_SECONDS = 3600


class CallCounter:
    """Counts outgoing provider requests per provider and endpoint, and logs the counts about
    once an hour (on the first call after the hour is up; no background thread).

    "ok" is HTTP 200, which is what CoinGecko bills a credit for; "cdn_hit" counts responses its
    CDN served from cache (whether those cost a credit is not documented)."""

    def __init__(self, timer: Callable[[], float] = time.monotonic) -> None:
        self._timer = timer
        self._lock = threading.Lock()
        self._window: Counter[tuple[str, str, str]] = Counter()
        self._total: Counter[tuple[str, str, str]] = Counter()
        self._window_start = timer()

    def record(self, provider: str, endpoint: str, status: int | None, cdn_hit: bool) -> None:
        outcome = "error" if status is None else "ok" if status == 200 else str(status)
        report = None
        with self._lock:
            for key in [(provider, endpoint, outcome)] + (
                [(provider, endpoint, "cdn_hit")] if cdn_hit else []
            ):
                self._window[key] += 1
                self._total[key] += 1
            if self._timer() - self._window_start >= REPORT_INTERVAL_SECONDS:
                report = self._summary(self._window), self._summary(self._total)
                self._window.clear()
                self._window_start = self._timer()
        if report:
            logger.info("Provider calls, last hour: %s; since start: %s", *report)

    def snapshot(self) -> dict[tuple[str, str, str], int]:
        with self._lock:
            return dict(self._total)

    @staticmethod
    def _summary(counts: Counter[tuple[str, str, str]]) -> str:
        return ", ".join(f"{p} {e} {o}={n}" for (p, e, o), n in sorted(counts.items())) or "none"


provider_calls = CallCounter()


@dataclass(frozen=True)
class JsonResponse:
    status_code: int
    body: Any


def get_json(
    client: httpx2.Client,
    url: str,
    *,
    provider: str,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    endpoint: str | None = None,
) -> JsonResponse:
    """GET and parse JSON, mapping transport failures, 429s and 5xx to MarketDataErrors.

    Other 4xx responses are returned so each adapter can interpret its own error bodies.
    `endpoint` names the call in the usage counts (e.g. "/coins/{id}/history"); default: the URL.
    """
    label = endpoint or url
    try:
        response = client.get(url, params=params, headers=headers)
    except httpx2.HTTPError as exc:
        provider_calls.record(provider, label, None, cdn_hit=False)
        raise ProviderUnavailableError(f"{provider} is unreachable right now.") from exc
    provider_calls.record(
        provider,
        label,
        response.status_code,
        cdn_hit=response.headers.get("cf-cache-status", "").upper() == "HIT",
    )

    if response.status_code == 429:
        raise RateLimitedError(
            f"{provider} rate limit reached; try again in a minute.",
            retry_after=_retry_after(response),
        )
    if response.status_code >= 500:
        raise ProviderUnavailableError(f"{provider} is having problems right now.")

    try:
        # parse_float=Decimal keeps prices exact: a float would round them before we ever see them.
        body = json.loads(response.text, parse_float=Decimal)
    except ValueError as exc:
        raise ProviderUnavailableError(f"{provider} returned an unreadable response.") from exc
    return JsonResponse(status_code=response.status_code, body=body)


def _retry_after(response: httpx2.Response) -> int | None:
    value = response.headers.get("retry-after", "")
    return int(value) if value.isdigit() else None
