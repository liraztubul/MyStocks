# Importing every model here registers it on Base.metadata, which Alembic autogenerate reads.
from app.db.models.transaction import Transaction
from app.db.models.user import User
from app.db.models.user_asset import UserAsset

__all__ = ["Transaction", "User", "UserAsset"]
