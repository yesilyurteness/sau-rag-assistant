"""Data types shared by all loaders.

Every loader (TXT, PDF, CSV) returns a `LoadedDocument`, so later steps (database, chunking)
do not need to know which file type a document came from.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

FileType = Literal["txt", "pdf", "csv"]


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
