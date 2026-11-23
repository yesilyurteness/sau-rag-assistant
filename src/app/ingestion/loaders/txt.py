"""Plain-text loader (course information packages, announcements)."""

from pathlib import Path

from app.ingestion.cleaning import clean_text
from app.ingestion.encoding import decode_bytes, encoding_warnings
from app.ingestion.errors import EmptyDocumentError
from app.ingestion.models import LoadedDocument, Segment


def load_txt(path: Path) -> LoadedDocument:
    """Read a TXT file, clean it and return it as a single segment.

    Raises `DocumentDecodeError` if no supported encoding fits and `EmptyDocumentError`
    if nothing is left after cleaning.
    """
    decoded, encoding = decode_bytes(path.read_bytes(), path)
    text = clean_text(decoded)
    if not text:
        raise EmptyDocumentError(path, "no text after cleaning")

    return LoadedDocument(
        source=path,
        file_type="txt",
        segments=(Segment(text=text),),
        encoding=encoding,
        warnings=encoding_warnings(encoding),
    )
