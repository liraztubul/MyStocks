from decimal import ROUND_HALF_EVEN, Decimal
from typing import Annotated, Any

from pydantic import AfterValidator, BeforeValidator, Field, PlainSerializer

from app.domain.precision import exact


def _reject_float(value: Any) -> Any:
    # Pydantic parses fractional JSON numbers through a Python float before building the Decimal,
    # so 1.00000000000000000001 would silently become 1. Require strings (ints are exact).
    if isinstance(value, float):
        raise ValueError('decimal values must be sent as strings, e.g. "0.1"')
    return value


def format_decimal(value: Decimal) -> str:
    # normalize() drops Numeric(28, 10)'s trailing zeros; "f" keeps it out of exponent notation.
    return format(value.normalize(), "f")


# JSON only: model_dump() must keep real Decimals, since its output feeds the ORM.
_as_string = PlainSerializer(format_decimal, return_type=str, when_used="json")


_Amount = Annotated[
    Decimal,
    BeforeValidator(_reject_float),
    Field(max_digits=28, decimal_places=10),
    _as_string,
]

PositiveAmount = Annotated[_Amount, Field(gt=0)]
NonNegativeAmount = Annotated[_Amount, Field(ge=0)]
DecimalString = Annotated[Decimal, _as_string]


def _round_half_even(places: int) -> AfterValidator:
    step = Decimal(1).scaleb(-places)

    def round_value(value: Decimal) -> Decimal:
        # Wide context: quantizing a large full-precision engine value in the default 28-digit
        # context raises instead of rounding.
        with exact():
            return value.quantize(step, rounding=ROUND_HALF_EVEN)

    return AfterValidator(round_value)


# Presentation rounding, applied only at the API boundary; the engine never rounds.
Money = Annotated[DecimalString, _round_half_even(10)]
Percent = Annotated[DecimalString, _round_half_even(4)]
