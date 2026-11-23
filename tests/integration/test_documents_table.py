"""The documents table's constraints, on the migrated test database.

Every test runs in a transaction that is rolled back, so tests do not see each other's rows.
"""

import unicodedata
from datetime import datetime
from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.storage.models import Document
from tests.integration.conftest import run_in_rolled_back_transaction

pytestmark = pytest.mark.integration

VALID: dict[str, str] = {
    "source_name": "StajSSS.pdf",
    "file_type": "pdf",
    "academic_year": "2025-2026",
    "status": "current",
    "content_hash": "0123456789abcdef" * 4,
}
INSERT = text(
    "INSERT INTO documents (source_name, file_type, academic_year, status, content_hash) "
    "VALUES (:source_name, :file_type, :academic_year, :status, :content_hash) "
    "RETURNING id, created_at, updated_at"
)
NFC_NAME = "İstatistik Olasılık 1.txt"
NFD_NAME = unicodedata.normalize("NFD", NFC_NAME)


def _insert(database_url: str, *rows: dict[str, str]) -> list[Any]:
    async def work(connection: AsyncConnection) -> list[Any]:
        return [(await connection.execute(INSERT, row)).one() for row in rows]

    return run_in_rolled_back_transaction(database_url, work)


def _violated_constraint(database_url: str, *rows: dict[str, str]) -> str:
    with pytest.raises(IntegrityError) as exc_info:
        _insert(database_url, *rows)
    name: str = exc_info.value.orig.__cause__.constraint_name  # type: ignore[union-attr]
    return name


def test_valid_row_is_stored_with_timezone_aware_timestamps(migrated_database_url: str) -> None:
    (row,) = _insert(migrated_database_url, VALID)

    assert row.id > 0
    assert isinstance(row.created_at, datetime)
    assert row.created_at.tzinfo is not None
    assert row.updated_at.tzinfo is not None


def test_timestamps_are_timestamptz_columns(migrated_database_url: str) -> None:
    async def work(connection: AsyncConnection) -> dict[str, str]:
        result = await connection.execute(
            text(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name = 'documents' AND column_name IN ('created_at', 'updated_at')"
            )
        )
        return {name: data_type for name, data_type in result}

    assert run_in_rolled_back_transaction(migrated_database_url, work) == {
        "created_at": "timestamp with time zone",
        "updated_at": "timestamp with time zone",
    }


@pytest.mark.parametrize(
    ("column", "value", "constraint"),
    [
        ("file_type", "docx", "ck_documents_file_type"),
        ("status", "archived", "ck_documents_status"),
        ("academic_year", "2025-2027", "ck_documents_academic_year"),
        ("academic_year", "2026-2025", "ck_documents_academic_year"),
        ("academic_year", "2025/2026", "ck_documents_academic_year"),
        ("academic_year", "25-26", "ck_documents_academic_year"),
        ("academic_year", "2025-2026 ", "ck_documents_academic_year"),
        ("content_hash", "0123456789ABCDEF" * 4, "ck_documents_content_hash"),
        ("content_hash", "0" * 63, "ck_documents_content_hash"),
        ("content_hash", "g" * 64, "ck_documents_content_hash"),
        ("source_name", NFD_NAME, "ck_documents_source_name_nfc"),
    ],
)
def test_invalid_value_is_rejected(
    migrated_database_url: str, column: str, value: str, constraint: str
) -> None:
    row = {**VALID, column: value}

    assert _violated_constraint(migrated_database_url, row) == constraint


def test_duplicate_source_name_is_rejected(migrated_database_url: str) -> None:
    other = {**VALID, "status": "superseded"}

    assert _violated_constraint(migrated_database_url, VALID, other) == "uq_documents_source_name"


def test_orm_stores_a_decomposed_name_as_nfc(migrated_database_url: str) -> None:
    async def work(connection: AsyncConnection) -> list[str]:
        session = AsyncSession(bind=connection)
        session.add(Document(**{**VALID, "source_name": NFD_NAME}))
        await session.flush()
        return list(await session.scalars(select(Document.source_name)))

    assert run_in_rolled_back_transaction(migrated_database_url, work) == [NFC_NAME]


def test_nfd_and_nfc_spellings_are_the_same_source(migrated_database_url: str) -> None:
    async def work(connection: AsyncConnection) -> None:
        session = AsyncSession(bind=connection)
        session.add(Document(**{**VALID, "source_name": NFC_NAME}))
        await session.flush()
        session.add(Document(**{**VALID, "source_name": NFD_NAME}))
        await session.flush()

    with pytest.raises(IntegrityError, match="uq_documents_source_name"):
        run_in_rolled_back_transaction(migrated_database_url, work)
