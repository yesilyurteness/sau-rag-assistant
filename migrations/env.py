"""Alembic environment: runs migrations with the app's async engine.

The URL comes from `app.core.config.Settings`, never from alembic.ini or os.environ, so the
app and the migrations always talk to the same database. Tests point migrations at the test
database by passing `Config.attributes["database_url"]`.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.storage.models import Base

config = context.config
if config.config_file_name is not None:
    # Keep the app's (structlog) loggers working when migrations run inside tests.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Used only to compare models with the hand-written migrations (`alembic check`).
target_metadata = Base.metadata


def _database_url() -> str:
    override = config.attributes.get("database_url")
    if isinstance(override, str):
        return override
    return str(get_settings().database_url)


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it (`alembic upgrade head --sql`)."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(_database_url(), poolclass=pool.NullPool)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_run_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
