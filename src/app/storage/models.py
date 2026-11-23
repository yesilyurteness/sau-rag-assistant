"""Database tables (SQLAlchemy ORM). The schema itself is created by Alembic migrations.

Each table has a matching hand-written migration; an integration test runs Alembic's
autogenerate comparison to prove the two agree.
"""

import unicodedata
from datetime import datetime
from typing import Literal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    MetaData,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, validates

# Fixed constraint names, so migrations and the models name things the same way.
# column_0_N_name joins all column names, so a two-column key is named after both.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

FileType = Literal["txt", "pdf", "csv"]
Status = Literal["current", "superseded"]

FILE_TYPES: tuple[FileType, ...] = ("txt", "pdf", "csv")
STATUSES: tuple[Status, ...] = ("current", "superseded")

# "2025-2026": four digits, a dash, four digits, and the second year is the first plus one.
# CASE makes Postgres test the format before casting; AND gives no evaluation order.
ACADEMIC_YEAR_CHECK = (
    "CASE WHEN academic_year ~ '^[0-9]{4}-[0-9]{4}$' "
    "THEN substr(academic_year, 6, 4)::int = substr(academic_year, 1, 4)::int + 1 "
    "ELSE false END"
)


def _in_list(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(value) for value in values)})"


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Document(Base):
    """One source file: its registry entry for re-ingest and the ingestion report.

    TXT and PDF documents get chunks (step 1b-3); CSV documents get none, their rows go to
    SQL tables in step 2. `academic_year` and `status` live only here; chunks reach them with
    a join.
    """

    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(_in_list("file_type", FILE_TYPES), name="file_type"),
        CheckConstraint(_in_list("status", STATUSES), name="status"),
        CheckConstraint(ACADEMIC_YEAR_CHECK, name="academic_year"),
        CheckConstraint("content_hash ~ '^[0-9a-f]{64}$'", name="content_hash"),
        # Turkish file names can arrive decomposed (I + combining dot); store one form only.
        CheckConstraint("source_name = normalize(source_name, NFC)", name="source_name_nfc"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    source_name: Mapped[str] = mapped_column(Text, unique=True)
    file_type: Mapped[FileType] = mapped_column(Text)
    academic_year: Mapped[str] = mapped_column(Text)
    status: Mapped[Status] = mapped_column(Text)
    # SHA-256 of the raw file bytes, lowercase hex; unchanged hash means no re-ingest (1d).
    content_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    @validates("source_name")
    def _normalize_source_name(self, _key: str, value: str) -> str:
        return unicodedata.normalize("NFC", value)


class Chunk(Base):
    """A piece of a TXT or PDF document's text, in reading order.

    Deleting a document deletes its chunks in the database itself (ON DELETE CASCADE), so a
    re-ingest that replaces a document cannot leave orphans. Embeddings (step 3) and the
    full-text search column (step 4) are added by their own migrations.
    """

    __tablename__ = "chunks"
    __table_args__ = (
        # Also serves lookups by document_id, so no separate index on that column.
        UniqueConstraint("document_id", "position"),
        CheckConstraint("length(text) > 0", name="text_not_empty"),
        CheckConstraint("page IS NULL OR page >= 1", name="page"),
        CheckConstraint("position >= 0", name="position"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    document_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("documents.id", ondelete="CASCADE")
    )
    # 0-based order of the chunk inside its document.
    position: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    # 1-based PDF page; NULL for TXT documents.
    page: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
