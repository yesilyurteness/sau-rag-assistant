"""Runs the migrations against the test database. Start Postgres first: `make up` (or CI)."""

import asyncio

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.integration.conftest import alembic_config

pytestmark = pytest.mark.integration

EXTENSIONS = {"vector", "pg_trgm"}


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


def test_models_match_the_migrations(migrated_database_url: str) -> None:
    # `alembic check` runs the autogenerate comparison and raises if the ORM models
    # (app.storage.models) describe anything the hand-written migrations did not create.
    command.check(alembic_config(migrated_database_url))
