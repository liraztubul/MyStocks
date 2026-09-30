from enum import Enum


class AssetType(str, Enum):
    STOCK = "stock"
    CRYPTO = "crypto"


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"
