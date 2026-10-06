from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.core.config import settings
from app.domain.enums import AssetType
from app.market_data.access import StockDataNotAvailableError, UserMarketData, stock_data_allowed
from app.market_data.provider import AssetMatch, PriceOnDate, Quote
from app.market_data.service import MarketData


class CountingProvider:
    def __init__(self, asset_type: AssetType) -> None:
        self.asset_type = asset_type
        self.calls = 0

    def search(self, query: str) -> list[AssetMatch]:
        self.calls += 1
        return [AssetMatch(query.upper(), query, self.asset_type, query)]

    def get_quote(self, symbol: str, provider_id: str | None = None) -> Quote:
        self.calls += 1
        return Quote(
            symbol, self.asset_type, Decimal("1"), "USD", datetime(2026, 10, 6, tzinfo=UTC)
        )

    def get_price_on(self, symbol: str, on: date, provider_id: str | None = None) -> PriceOnDate:
        self.calls += 1
        raise NotImplementedError


@pytest.mark.parametrize(
    ("environment", "configured", "email", "allowed"),
    [
        ("production", None, "owner@example.com", False),
        ("production", "", "owner@example.com", False),
        ("production", " , ", "owner@example.com", False),
        ("development", None, "anyone@example.com", True),
        ("development", "", "anyone@example.com", True),
        ("production", "owner@example.com", "owner@example.com", True),
        ("production", "owner@example.com", "other@example.com", False),
        ("development", "owner@example.com", "other@example.com", False),
        # The configured list is normalized too: case and spaces don't matter.
        ("production", "  Owner@Example.COM , second@example.com", "owner@example.com", True),
        ("production", "owner@example.com,second@example.com", "second@example.com", True),
    ],
)
def test_allowlist_rule(
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
    configured: str | None,
    email: str,
    allowed: bool,
) -> None:
    monkeypatch.setattr(settings, "environment", environment)
    monkeypatch.setattr(settings, "stock_data_allowed_emails", configured)
    assert stock_data_allowed(email) is allowed


def _gated(allowed: bool) -> tuple[UserMarketData, CountingProvider, CountingProvider]:
    stocks, crypto = CountingProvider(AssetType.STOCK), CountingProvider(AssetType.CRYPTO)
    shared = MarketData({AssetType.STOCK: stocks, AssetType.CRYPTO: crypto})
    return UserMarketData(shared, stock_data_available=allowed), stocks, crypto


def test_blocked_user_never_reaches_the_stock_provider() -> None:
    gated, stocks, _ = _gated(allowed=False)
    with pytest.raises(StockDataNotAvailableError):
        gated.provider(AssetType.STOCK).get_quote("AAPL")
    with pytest.raises(StockDataNotAvailableError):
        gated.provider(AssetType.STOCK).get_price_on("AAPL", date(2026, 10, 1))
    assert stocks.calls == 0


def test_blocked_user_still_gets_crypto() -> None:
    gated, _, crypto = _gated(allowed=False)
    assert gated.provider(AssetType.CRYPTO).get_quote("BTC").price == Decimal("1")
    assert crypto.calls == 1


def test_blocked_search_skips_stocks_and_says_why() -> None:
    gated, stocks, crypto = _gated(allowed=False)
    result = gated.search("abc")
    assert [m.asset_type for m in result.matches] == [AssetType.CRYPTO]
    assert [(f.asset_type, f.error.code) for f in result.failures] == [
        (AssetType.STOCK, "not_available_on_deployment")
    ]
    assert (stocks.calls, crypto.calls) == (0, 1)


def test_allowed_user_passes_through() -> None:
    gated, stocks, _ = _gated(allowed=True)
    gated.provider(AssetType.STOCK).get_quote("AAPL")
    assert {m.asset_type for m in gated.search("abc").matches} == {
        AssetType.STOCK,
        AssetType.CRYPTO,
    }
    assert stocks.calls == 2
