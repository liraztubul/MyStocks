"""Which coin a crypto ticker means, when the user didn't pick one.

Tickers aren't unique on CoinGecko: "PEPE" is several coins, and "TON" today matches only a
rank-805 token because Toncoin trades as "GRAM". So a coin is chosen automatically only when
one exact-ticker match is both well known and far ahead of the others; anything less clear is
handed back to the user as a choice. Never a silent guess: an automatic pick is always shown
as such ("Showing X, not this one?").
"""

from dataclasses import dataclass

from app.market_data.provider import AssetMatch

# Auto-pick only coins at least this prominent by market cap (1 = largest).
AUTOPICK_MAX_RANK = 100
# ...and only if every other coin with the same ticker is unranked or ranked at least this many
# times further down (rank 5 vs 50 qualifies; rank 5 vs 49 does not).
DOMINANCE_FACTOR = 10
# How many search results (beyond the exact-ticker matches) to offer when asking.
MAX_CANDIDATES = 8


@dataclass(frozen=True)
class CoinPick:
    coin_id: str
    name: str


@dataclass(frozen=True)
class CoinChoiceNeeded:
    symbol: str
    candidates: tuple[AssetMatch, ...]


def _rank(match: AssetMatch) -> int | None:
    """The match's rank, None if unranked; raises if the provider sent something unexpected."""
    rank = match.market_cap_rank
    if rank is None:
        return None
    # bool is an int subclass; a True/False rank would be a provider bug, not a rank.
    if isinstance(rank, bool) or not isinstance(rank, int) or rank < 1:
        raise ValueError(rank)
    return rank


def resolve_coin(symbol: str, matches: list[AssetMatch]) -> CoinPick | CoinChoiceNeeded | None:
    """None when no coin has this ticker at all."""
    ticker = symbol.strip().upper()
    exact = [m for m in matches if m.symbol.upper() == ticker]
    if not exact:
        return None
    others = [m for m in matches if m not in exact]
    ask = CoinChoiceNeeded(ticker, tuple(exact + others)[: len(exact) + MAX_CANDIDATES])

    try:
        ranks = [_rank(m) for m in exact]
    except ValueError:
        # market_cap_rank isn't what we assume (a number or null): don't build a pick on it.
        return ask
    ranked = sorted((rank, i) for i, rank in enumerate(ranks) if rank is not None)
    if not ranked:
        return ask
    top_rank, top_index = ranked[0]
    if top_rank > AUTOPICK_MAX_RANK:
        return ask
    if any(rank < top_rank * DOMINANCE_FACTOR for rank, _ in ranked[1:]):
        return ask
    top = exact[top_index]
    return CoinPick(top.provider_id, top.name)
