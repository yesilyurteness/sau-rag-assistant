"""Runs the migrations against real Postgres. Start it first: `make up` (or CI services)."""

import asyncio
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings

pytestmark = pytest.mark.integration

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"
EXTENSIONS = {"vector", "pg_trgm"}


def _installed_extensions() -> set[str]:
    async def query() -> set[str]:
        engine = create_async_engine(str(get_settings().database_url))
        try:
            async with engine.connect() as connection:
                result = await connection.execute(text("SELECT extname FROM pg_extension"))
                return {row[0] for row in result}
        finally:
            await engine.dispose()

    return asyncio.run(query())


def test_upgrade_downgrade_upgrade_round_trip() -> None:
    config = Config(str(ALEMBIC_INI))

    command.upgrade(config, "head")
    assert _installed_extensions() >= EXTENSIONS

    command.downgrade(config, "base")
    assert not EXTENSIONS & _installed_extensions()

    # Leave the database migrated, as a developer would expect after the tests.
    command.upgrade(config, "head")
    assert _installed_extensions() >= EXTENSIONS
