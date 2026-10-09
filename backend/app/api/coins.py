"""Coin search-as-you-type from the local coin index: no provider call per keystroke.

Crypto only. A query shorter than 2 characters returns no results. Reaches the index only
through app.market_data.access.CoinIndexDep.
"""

from typing import Annotated

from fastapi import APIRouter, Query

from app.db.session import DbSession
from app.market_data.access import CoinIndexDep
from app.schemas.coins import CoinSuggestion, CoinSuggestResponse

router = APIRouter(prefix="/coins", tags=["coins"])


@router.get("/suggest", response_model=CoinSuggestResponse)
def suggest_coins(
    index: CoinIndexDep, db: DbSession, q: Annotated[str, Query(max_length=200)] = ""
) -> CoinSuggestResponse:
    found = index.suggest(db, q)
    return CoinSuggestResponse(
        results=[CoinSuggestion.model_validate(c) for c in found.coins], reason=found.reason
    )
