"""Data types shared by all loaders.

The TXT and PDF loaders return a `LoadedDocument`, text to be searched, so later steps
(database, chunking) do not need to know which file type a document came from. The CSV loader
returns a `LoadedTable`: its rows go to SQL tables in step 2, so cells are kept apart instead of
being turned into text.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

FileType = Literal["txt", "pdf"]


@dataclass(frozen=True, slots=True)
class Segment:
    """A piece of a document's text plus where it came from.

    A TXT file is one segment. Loaders for other types split the document into several
    segments (for example one per PDF page) and fill in the location fields they know.
    """

    text: str
    page: int | None = None


@dataclass(frozen=True, slots=True)
class LoadedDocument:
    """The cleaned content of one source file."""

    source: Path
    file_type: FileType
    segments: tuple[Segment, ...]
    encoding: str | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def text(self) -> str:
        """All segment texts joined with a blank line."""
        return "\n\n".join(segment.text for segment in self.segments)


@dataclass(frozen=True, slots=True)
class LoadedTable:
    """The rows of one CSV file, cells kept as strings (form cleaned, content untouched).

    Every row has exactly `len(columns)` cells and column names are unique and non-empty,
    so `zip(columns, row)` is always safe. Types, empty-cell meaning and which columns to keep
    are decided by the SQL step, not here.
    """

    source: Path
    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    encoding: str
    warnings: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class TextChunk:
    """One chunk produced by a chunker, before it is stored (the DB model is separate).

    `position` is the 0-based order inside the document, `page` the 1-based page the chunk
    starts on (None for TXT), `section` the section title when the chunker knows one.
    """

    text: str
    position: int
    page: int | None = None
    section: str | None = None
