import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domain.currency import DEFAULT_BASE_CURRENCY


class User(Base):
    __tablename__ = "users"
    # Stored emails are always in normalize_email's form, so the unique index can't hold two
    # spellings of one address (the API lowercases; this makes it a database invariant too).
    __table_args__ = (CheckConstraint("email = lower(email)", name="email_lowercase"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    base_currency: Mapped[str] = mapped_column(
        String(3), default=DEFAULT_BASE_CURRENCY, server_default=DEFAULT_BASE_CURRENCY
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
