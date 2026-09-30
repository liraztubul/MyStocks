from datetime import date
from decimal import Decimal

from app.domain.enums import AssetType
from app.market_data.provider import PriceKind, PriceOnDate
from app.schemas.assets import PriceOnDateRead


def price_json(price: str) -> str:
    result = PriceOnDate(
        "SHIB",
        AssetType.CRYPTO,
        Decimal(price),
        "USD",
        date(2026, 3, 1),
        date(2026, 3, 1),
        PriceKind.CLOSE,
    )
    return PriceOnDateRead.model_validate(result).model_dump(mode="json")["price"]


def test_prices_beyond_ten_places_are_rounded_to_what_transactions_accept() -> None:
    assert price_json("0.000012345678951234") == "0.0000123457"


def test_rounding_is_half_even() -> None:
    assert price_json("0.00000000005") == "0"
    assert price_json("0.00000000015") == "0.0000000002"


def test_ordinary_prices_are_unchanged_and_trimmed() -> None:
    assert price_json("211.5000") == "211.5"
    assert price_json("150") == "150"
