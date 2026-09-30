from collections.abc import Iterator

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, make_url, text
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app

TEST_DB_URL = make_url(settings.database_url).set(database=f"{settings.postgres_db}_test")


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    admin = create_engine(
        make_url(settings.database_url).set(database="postgres"), isolation_level="AUTOCOMMIT"
    )
    with admin.connect() as conn:
        exists = conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": TEST_DB_URL.database},
        )
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{TEST_DB_URL.database}"'))
    admin.dispose()

    test_engine = create_engine(TEST_DB_URL)
    Base.metadata.drop_all(test_engine)
    Base.metadata.create_all(test_engine)
    yield test_engine
    test_engine.dispose()


@pytest.fixture(autouse=True)
def fast_password_hasher(monkeypatch: pytest.MonkeyPatch) -> None:
    # Production argon2 params cost ~1s per hash under load; integration tests only need
    # a valid argon2 hash, not a slow one. Unit tests still exercise the real hasher.
    monkeypatch.setattr(
        security, "_hasher", PasswordHasher(time_cost=1, memory_cost=1024, parallelism=1)
    )


@pytest.fixture
def db_session(engine: Engine) -> Iterator[Session]:
    # Each test runs inside an outer transaction that is rolled back afterwards; app-level
    # commits become savepoints, so tests stay isolated without truncating tables.
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    app.dependency_overrides[get_db] = lambda: db_session
    # https base URL so the client's cookie jar sends back the Secure auth cookie.
    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client
    app.dependency_overrides.clear()
