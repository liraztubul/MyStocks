import json
from pathlib import Path

import pytest

from app.domain.enums import AssetType
from app.market_data.coin_resolution import (
    AUTOPICK_MAX_RANK,
    DOMINANCE_FACTOR,
    CoinChoiceNeeded,
    CoinPick,
    resolve_coin,
)
from app.market_data.provider import AssetMatch

FIXTURES = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "coingecko_search_2026-10-06.json").read_text(
        encoding="utf-8"
    )
)


def recorded(query: str) -> list[AssetMatch]:
    return [
        AssetMatch(c["symbol"], c["name"], AssetType.CRYPTO, c["id"], c["market_cap_rank"])
        for c in FIXTURES[query]
    ]


def coin(coin_id: str, rank: object, symbol: str = "XYZ") -> AssetMatch:
    return AssetMatch(symbol, coin_id.title(), AssetType.CRYPTO, coin_id, rank)


# --- Recorded CoinGecko answers ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("query", "coin_id"),
    [("btc", "bitcoin"), ("eth", "ethereum"), ("uni", "uniswap"), ("pepe", "pepe")],
)
def test_recorded_clear_winners_are_picked(query: str, coin_id: str) -> None:
    result = resolve_coin(query, recorded(query))
    assert isinstance(result, CoinPick)
    assert result.coin_id == coin_id


def test_recorded_ton_asks_instead_of_charting_tokamak() -> None:
    # The only exact "TON" is Tokamak Network at rank 805; Toncoin trades as GRAM. Picking the
    # single match would silently chart the wrong coin.
    result = resolve_coin("TON", recorded("ton"))
    assert isinstance(result, CoinChoiceNeeded)
    ids = [c.provider_id for c in result.candidates]
    assert ids[0] == "tokamak-network"  # exact matches first
    assert "the-open-network" in ids  # the renamed coin is still offered


def test_unknown_ticker() -> None:
    assert resolve_coin("NOPE", recorded("btc")) is None


# --- AUTOPICK_MAX_RANK boundary ------------------------------------------------------------------


def test_rank_at_the_limit_is_picked() -> None:
    assert isinstance(resolve_coin("XYZ", [coin("a", AUTOPICK_MAX_RANK)]), CoinPick)


def test_rank_just_past_the_limit_asks() -> None:
    assert isinstance(resolve_coin("XYZ", [coin("a", AUTOPICK_MAX_RANK + 1)]), CoinChoiceNeeded)


# --- DOMINANCE_FACTOR boundary -------------------------------------------------------------------


def test_rival_exactly_factor_times_worse_still_lets_the_top_win() -> None:
    matches = [coin("top", 5), coin("rival", 5 * DOMINANCE_FACTOR)]
    result = resolve_coin("XYZ", matches)
    assert isinstance(result, CoinPick) and result.coin_id == "top"


def test_rival_just_inside_the_factor_asks() -> None:
    matches = [coin("top", 5), coin("rival", 5 * DOMINANCE_FACTOR - 1)]
    assert isinstance(resolve_coin("XYZ", matches), CoinChoiceNeeded)


def test_unranked_rivals_do_not_block_a_pick() -> None:
    result = resolve_coin("XYZ", [coin("rival", None), coin("top", 7)])
    assert isinstance(result, CoinPick) and result.coin_id == "top"


def test_tied_ranks_ask() -> None:
    assert isinstance(resolve_coin("XYZ", [coin("a", 3), coin("b", 3)]), CoinChoiceNeeded)


def test_only_unranked_matches_ask() -> None:
    assert isinstance(resolve_coin("XYZ", [coin("a", None)]), CoinChoiceNeeded)


# --- market_cap_rank not what we assume -> ask, never pick on it -------------------------------


@pytest.mark.parametrize("bad_rank", ["1", 1.0, True, 0, -3, {"rank": 1}])
def test_unexpected_rank_values_ask(bad_rank: object) -> None:
    result = resolve_coin("XYZ", [coin("a", bad_rank), coin("b", None)])
    assert isinstance(result, CoinChoiceNeeded)


def test_ticker_match_ignores_case_and_spaces() -> None:
    result = resolve_coin("  btc ", recorded("btc"))
    assert isinstance(result, CoinPick) and result.coin_id == "bitcoin"
