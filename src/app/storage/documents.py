"""Postgres implementation of the ingestion `DocumentStore` protocol."""

from sqlalchemy import ColumnElement, delete, func, select, true, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.ingestion.checks import content_hash
from app.ingestion.chunking import estimate_tokens
from app.ingestion.models import PIPELINE_VERSION, ProcessedDocument
from app.storage.models import ChunkRow, DocumentRow


class SqlDocumentStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def get_fingerprint(self, source_name: str) -> str | None:
        async with self._sessions() as session:
            row = await session.scalar(
                select(DocumentRow.fingerprint).where(
                    DocumentRow.source_name == source_name, DocumentRow.is_active.is_(True)
                )
            )
            return row

    async def upsert(self, document: ProcessedDocument, fingerprint: str) -> None:
        entry = document.entry
        values = {
            "title": document.title,
            "source_type": document.source_type.value,
            "source_kind": entry.kind.value,
            "target": document.target.value,
            "academic_year": document.academic_year,
            "valid_from": entry.valid_from,
            "valid_until": entry.valid_until,
            "status": entry.status.value,
            "access": entry.access,
            "content_hash": document.content_hash,
            "fingerprint": fingerprint,
            "pipeline_version": PIPELINE_VERSION,
            "page_count": document.page_count,
            "char_count": document.clean_chars,
            "is_active": True,
            "notes": entry.notes,
            "metadata_": document.metadata,
        }
        async with self._sessions.begin() as session:
            row = await session.scalar(
                select(DocumentRow).where(DocumentRow.source_name == entry.name)
            )
            if row is None:
                row = DocumentRow(source_name=entry.name, **values)
                session.add(row)
                await session.flush()
            else:
                for key, value in values.items():
                    setattr(row, key, value)
                row.updated_at = func.now()
                await session.execute(delete(ChunkRow).where(ChunkRow.document_id == row.id))
            session.add_all(
                ChunkRow(
                    document_id=row.id,
                    ordinal=c.ordinal,
                    section=c.section,
                    header=c.header,
                    content=c.content,
                    content_hash=content_hash(c.embedding_text),
                    char_count=c.char_count,
                    token_estimate=estimate_tokens(c.embedding_text),
                    page_start=c.page_start,
                    page_end=c.page_end,
                    metadata_=c.metadata,
                )
                for c in document.chunks
            )

    async def deactivate_missing(self, keep: set[str], *, prune: bool) -> list[str]:
        async with self._sessions.begin() as session:
            conditions: list[ColumnElement[bool]] = [true()]
            if keep:
                conditions.append(DocumentRow.source_name.not_in(keep))
            if not prune:
                conditions.append(DocumentRow.is_active.is_(True))
            names = list(await session.scalars(select(DocumentRow.source_name).where(*conditions)))
            if not names:
                return []
            condition = DocumentRow.source_name.in_(names)
            if prune:
                await session.execute(delete(DocumentRow).where(condition))
            else:
                await session.execute(
                    update(DocumentRow)
                    .where(condition)
                    .values(is_active=False, updated_at=func.now())
                )
            return sorted(names)
