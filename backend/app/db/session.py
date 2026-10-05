from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

# Neon suspends compute after 5 idle minutes and drops every connection with it. Recycling
# before that point and pinging on checkout means a pooled connection is never handed out dead;
# the first request after a suspend just pays Neon's wake-up time.
POOL_RECYCLE_SECONDS = 240
POOL_SIZE = 3
MAX_OVERFLOW = 2
CONNECT_TIMEOUT_SECONDS = 15


def create_db_engine(url: str) -> Engine:
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_recycle=POOL_RECYCLE_SECONDS,
        pool_size=POOL_SIZE,
        max_overflow=MAX_OVERFLOW,
        connect_args={"connect_timeout": CONNECT_TIMEOUT_SECONDS},
    )


engine = create_db_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


DbSession = Annotated[Session, Depends(get_db)]
