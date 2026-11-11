"""SqlDocumentStore and migration 0001 against a real, throw-away Postgres database."""

import asyncio
import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import replace

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import Settings
from app.ingestion.models import (
    Chunk,
    DocStatus,
    ManifestEntry,
    ProcessedDocument,
    SourceKind,
    SourceType,
    Target,
)
from app.storage.documents import SqlDocumentStore
from app.storage.models import ChunkRow, DocumentRow

pytestmark = pytest.mark.integration


async def _admin(url: str, sql: str) -> None:
    engine = create_async_engine(url, isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        await conn.execute(text(sql))
    await engine.dispose()


@pytest.fixture(scope="module")
def database_url() -> Iterator[str]:
    base = make_url(str(Settings().database_url))
    name = f"rag_test_{uuid.uuid4().hex[:8]}"
    admin = base.set(database="postgres").render_as_string(hide_password=False)
    asyncio.run(_admin(admin, f'CREATE DATABASE "{name}"'))
    url = base.set(database=name).render_as_string(hide_password=False)
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    config.attributes["configure_logger"] = False
    command.upgrade(config, "head")
    yield url
    asyncio.run(_admin(admin, f'DROP DATABASE "{name}" WITH (FORCE)'))


@pytest.fixture
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(database_url)
    async with eng.begin() as conn:
        await conn.execute(text("TRUNCATE documents, chunks RESTART IDENTITY CASCADE"))
    yield eng
    await eng.dispose()


def _doc(name: str = "a.pdf", chunks: int = 2, content_hash: str = "h1") -> ProcessedDocument:
    entry = ManifestEntry(
        name=name, kind=SourceKind.FAQ, academic_year="2025-2026", status=DocStatus.CURRENT
    )
    return ProcessedDocument(
        entry=entry,
        source_type=SourceType.PDF,
        target=Target.VECTOR,
        title="Örnek",
        academic_year="2025-2026",
        content_hash=content_hash,
        raw_chars=100,
        clean_chars=90,
        duplicate_chars_removed=0,
        page_count=1,
        chunks=[Chunk(i, f"s{i}", f"Örnek | s{i}", f"içerik {i}", 1, 1) for i in range(chunks)],
        metadata={"k": "v"},
        findings=[],
    )


async def _count(engine: AsyncEngine, model: type[DocumentRow] | type[ChunkRow]) -> int:
    async with engine.connect() as conn:
        return int(await conn.scalar(select(func.count()).select_from(model)) or 0)


async def test_upsert_insert_then_replace_chunks(engine: AsyncEngine) -> None:
    store = SqlDocumentStore(engine)
    assert await store.get_fingerprint("a.pdf") is None

    await store.upsert(_doc(chunks=3), "fp1")
    assert await store.get_fingerprint("a.pdf") == "fp1"
    assert await _count(engine, ChunkRow) == 3

    await store.upsert(_doc(chunks=1, content_hash="h2"), "fp2")
    assert await store.get_fingerprint("a.pdf") == "fp2"
    assert await _count(engine, DocumentRow) == 1
    assert await _count(engine, ChunkRow) == 1


async def test_deactivate_then_reactivate_and_prune(engine: AsyncEngine) -> None:
    store = SqlDocumentStore(engine)
    await store.upsert(_doc("a.pdf"), "fp-a")
    await store.upsert(_doc("b.pdf"), "fp-b")

    assert await store.deactivate_missing({"a.pdf"}, prune=False) == ["b.pdf"]
    assert await store.get_fingerprint("b.pdf") is None  # inactive documents are not "unchanged"
    assert await store.deactivate_missing({"a.pdf"}, prune=False) == []

    await store.upsert(_doc("b.pdf"), "fp-b")
    assert await store.get_fingerprint("b.pdf") == "fp-b"

    assert await store.deactivate_missing({"a.pdf"}, prune=True) == ["b.pdf"]
    assert await _count(engine, DocumentRow) == 1
    assert await _count(engine, ChunkRow) == 2  # b's chunks were deleted by the cascade


async def test_constraints_reject_bad_status(engine: AsyncEngine) -> None:
    store = SqlDocumentStore(engine)
    bad = _doc()
    bad = replace(bad, entry=replace(bad.entry, name="c.pdf"), academic_year="2025/26")

    with pytest.raises(Exception, match="ck_documents_academic_year"):
        await store.upsert(bad, "fp")
