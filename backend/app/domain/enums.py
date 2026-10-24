from enum import StrEnum


class AssetType(StrEnum):
    STOCK = "stock"
    CRYPTO = "crypto"


class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"
