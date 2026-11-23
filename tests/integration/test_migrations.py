"""Runs the migrations against the test database. Start Postgres first: `make up` (or CI)."""

import asyncio
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"
EXTENSIONS = {"vector", "pg_trgm"}


def alembic_config(database_url: str) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.attributes["database_url"] = database_url
    return config


def _installed_extensions(database_url: str) -> set[str]:
    async def query() -> set[str]:
        engine = create_async_engine(database_url)
        try:
            async with engine.connect() as connection:
                result = await connection.execute(text("SELECT extname FROM pg_extension"))
                return {row[0] for row in result}
        finally:
            await engine.dispose()

    return asyncio.run(query())


def test_upgrade_downgrade_upgrade_round_trip(test_database_url: str) -> None:
    config = alembic_config(test_database_url)

    command.upgrade(config, "head")
    assert _installed_extensions(test_database_url) >= EXTENSIONS

    command.downgrade(config, "base")
    assert not EXTENSIONS & _installed_extensions(test_database_url)

    # Leave the test database migrated for the tests that need tables.
    command.upgrade(config, "head")
    assert _installed_extensions(test_database_url) >= EXTENSIONS
