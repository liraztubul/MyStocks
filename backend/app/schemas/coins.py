from typing import Literal

from pydantic import BaseModel, ConfigDict


class CoinSuggestion(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    # The CoinGecko coin id: send it as `id` when adding, so no lookup is needed.
    provider_id: str
    symbol: str
    name: str
    market_cap_rank: int | None


class CoinSuggestResponse(BaseModel):
    results: list[CoinSuggestion]
    # Set when the index itself can't answer (empty, or still loading for the first time); the
    # client then falls back to exact tickers. Null when the index answered, even with no match.
    reason: Literal["coin_index_loading", "coin_index_unavailable"] | None = None
