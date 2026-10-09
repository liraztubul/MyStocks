"""CoinGecko /coins/markets paging for the coin index (shape from the 2026-10-09 probe)."""

import httpx2

from app.market_data.coingecko_provider import MARKETS_PAGE_SIZE, CoinGeckoProvider
from app.market_data.provider import CoinListing


def row(i: int, rank: object = None) -> dict[str, object]:
    return {"id": f"coin-{i}", "symbol": f"c{i}", "name": f"Coin {i}", "market_cap_rank": rank}


def test_top_coins_pages_at_250_and_normalizes() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        page = int(request.url.params["page"])
        start = (page - 1) * MARKETS_PAGE_SIZE
        rows = [row(i, i + 1) for i in range(start, start + MARKETS_PAGE_SIZE)]
        if page == 2:
            rows[0] = row(250, None)  # unranked coins appear on page 2
            rows[1] = {"id": "coin-0", "symbol": "dup", "name": "Duplicate", "market_cap_rank": 3}
            rows[2] = {"id": "bad", "symbol": None, "name": "No symbol"}
            rows[3] = row(253, True)  # a bool isn't a rank
        return httpx2.Response(200, json=rows)

    coins = CoinGeckoProvider(httpx2.Client(transport=httpx2.MockTransport(handler))).top_coins(500)
    assert [r.url.path for r in seen] == ["/api/v3/coins/markets"] * 2
    assert [r.url.params["page"] for r in seen] == ["1", "2"]
    assert all(r.url.params["per_page"] == "250" for r in seen)
    assert all(r.url.params["order"] == "market_cap_desc" for r in seen)
    assert coins[0] == CoinListing("coin-0", "C0", "Coin 0", 1)
    # 500 rows, minus a duplicate id and a row without a symbol; no third page for the two.
    assert len(coins) == 498
    by_id = {c.provider_id: c for c in coins}
    assert by_id["coin-250"].market_cap_rank is None
    assert by_id["coin-253"].market_cap_rank is None
    assert "bad" not in by_id


def test_top_coins_stops_at_a_short_page() -> None:
    calls: list[int] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(1)
        return httpx2.Response(200, json=[row(i, i + 1) for i in range(40)])

    client = httpx2.Client(transport=httpx2.MockTransport(handler))
    assert len(CoinGeckoProvider(client).top_coins(500)) == 40
    assert len(calls) == 1
