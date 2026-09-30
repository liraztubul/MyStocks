import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx2

from app.market_data.provider import ProviderUnavailableError, RateLimitedError


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
) -> JsonResponse:
    """GET and parse JSON, mapping transport failures, 429s and 5xx to MarketDataErrors.

    Other 4xx responses are returned so each adapter can interpret its own error bodies.
    """
    try:
        response = client.get(url, params=params, headers=headers)
    except httpx2.HTTPError as exc:
        raise ProviderUnavailableError(f"{provider} is unreachable right now.") from exc

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
