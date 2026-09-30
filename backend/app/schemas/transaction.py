import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.domain.enums import AssetType, Side
from app.schemas.decimal import DecimalString, NonNegativeAmount, PositiveAmount


def _normalize_symbol(symbol: str) -> str:
    symbol = symbol.strip().upper()
    if not symbol:
        raise ValueError("symbol must not be blank")
    return symbol


NormalizedSymbol = Annotated[str, Field(max_length=32), AfterValidator(_normalize_symbol)]


class TransactionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: NormalizedSymbol
    asset_type: AssetType
    side: Side
    quantity: PositiveAmount
    price: PositiveAmount
    fee: NonNegativeAmount = Decimal(0)
    # USD-only until multi-currency lands; the column exists so that won't need a migration.
    currency: Literal["USD"] = "USD"
    executed_at: AwareDatetime


class TransactionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: NormalizedSymbol | None = None
    asset_type: AssetType | None = None
    side: Side | None = None
    quantity: PositiveAmount | None = None
    price: PositiveAmount | None = None
    fee: NonNegativeAmount | None = None
    currency: Literal["USD"] | None = None
    executed_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def _no_explicit_nulls(self) -> "TransactionUpdate":
        # Omitting a field means "leave it"; sending null would try to blank a required column.
        nulls = [name for name in self.model_fields_set if getattr(self, name) is None]
        if nulls:
            raise ValueError(f"fields cannot be null: {', '.join(sorted(nulls))}")
        return self


class TransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    symbol: str
    asset_type: AssetType
    side: Side
    quantity: DecimalString
    price: DecimalString
    fee: DecimalString
    currency: str
    executed_at: datetime
    created_at: datetime
