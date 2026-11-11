"""Plain-text loader (course information packages, announcements)."""

from pathlib import Path

from app.ingestion.cleaning import clean_text
from app.ingestion.errors import DocumentDecodeError, EmptyDocumentError
from app.ingestion.models import LoadedDocument, Segment

# Tried in order. "utf-8-sig" is UTF-8 that also drops a leading byte order mark.
# cp1254 is the Windows Turkish code page, used by files saved with old Windows editors.
ENCODINGS: tuple[str, ...] = ("utf-8-sig", "cp1254")


def _decode(raw: bytes, source: Path) -> tuple[str, str]:
    for encoding in ENCODINGS:
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise DocumentDecodeError(source, f"not decodable as any of {', '.join(ENCODINGS)}")


def load_txt(path: Path) -> LoadedDocument:
    """Read a TXT file, clean it and return it as a single segment.

    Raises `DocumentDecodeError` if no supported encoding fits and `EmptyDocumentError`
    if nothing is left after cleaning.
    """
    raw = path.read_bytes()
    decoded, encoding = _decode(raw, path)
    text = clean_text(decoded)
    if not text:
        raise EmptyDocumentError(path, "no text after cleaning")

    warnings: tuple[str, ...] = ()
    if encoding != ENCODINGS[0]:
        warnings = (f"decoded as {encoding}, not UTF-8",)

    return LoadedDocument(
        source=path,
        file_type="txt",
        segments=(Segment(text=text),),
        encoding=encoding,
        warnings=warnings,
    )
