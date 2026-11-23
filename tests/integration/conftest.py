"""Integration tests run against a separate test database, never the development one.

The test database URL is the app's `database_url` with only the database name replaced by
`TEST_DATABASE`. It is created on first use. Migration tests downgrade to base, which would
delete ingested data if they ran on the development database, so the session stops if both
names are the same.
"""

import asyncio
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import make_url, text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings

TEST_DATABASE = "sau_rag_test"
MAINTENANCE_DATABASE = "postgres"
ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def derive_test_url(app_url: URL) -> URL:
    """The app URL with the test database name; refuses to return the app's own database."""
    if app_url.database == TEST_DATABASE:
        raise ValueError(
            f"the app database is already named {TEST_DATABASE!r}; integration tests "
            "would run on it. Point DATABASE_URL at the development database instead."
        )
    return app_url.set(database=TEST_DATABASE)


async def _create_database_if_missing(app_url: URL) -> None:
    maintenance = app_url.set(database=MAINTENANCE_DATABASE)
    engine = create_async_engine(maintenance, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as connection:
            exists = await connection.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": TEST_DATABASE},
            )
            if not exists:
                # The name is a constant, not user input; CREATE DATABASE takes no parameters.
                await connection.execute(text(f'CREATE DATABASE "{TEST_DATABASE}"'))
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
def test_database_url() -> str:
    """URL of the (created if missing) test database, password included, for engines."""
    app_url = make_url(str(get_settings().database_url))
    try:
        test_url = derive_test_url(app_url)
    except ValueError as exc:
        pytest.exit(f"unsafe test database: {exc}", returncode=1)
    asyncio.run(_create_database_if_missing(app_url))
    return test_url.render_as_string(hide_password=False)


def alembic_config(database_url: str) -> Config:
    """Alembic config that targets `database_url` instead of the app database."""
    config = Config(str(ALEMBIC_INI))
    config.attributes["database_url"] = database_url
    return config


@pytest.fixture(scope="session")
def migrated_database_url(test_database_url: str) -> str:
    """The test database upgraded to the latest migration."""
    command.upgrade(alembic_config(test_database_url), "head")
    return test_database_url
