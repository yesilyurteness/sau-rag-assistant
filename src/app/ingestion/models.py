"""Plain data types shared by the ingestion modules (no I/O, no framework imports)."""

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Any

PIPELINE_VERSION = "1"
"""Bump when cleaning or chunking changes in a way that should re-chunk unchanged files."""


class SourceType(StrEnum):
    TXT = "txt"
    PDF = "pdf"
    CSV = "csv"


class SourceKind(StrEnum):
    COURSE_PACKAGE = "course_package"  # one course information package (EBS print)
    FAQ = "faq"  # question and answer pairs
    DECISIONS = "decisions"  # numbered committee decisions ("1.", "2.", ...)
    PROCEDURE = "procedure"  # numbered how-to steps ("1-", "ADIM 3", "8.1.2-")
    NARRATIVE = "narrative"  # headings and paragraphs
    ANNOUNCEMENT = "announcement"  # announcement text with date tables
    SLIDES = "slides"  # one slide per PDF page
    TABULAR = "tabular"  # CSV, goes to SQL tables in step 2


class DocStatus(StrEnum):
    CURRENT = "current"
    SUPERSEDED = "superseded"


class Target(StrEnum):
    VECTOR = "vector"
    SQL = "sql"


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class Finding:
    severity: Severity
    code: str
    message: str


@dataclass(frozen=True)
class ManifestEntry:
    """What the project owner declared about one source file."""

    name: str
    kind: SourceKind
    title: str | None = None
    academic_year: str | None = None
    status: DocStatus = DocStatus.CURRENT
    access: str = "public"
    valid_from: date | None = None
    valid_until: date | None = None
    skip_reason: str | None = None
    notes: str | None = None

    @property
    def skipped(self) -> bool:
        return self.skip_reason is not None


@dataclass(frozen=True)
class Page:
    """Text of one PDF page, plus facts the quality checks need."""

    number: int  # 1-based
    text: str
    image_count: int = 0


@dataclass(frozen=True)
class Table:
    header: list[str]
    rows: list[list[str]]


@dataclass(frozen=True)
class LoadedSource:
    """Raw content of a file as read from disk, before cleaning."""

    source_type: SourceType
    text: str = ""  # TXT: whole file; PDF: pages joined; CSV: empty
    pages: list[Page] = field(default_factory=list)  # PDF only
    table: Table | None = None  # CSV only
    encoding: str = "utf-8"


@dataclass(frozen=True)
class Chunk:
    ordinal: int
    section: str
    header: str
    content: str
    page_start: int | None = None
    page_end: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def char_count(self) -> int:
        return len(self.content)

    @property
    def embedding_text(self) -> str:
        """Header plus body: what gets embedded and shown to the LLM."""
        return f"{self.header}\n{self.content}"


@dataclass(frozen=True)
class ProcessedDocument:
    """A source file after loading, cleaning and chunking, ready to store."""

    entry: ManifestEntry
    source_type: SourceType
    target: Target
    title: str
    academic_year: str | None
    content_hash: str
    raw_chars: int
    clean_chars: int
    duplicate_chars_removed: int
    page_count: int | None
    chunks: list[Chunk]
    metadata: dict[str, Any]
    findings: list[Finding]
