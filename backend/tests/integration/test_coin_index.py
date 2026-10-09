"""The coin index: matching through the API, and lazy refresh against a real database.

The refresh tests commit for real (the refresh runs in its own thread and session) and clear
the shared coin_index table before and after each test.
"""

import threading
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import CoinIndexEntry
from app.main import app
from app.market_data.coin_index import (
    INDEX_LOADING,
    INDEX_UNAVAILABLE,
    CoinIndexService,
    shared_coin_index,
)
from app.market_data.provider import CoinListing, ProviderUnavailableError

PASSWORD = "correct-horse-battery"
INVITE = "test-invite"


class FakeList:
    """Top coins on demand. `gate` holds the call until set; `during` runs inside the call."""

    def __init__(self, coins: list[CoinListing]) -> None:
        self.coins = coins
        self.calls = 0
        self.fail = False
        self.gate: threading.Event | None = None
        self.during: Callable[[], None] | None = None
        self._lock = threading.Lock()

    def top_coins(self, limit: int) -> list[CoinListing]:
        with self._lock:
            self.calls += 1
        if self.during:
            self.during()
        if self.gate is not None:
            self.gate.wait(10)
        if self.fail:
            raise ProviderUnavailableError("CoinGecko is unreachable right now.")
        return self.coins[:limit]


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 9, 12, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


OLD = [CoinListing("bitcoin", "BTC", "Bitcoin", 1), CoinListing("ethereum", "ETH", "Ethereum", 2)]
NEW = [*OLD, CoinListing("pepe", "PEPE", "Pepe", 30)]


def entry(
    provider_id: str, symbol: str, name: str, rank: int | None, at: datetime
) -> CoinIndexEntry:
    return CoinIndexEntry(
        provider_id=provider_id, symbol=symbol, name=name, market_cap_rank=rank, updated_at=at
    )


# --- Matching, through the API (rolled-back test transaction) ----------------------------------


@pytest.fixture
def source() -> FakeList:
    return FakeList(NEW)


@pytest.fixture
def api(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, source: FakeList, db_session: Session
) -> Iterator[TestClient]:
    monkeypatch.setattr(settings, "registration_invite_code", INVITE)
    service = CoinIndexService(source, lambda: db_session)
    app.dependency_overrides[shared_coin_index] = lambda: service
    body = {"email": "coins@example.com", "password": PASSWORD, "invite_code": INVITE}
    client.post("/api/auth/register", json=body)
    assert client.post("/api/auth/login", json={"email": body["email"], "password": PASSWORD})
    yield client


def seed(db: Session, rows: list[tuple[str, str, str, int | None]]) -> None:
    now = datetime.now(UTC)
    db.add_all(entry(*r, now) for r in rows)
    db.commit()


def suggest(api: TestClient, q: str) -> Any:
    response = api.get("/api/coins/suggest", params={"q": q})
    assert response.status_code == 200, response.text
    return response.json()


def test_login_required(api: TestClient) -> None:
    api.cookies.clear()
    assert api.get("/api/coins/suggest", params={"q": "bit"}).status_code == 401


def test_match_order(api: TestClient, db_session: Session, source: FakeList) -> None:
    seed(
        db_session,
        [
            ("orbit-chain", "ORB", "Orbit Chain", 5),  # name contains "bit"
            ("wrapped-bitcoin", "WBTC", "Wrapped Bitcoin", 15),  # a name word starts with it
            ("bittorrent", "BTT", "BitTorrent", 80),  # name prefix, lower rank
            ("bitcoin", "BTC", "Bitcoin", 1),  # name prefix
            ("nullbit", "BITN", "Nullbit", None),  # ticker prefix, unranked
            ("bit-x", "BITX", "Some X", 70),  # ticker prefix
            ("bitdao", "BIT", "BitDAO", 60),  # exact ticker
            ("ethereum", "ETH", "Ethereum", 2),  # no match
        ],
    )
    body = suggest(api, "bit")
    assert [c["symbol"] for c in body["results"]] == [
        "BIT",
        "BITX",
        "BITN",
        "BTC",
        "BTT",
        "WBTC",
        "ORB",
    ]
    assert body["results"][3] == {
        "provider_id": "bitcoin",
        "symbol": "BTC",
        "name": "Bitcoin",
        "market_cap_rank": 1,
    }
    assert body["reason"] is None
    assert source.calls == 0  # fresh index: no provider call


def test_at_most_eight_results_by_rank(api: TestClient, db_session: Session) -> None:
    seed(db_session, [(f"coin-{i}", f"CO{i}", f"Coin {i}", 20 - i) for i in range(12)])
    ranks = [c["market_cap_rank"] for c in suggest(api, "co")["results"]]
    assert ranks == sorted(ranks) and len(ranks) == 8 and ranks[0] == 9


def test_like_wildcards_are_matched_literally(api: TestClient, db_session: Session) -> None:
    seed(
        db_session,
        [
            ("hundred", "HND", "100% Coin", 10),
            ("under", "U_S", "Under_score", 11),
            ("plain", "PLN", "Plain", 12),
            ("slash", "SLH", "Back\\slash", 13),
        ],
    )
    assert [c["symbol"] for c in suggest(api, "0%")["results"]] == ["HND"]
    assert [c["symbol"] for c in suggest(api, "%%")["results"]] == []
    assert [c["symbol"] for c in suggest(api, "__")["results"]] == []
    assert [c["symbol"] for c in suggest(api, "r_s")["results"]] == ["U_S"]
    assert [c["symbol"] for c in suggest(api, "k\\s")["results"]] == ["SLH"]


def test_short_queries_return_nothing(api: TestClient, db_session: Session) -> None:
    seed(db_session, [("bitcoin", "BTC", "Bitcoin", 1)])
    for q in ["", "b", "  b  "]:
        assert suggest(api, q) == {"results": [], "reason": None}
    assert [c["symbol"] for c in suggest(api, "  bt  ")["results"]] == ["BTC"]


def test_query_length_is_capped(api: TestClient, db_session: Session) -> None:
    seed(db_session, [("bitcoin", "BTC", "Bitcoin", 1)])
    assert suggest(api, "bitcoin" + "x" * 100)["results"] == []  # trimmed to 50, no error
    assert api.get("/api/coins/suggest", params={"q": "x" * 201}).status_code == 422


def test_empty_index_and_provider_down(api: TestClient, source: FakeList) -> None:
    source.fail = True
    assert suggest(api, "bit") == {"results": [], "reason": INDEX_UNAVAILABLE}
    assert suggest(api, "bit") == {"results": [], "reason": INDEX_UNAVAILABLE}
    assert source.calls == 1  # the second request is inside the cooldown


# --- Lazy refresh (real commits, own sessions) ---------------------------------------------------


@pytest.fixture
def clean_index(engine: Engine) -> Iterator[None]:
    def clear() -> None:
        with Session(engine) as db:
            db.execute(delete(CoinIndexEntry))
            db.commit()

    clear()
    yield
    clear()


def service(engine: Engine, source: FakeList, clock: Clock, **kw: Any) -> CoinIndexService:
    return CoinIndexService(source, lambda: Session(engine), now=clock, **kw)


def store(engine: Engine, coins: list[CoinListing], at: datetime) -> None:
    with Session(engine) as db:
        db.add_all(entry(c.provider_id, c.symbol, c.name, c.market_cap_rank, at) for c in coins)
        db.commit()


def index(engine: Engine) -> tuple[list[str], datetime | None]:
    with Session(engine) as db:
        ids = list(db.scalars(select(CoinIndexEntry.provider_id).order_by("provider_id")))
        return ids, db.scalar(select(func.max(CoinIndexEntry.updated_at)))


def settle(svc: CoinIndexService) -> None:
    """Waits for the refresh in flight, if any, without starting one."""
    flight = svc._flight
    if flight is not None:
        flight.join(5)


def ask(engine: Engine, svc: CoinIndexService, q: str) -> tuple[list[str], str | None]:
    with Session(engine) as db:
        found = svc.suggest(db, q)
        return [c.symbol for c in found.coins], found.reason


@pytest.mark.usefixtures("clean_index")
def test_stale_index_is_served_while_one_refresh_runs(engine: Engine) -> None:
    clock, source = Clock(), FakeList(NEW)
    store(engine, OLD, clock.now - timedelta(hours=25))
    source.gate = threading.Event()
    svc = service(engine, source, clock)

    assert ask(engine, svc, "pe") == ([], None)  # old index, answered at once: no PEPE yet
    assert ask(engine, svc, "bit") == (["BTC"], None)
    assert svc._flight is not None and svc._flight.is_alive()
    assert source.calls == 1  # both requests share the one refresh

    source.gate.set()
    settle(svc)
    assert index(engine) == (["bitcoin", "ethereum", "pepe"], clock.now)
    assert ask(engine, svc, "pe") == (["PEPE"], None)
    assert source.calls == 1  # fresh again: no more provider calls


@pytest.mark.usefixtures("clean_index")
def test_concurrent_first_requests_cause_one_fetch(engine: Engine) -> None:
    clock, source = Clock(), FakeList(NEW)
    svc = service(engine, source, clock)
    start = threading.Barrier(8)
    answers: list[tuple[list[str], str | None]] = []

    def request() -> None:
        start.wait()
        answers.append(ask(engine, svc, "pepe"))

    threads = [threading.Thread(target=request) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert source.calls == 1
    assert answers == [(["PEPE"], None)] * 8  # each waited for the same refresh


@pytest.mark.usefixtures("clean_index")
def test_failed_refresh_keeps_old_rows_and_cools_down(engine: Engine) -> None:
    clock, source = Clock(), FakeList(NEW)
    stale_at = clock.now - timedelta(hours=30)
    store(engine, OLD, stale_at)
    source.fail = True
    svc = service(engine, source, clock, cooldown=timedelta(minutes=15))

    assert ask(engine, svc, "eth") == (["ETH"], None)
    settle(svc)
    assert index(engine) == (["bitcoin", "ethereum"], stale_at)  # old rows kept
    assert source.calls == 1

    clock.now += timedelta(minutes=10)
    assert ask(engine, svc, "eth") == (["ETH"], None)
    assert source.calls == 1  # inside the cooldown: no retry

    clock.now += timedelta(minutes=6)
    source.fail = False
    ask(engine, svc, "eth")
    settle(svc)
    assert source.calls == 2
    assert index(engine)[0] == ["bitcoin", "ethereum", "pepe"]


@pytest.mark.usefixtures("clean_index")
def test_empty_index_still_loading(engine: Engine) -> None:
    clock, source = Clock(), FakeList(NEW)
    source.gate = threading.Event()
    svc = service(engine, source, clock, empty_wait_seconds=0.2)
    try:
        assert ask(engine, svc, "bit") == ([], INDEX_LOADING)
    finally:
        source.gate.set()
        settle(svc)  # done before the table is cleared for the next test


@pytest.mark.usefixtures("clean_index")
def test_no_transaction_is_open_during_the_provider_call(engine: Engine) -> None:
    clock, source = Clock(), FakeList(NEW)
    store(engine, OLD, clock.now - timedelta(hours=25))
    svc = service(engine, source, clock)
    seen: list[bool] = []
    with Session(engine) as request_db:
        source.during = lambda: seen.append(request_db.in_transaction())
        source.gate = threading.Event()
        found = svc.suggest(request_db, "bit")
        source.gate.set()
        settle(svc)
    assert [c.symbol for c in found.coins] == ["BTC"]
    # The request's own read transaction was ended before the refresh could start.
    assert seen == [False]
