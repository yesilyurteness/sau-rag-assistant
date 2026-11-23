"""The chunks table's constraints, on the migrated test database (plain SQL, no ORM).

Every test runs in a transaction that is rolled back, so tests do not see each other's rows.
"""

from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from tests.integration.conftest import run_in_rolled_back_transaction

pytestmark = pytest.mark.integration

INSERT_DOCUMENT = text(
    "INSERT INTO documents (source_name, file_type, academic_year, status, content_hash) "
    "VALUES (:name, 'pdf', '2025-2026', 'current', :hash) RETURNING id"
)
INSERT_CHUNK = text(
    "INSERT INTO chunks (document_id, position, text, page) "
    "VALUES (:document_id, :position, :text, :page) RETURNING id, created_at"
)
COUNT_CHUNKS = text("SELECT count(*) FROM chunks WHERE document_id = :document_id")


async def _add_document(connection: AsyncConnection, name: str = "StajSSS.pdf") -> int:
    document_id: int = await connection.scalar(INSERT_DOCUMENT, {"name": name, "hash": "ab" * 32})
    return document_id


async def _add_chunk(
    connection: AsyncConnection,
    document_id: int,
    position: int = 0,
    chunk_text: str = "Staj 20 iş günüdür.",
    page: int | None = 1,
) -> Any:
    values = {"document_id": document_id, "position": position, "text": chunk_text, "page": page}
    return (await connection.execute(INSERT_CHUNK, values)).one()


def _violated_constraint(database_url: str, **chunk: Any) -> str:
    async def work(connection: AsyncConnection) -> None:
        document_id = await _add_document(connection)
        await _add_chunk(connection, document_id)  # a valid chunk at position 0
        await _add_chunk(connection, chunk.pop("document_id", document_id), **chunk)

    with pytest.raises(IntegrityError) as exc_info:
        run_in_rolled_back_transaction(database_url, work)
    name: str = exc_info.value.orig.__cause__.constraint_name  # type: ignore[union-attr]
    return name


def test_chunks_are_stored_with_and_without_a_page(migrated_database_url: str) -> None:
    async def work(connection: AsyncConnection) -> list[Any]:
        document_id = await _add_document(connection)
        pdf_chunk = await _add_chunk(connection, document_id, position=0, page=3)
        txt_chunk = await _add_chunk(connection, document_id, position=1, page=None)
        return [pdf_chunk, txt_chunk]

    pdf_chunk, txt_chunk = run_in_rolled_back_transaction(migrated_database_url, work)

    assert pdf_chunk.id < txt_chunk.id
    assert pdf_chunk.created_at.tzinfo is not None


@pytest.mark.parametrize(
    ("chunk", "constraint"),
    [
        ({"position": 1, "chunk_text": ""}, "ck_chunks_text_not_empty"),
        ({"position": 1, "page": 0}, "ck_chunks_page"),
        ({"position": -1}, "ck_chunks_position"),
        ({"position": 0}, "uq_chunks_document_id_position"),
        ({"position": 1, "document_id": 999_999_999}, "fk_chunks_document_id_documents"),
    ],
    ids=["empty-text", "page-0", "negative-position", "duplicate-position", "no-document"],
)
def test_invalid_chunk_is_rejected(
    migrated_database_url: str, chunk: dict[str, Any], constraint: str
) -> None:
    assert _violated_constraint(migrated_database_url, **chunk) == constraint


def test_same_position_is_allowed_in_another_document(migrated_database_url: str) -> None:
    async def work(connection: AsyncConnection) -> None:
        first = await _add_document(connection, "StajSSS.pdf")
        second = await _add_document(connection, "OgrenciDegisimi.pdf")
        await _add_chunk(connection, first, position=0)
        await _add_chunk(connection, second, position=0)

    run_in_rolled_back_transaction(migrated_database_url, work)


def test_deleting_a_document_deletes_its_chunks(migrated_database_url: str) -> None:
    async def work(connection: AsyncConnection) -> tuple[int, int, int]:
        document_id = await _add_document(connection, "StajSSS.pdf")
        other_id = await _add_document(connection, "OgrenciDegisimi.pdf")
        for position in range(3):
            await _add_chunk(connection, document_id, position=position)
        await _add_chunk(connection, other_id)
        before = await connection.scalar(COUNT_CHUNKS, {"document_id": document_id})

        # Plain SQL, no ORM: the cascade happens in the database.
        await connection.execute(text("DELETE FROM documents WHERE id = :id"), {"id": document_id})

        after = await connection.scalar(COUNT_CHUNKS, {"document_id": document_id})
        others = await connection.scalar(COUNT_CHUNKS, {"document_id": other_id})
        return before, after, others

    assert run_in_rolled_back_transaction(migrated_database_url, work) == (3, 0, 1)


def test_created_at_is_timestamptz(migrated_database_url: str) -> None:
    async def work(connection: AsyncConnection) -> str:
        data_type: str = await connection.scalar(
            text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name = 'chunks' AND column_name = 'created_at'"
            )
        )
        return data_type

    assert run_in_rolled_back_transaction(migrated_database_url, work) == (
        "timestamp with time zone"
    )


def test_no_separate_index_on_document_id(migrated_database_url: str) -> None:
    # The unique (document_id, position) index serves lookups by document_id.
    async def work(connection: AsyncConnection) -> set[str]:
        result = await connection.execute(
            text("SELECT indexname FROM pg_indexes WHERE tablename = 'chunks'")
        )
        return {row[0] for row in result}

    assert run_in_rolled_back_transaction(migrated_database_url, work) == {
        "pk_chunks",
        "uq_chunks_document_id_position",
    }
