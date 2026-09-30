from decimal import Decimal
from typing import Annotated, Any

from pydantic import BeforeValidator, Field, PlainSerializer


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
