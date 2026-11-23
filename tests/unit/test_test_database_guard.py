"""The guard that keeps integration tests off the development database (no database needed)."""

import pytest
from sqlalchemy import make_url

from tests.integration.conftest import TEST_DATABASE, derive_test_url


def test_only_the_database_name_changes() -> None:
    app_url = make_url("postgresql+asyncpg://rag:secret@db.example:5433/rag")

    test_url = derive_test_url(app_url)

    assert test_url.database == TEST_DATABASE
    assert (test_url.drivername, test_url.host, test_url.port) == (
        "postgresql+asyncpg",
        "db.example",
        5433,
    )
    assert (test_url.username, test_url.password) == ("rag", "secret")


def test_app_database_with_the_test_name_is_refused() -> None:
    app_url = make_url(f"postgresql+asyncpg://rag:rag@localhost:5432/{TEST_DATABASE}")

    with pytest.raises(ValueError, match="integration tests would run on it"):
        derive_test_url(app_url)
