from collections.abc import Iterator
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.domain.enums import AssetType
from app.main import app
from app.market_data.provider import (
    AssetMatch,
    MarketDataError,
    PriceKind,
    PriceOnDate,
    ProviderUnavailableError,
    Quote,
)
from app.market_data.service import MarketData, shared_market_data

PASSWORD = "correct-horse-battery"


class StubProvider:
    def __init__(self, asset_type: AssetType, error: MarketDataError | None = None) -> None:
        self.asset_type = asset_type
        self.error = error

    def _maybe_fail(self) -> None:
        if self.error:
            raise self.error

    def search(self, query: str) -> list[AssetMatch]:
        self._maybe_fail()
        symbol = "AAPL" if self.asset_type is AssetType.STOCK else "BTC"
        provider_id = symbol if self.asset_type is AssetType.STOCK else "bitcoin"
        return [AssetMatch(symbol, f"{symbol} name", self.asset_type, provider_id)]

    def get_quote(self, symbol: str, provider_id: str | None = None) -> Quote:
        self._maybe_fail()
        as_of = datetime(2026, 3, 13, tzinfo=timezone.utc)
        return Quote(symbol, self.asset_type, Decimal("0.1"), "USD", as_of)

    def get_price_on(self, symbol: str, on: date, provider_id: str | None = None) -> PriceOnDate:
        self._maybe_fail()
        return PriceOnDate(
            symbol,
            self.asset_type,
            Decimal("211.5000000001"),
            "USD",
            requested_date=on,
            price_date=date(2026, 3, 13),
            kind=PriceKind.CLOSE,
            note="fell back",
        )


@pytest.fixture
def providers() -> dict[AssetType, StubProvider]:
    return {asset_type: StubProvider(asset_type) for asset_type in AssetType}


@pytest.fixture
def authed(client: TestClient, providers: dict[AssetType, StubProvider]) -> Iterator[TestClient]:
    app.dependency_overrides[shared_market_data] = lambda: MarketData(providers)
    client.post("/api/auth/register", json={"email": "a@example.com", "password": PASSWORD})
    client.post("/api/auth/login", json={"email": "a@example.com", "password": PASSWORD})
    yield client


def test_search_merges_both_providers_tagged_by_type(authed: TestClient) -> None:
    body = authed.get("/api/assets/search", params={"q": "a"}).json()
    assert [(r["symbol"], r["asset_type"], r["provider_id"]) for r in body["results"]] == [
        ("AAPL", "stock", "AAPL"),
        ("BTC", "crypto", "bitcoin"),
    ]
    assert body["unavailable"] == []


def test_search_degrades_when_one_provider_is_down(
    authed: TestClient, providers: dict[AssetType, StubProvider]
) -> None:
    providers[AssetType.STOCK].error = ProviderUnavailableError("Finnhub is unreachable.")
    response = authed.get("/api/assets/search", params={"q": "a"})
    assert response.status_code == 200
    body = response.json()
    assert [r["symbol"] for r in body["results"]] == ["BTC"]
    assert body["unavailable"] == [
        {"asset_type": "stock", "code": "provider_unavailable", "detail": "Finnhub is unreachable."}
    ]


def test_search_fails_with_503_only_when_every_provider_is_down(
    authed: TestClient, providers: dict[AssetType, StubProvider]
) -> None:
    for provider in providers.values():
        provider.error = ProviderUnavailableError("down")
    response = authed.get("/api/assets/search", params={"q": "a"})
    assert response.status_code == 503
    assert response.json()["code"] == "provider_unavailable"


def test_price_on_returns_decimal_string_and_fallback_flag(authed: TestClient) -> None:
    response = authed.get(
        "/api/assets/AAPL/price-on", params={"date": "2026-03-14", "asset_type": "stock"}
    )
    assert response.status_code == 200
    assert response.json() == {
        "symbol": "AAPL",
        "asset_type": "stock",
        "price": "211.5000000001",
        "currency": "USD",
        "requested_date": "2026-03-14",
        "price_date": "2026-03-13",
        "is_fallback": True,
        "kind": "close",
        "note": "fell back",
    }


def test_quote_returns_decimal_string(authed: TestClient) -> None:
    response = authed.get("/api/assets/BTC/quote", params={"asset_type": "crypto"})
    assert response.json()["price"] == "0.1"


@pytest.mark.parametrize(
    ("error_name", "status", "code"),
    [
        ("SymbolNotFoundError", 404, "symbol_not_found"),
        ("PriceUnavailableError", 404, "price_unavailable"),
        ("RateLimitedError", 503, "rate_limited"),
        ("ProviderUnavailableError", 503, "provider_unavailable"),
    ],
)
def test_provider_errors_map_to_clear_json_never_500(
    authed: TestClient,
    providers: dict[AssetType, StubProvider],
    error_name: str,
    status: int,
    code: str,
) -> None:
    import app.market_data.provider as provider_module

    error_cls = getattr(provider_module, error_name)
    providers[AssetType.STOCK].error = error_cls("explained", retry_after=15)
    response = authed.get(
        "/api/assets/AAPL/price-on", params={"date": "2026-03-14", "asset_type": "stock"}
    )
    assert response.status_code == status
    assert response.json() == {"detail": "explained", "code": code}
    if code == "rate_limited":
        assert response.headers["retry-after"] == "15"


def test_price_on_requires_valid_params(authed: TestClient) -> None:
    missing_date = authed.get("/api/assets/AAPL/price-on", params={"asset_type": "stock"})
    assert missing_date.status_code == 422
    bad_type = authed.get(
        "/api/assets/AAPL/price-on", params={"date": "2026-03-14", "asset_type": "bond"}
    )
    assert bad_type.status_code == 422


def test_assets_require_auth(client: TestClient) -> None:
    assert client.get("/api/assets/search", params={"q": "a"}).status_code == 401
