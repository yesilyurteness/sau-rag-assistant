"""Errors raised while loading source documents.

The ingestion command (step 1d) catches `IngestionError`, records the file in the
ingestion report and continues with the next file.
"""

from pathlib import Path


class IngestionError(Exception):
    """Base class for problems with a single source file."""

    def __init__(self, source: Path, reason: str) -> None:
        self.source = source
        self.reason = reason
        super().__init__(f"{source.name}: {reason}")


class EmptyDocumentError(IngestionError):
    """The file has no text left after cleaning."""


class DocumentDecodeError(IngestionError):
    """The file bytes could not be decoded with any supported encoding."""
