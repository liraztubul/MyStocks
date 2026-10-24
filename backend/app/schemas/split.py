import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, model_validator

from app.domain.precision import exact
from app.schemas.decimal import DecimalString, PositiveAmount
from app.schemas.transaction import NormalizedSymbol

# A typo guard: real splits stay far inside 1:10000 .. 10000:1.
MAX_RATIO = Decimal(10000)


def check_ratio(numerator: Decimal, denominator: Decimal) -> None:
    if numerator == denominator:
        raise ValueError("A split ratio can't be 1:1.")
    with exact():
        ratio = numerator / denominator
        if ratio > MAX_RATIO or ratio * MAX_RATIO < 1:
            raise ValueError("A split ratio must be between 1:10000 and 10000:1.")


class SplitCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: NormalizedSymbol
    effective_date: date
    numerator: PositiveAmount
    denominator: PositiveAmount

    @model_validator(mode="after")
    def _ratio(self) -> "SplitCreate":
        check_ratio(self.numerator, self.denominator)
        return self


class SplitUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    effective_date: date | None = None
    numerator: PositiveAmount | None = None
    denominator: PositiveAmount | None = None

    @model_validator(mode="after")
    def _no_explicit_nulls(self) -> "SplitUpdate":
        nulls = [name for name in self.model_fields_set if getattr(self, name) is None]
        if nulls:
            raise ValueError(f"fields cannot be null: {', '.join(sorted(nulls))}")
        return self


class SplitRead(BaseModel):
    id: uuid.UUID
    symbol: str
    effective_date: date
    numerator: DecimalString
    denominator: DecimalString
    # What the split did to the holding: shares at the start of its date, and after it.
    shares_before: DecimalString
    shares_after: DecimalString
    created_at: datetime
