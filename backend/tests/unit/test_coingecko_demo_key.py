"""The CoinGecko Demo key: sent as a header on every call, never echoed, checked at startup.

The key here is a made-up placeholder; the transports are fakes, so nothing reaches CoinGecko.
"""

import logging
import threading
import time
from collections.abc import Callable
from datetime import UTC, date, datetime

import httpx2
import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.core.config import settings
from app.domain.enums import AssetType
from app.market_data import service
from app.market_data.coingecko_provider import CoinGeckoProvider, KeyCheck
from app.market_data.http import CallCounter, provider_calls
from app.market_data.provider import (
    CoinRef,
    MarketDataError,
    PriceUnavailableError,
    ProviderUnavailableError,
)

FAKE_KEY = "CG-placeholder-not-a-real-key"
HEADER = "x-cg-demo-api-key"
NOW = datetime(2026, 10, 7, 12, tzinfo=UTC)

Handler = Callable[[httpx2.Request], httpx2.Response]


def provider(handler: Handler, key: str | None = FAKE_KEY) -> CoinGeckoProvider:
    client = httpx2.Client(transport=httpx2.MockTransport(handler))
    return CoinGeckoProvider(client, demo_api_key=key, now=lambda: NOW)


def every_call(cg: CoinGeckoProvider) -> None:
    """Quote, batch quote, search, both history endpoints; their outcomes don't matter here."""
    calls: list[Callable[[], object]] = [
        lambda: cg.get_quote("BTC", "bitcoin"),
        lambda: cg.get_quotes([CoinRef("bitcoin", "BTC"), CoinRef("ethereum", "ETH")]),
        lambda: cg.search("bitcoin"),
        lambda: cg.get_daily_closes("bitcoin", date(2026, 9, 1), date(2026, 9, 30)),
        lambda: cg.get_price_on("BTC", date(2026, 9, 1), "bitcoin"),
    ]
    for call in calls:
        try:
            call()
        except (MarketDataError, KeyError, TypeError, ValueError):
            pass


def recorder() -> tuple[list[httpx2.Request], Handler]:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json={})

    return seen, handler


def test_key_is_sent_as_a_header_on_every_call() -> None:
    seen, handler = recorder()
    every_call(provider(handler))
    paths = {r.url.path.removeprefix("/api/v3") for r in seen}
    assert paths == {
        "/simple/price",
        "/search",
        "/coins/bitcoin/market_chart/range",
        "/coins/bitcoin/history",
    }
    assert all(r.headers.get(HEADER) == FAKE_KEY for r in seen)
    # Header only: the key never goes into a URL (where it would land in access logs).
    assert all(FAKE_KEY not in str(r.url) for r in seen)
    assert all(r.url.host == "api.coingecko.com" for r in seen)


@pytest.mark.parametrize("key", [None, ""])
def test_no_header_without_a_key(key: str | None) -> None:
    seen, handler = recorder()
    every_call(provider(handler, key=key))
    assert seen and all(HEADER not in r.headers for r in seen)


def rejected(request: httpx2.Request) -> httpx2.Response:
    # The shape CoinGecko sent for an invalid Demo key in the 2026-10-07 probe.
    body = {"status": {"error_code": 10002, "error_message": "API Key Missing."}}
    return httpx2.Response(401, json=body)


def test_rejected_key_is_reported_without_the_key(caplog: pytest.LogCaptureFixture) -> None:
    cg = provider(rejected)
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(ProviderUnavailableError) as first:
            cg.get_quote("BTC", "bitcoin")
        with pytest.raises(ProviderUnavailableError):
            cg.search("btc")
    assert "API key" in first.value.message
    assert FAKE_KEY not in str(first.value)
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1  # once per process, not once per request
    assert FAKE_KEY not in caplog.text


def test_history_range_401_is_not_a_key_problem(caplog: pytest.LogCaptureFixture) -> None:
    # CoinGecko sends the 365-day history limit as HTTP 401 with error 10012 (observed live).
    def range_error(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(401, json={"error": {"status": {"error_code": 10012}}})

    with pytest.raises(PriceUnavailableError, match="older than 1 year"):
        provider(range_error).get_price_on("BTC", date(2025, 1, 1), "bitcoin")
    assert "rejected" not in caplog.text


def ok(_request: httpx2.Request) -> httpx2.Response:
    return httpx2.Response(200, json={"gecko_says": "(V3) To the Moon!"})


def server_error(_request: httpx2.Request) -> httpx2.Response:
    return httpx2.Response(500, json={})


@pytest.mark.parametrize(
    ("handler", "expected"),
    [(ok, KeyCheck.ACCEPTED), (rejected, KeyCheck.REJECTED), (server_error, KeyCheck.UNKNOWN)],
)
def test_key_check_uses_ping(handler: Handler, expected: KeyCheck) -> None:
    seen: list[httpx2.Request] = []

    def spy(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return handler(request)

    assert provider(spy).check_demo_key() is expected
    assert [r.url.path for r in seen] == ["/api/v3/ping"]
    assert seen[0].headers[HEADER] == FAKE_KEY


def network_down(request: httpx2.Request) -> httpx2.Response:
    raise httpx2.ConnectError("network is unreachable", request=request)


@pytest.mark.parametrize(
    ("handler", "level", "text"),
    [
        (network_down, logging.WARNING, "couldn't be reached"),
        (rejected, logging.WARNING, "REJECTED"),
        (ok, logging.INFO, "accepted"),
    ],
)
def test_startup_check_logs_status_never_the_key(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    handler: Handler,
    level: int,
    text: str,
) -> None:
    monkeypatch.setattr(service, "coingecko_provider", lambda: provider(handler))
    with caplog.at_level(logging.INFO):
        service.check_coingecko_key()
    assert any(r.levelno == level and text in r.getMessage() for r in caplog.records)
    assert FAKE_KEY not in caplog.text


def test_startup_check_without_a_key_makes_no_call(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    seen, handler = recorder()
    monkeypatch.setattr(service, "coingecko_provider", lambda: provider(handler, key=None))
    with caplog.at_level(logging.INFO):
        service.check_coingecko_key()
    assert seen == [] and "no Demo key configured" in caplog.text


def test_startup_check_never_raises(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def broken() -> CoinGeckoProvider:
        raise RuntimeError(f"boom {FAKE_KEY}")

    monkeypatch.setattr(service, "coingecko_provider", broken)
    service.check_coingecko_key()  # no exception
    assert "key status unknown" in caplog.text
    assert FAKE_KEY not in caplog.text  # the exception's text isn't logged


def test_startup_does_not_wait_for_the_check(monkeypatch: pytest.MonkeyPatch) -> None:
    release = threading.Event()
    started = threading.Event()

    def slow_check() -> None:
        started.set()
        release.wait(timeout=10)

    monkeypatch.setattr(main, "check_coingecko_key", slow_check)
    begin = time.monotonic()
    try:
        with TestClient(main.app) as client:
            assert client.get("/healthz").status_code == 200
            elapsed = time.monotonic() - begin
            assert started.wait(timeout=2)
            assert not release.is_set()  # the check is still running; the app already answers
        assert elapsed < 5
    finally:
        release.set()


def test_crypto_quotes_use_the_configured_ttl() -> None:
    crypto = service.shared_market_data().provider(AssetType.CRYPTO)
    assert crypto._live.ttl == settings.crypto_quote_ttl_seconds == 300  # type: ignore[attr-defined]


def test_call_counter_counts_and_reports_hourly(caplog: pytest.LogCaptureFixture) -> None:
    clock = [0.0]
    counter = CallCounter(timer=lambda: clock[0])
    with caplog.at_level(logging.INFO):
        counter.record("CoinGecko", "/simple/price", 200, cdn_hit=False)
        counter.record("CoinGecko", "/simple/price", 200, cdn_hit=True)
        counter.record("CoinGecko", "/search", 429, cdn_hit=False)
        assert caplog.text == ""
        clock[0] = 3600
        counter.record("CoinGecko", "/simple/price", None, cdn_hit=False)
    assert counter.snapshot() == {
        ("CoinGecko", "/simple/price", "ok"): 2,
        ("CoinGecko", "/simple/price", "cdn_hit"): 1,
        ("CoinGecko", "/search", "429"): 1,
        ("CoinGecko", "/simple/price", "error"): 1,
    }
    assert "CoinGecko /simple/price ok=2" in caplog.text


def test_coin_ids_are_not_endpoint_labels() -> None:
    _, handler = recorder()
    before = provider_calls.snapshot()
    provider(handler).get_daily_closes("some-coin", date(2026, 9, 1), date(2026, 9, 2))
    after = provider_calls.snapshot()
    changed = {k for k in after if after[k] != before.get(k)}
    assert changed == {("CoinGecko", "/coins/{id}/market_chart/range", "ok")}
    before = after
    provider(lambda _r: httpx2.Response(200, json=[])).top_coins(10)
    after = provider_calls.snapshot()
    assert {k for k in after if after[k] != before.get(k)} == {
        ("CoinGecko", "/coins/markets", "ok")
    }
