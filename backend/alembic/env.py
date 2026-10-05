from logging.config import fileConfig

from sqlalchemy import create_engine, pool, text

from alembic import context
from app.core.config import settings
from app.db import models  # noqa: F401  (registers models on Base.metadata)
from app.db.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
# Arbitrary app-wide constant identifying "MyStocks schema migration" to pg_advisory_lock.
MIGRATION_LOCK_KEY = 72_340_517


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # URL comes from app settings rather than alembic.ini so there's one source of truth
    # (and so passwords with '%' don't trip configparser interpolation).
    connectable = create_engine(settings.database_url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        # Every start runs "alembic upgrade head", and during a deploy the old and new instances
        # overlap. A session-level advisory lock makes concurrent runs queue instead of racing;
        # the second one then finds the schema already at head. (Needs a direct connection:
        # a transaction-mode pooler can't hold session locks.)
        connection.execute(text("SELECT pg_advisory_lock(:key)"), {"key": MIGRATION_LOCK_KEY})
        try:
            context.configure(connection=connection, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()
        finally:
            connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": MIGRATION_LOCK_KEY})
            connection.commit()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
