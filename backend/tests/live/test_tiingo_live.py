"""Opt-in: one real Tiingo request through the adapter (run with -m live_network).

Asserts structure only (fields, order, positive Decimal values), never specific prices, and
prints nothing. Skipped unless TIINGO_API_KEY is set in the repo-root .env; tests/conftest.py
blanks the variable for every other test, so the key is read from the file here.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx2
import pytest

from app.core.config import Settings
from app.market_data.provider import RawStockBar
from app.market_data.tiingo_provider import TiingoProvider

pytestmark = pytest.mark.live_network


def _key(monkeypatch: pytest.MonkeyPatch) -> str | None:
    monkeypatch.delenv("TIINGO_API_KEY", raising=False)
    return Settings().tiingo_api_key


def test_tiingo_daily_bars_have_the_expected_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    key = _key(monkeypatch)
    if not key:
        pytest.skip("TIINGO_API_KEY not set")
    today = datetime.now(UTC).date()
    with httpx2.Client(timeout=30) as client:
        bars = TiingoProvider(key, client).fetch_daily("AAPL", today - timedelta(days=14), today)
    assert bars, "no bars for a two-week range"
    assert all(isinstance(b, RawStockBar) for b in bars)
    days = [b.day for b in bars]
    assert days == sorted(days) and len(set(days)) == len(days)
    assert all(isinstance(b.close, Decimal) and b.close > 0 for b in bars)
    assert all(isinstance(b.split_factor, Decimal) and b.split_factor > 0 for b in bars)
