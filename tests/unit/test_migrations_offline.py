"""Checks on the migration chain that need no database."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def _config() -> Config:
    return Config(str(ALEMBIC_INI))


def test_migration_chain_has_a_single_head() -> None:
    # Two heads would mean two branches that `upgrade head` cannot order.
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1


def test_offline_sql_renders_the_schema(capsys: pytest.CaptureFixture[str]) -> None:
    # Offline mode (`alembic upgrade head --sql`) renders SQL without connecting.
    command.upgrade(_config(), "head", sql=True)

    sql = capsys.readouterr().out
    assert "CREATE EXTENSION IF NOT EXISTS vector" in sql
    assert "CREATE EXTENSION IF NOT EXISTS pg_trgm" in sql
    assert "CREATE TABLE documents" in sql
    assert "CONSTRAINT ck_documents_academic_year CHECK" in sql
