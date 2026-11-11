"""Read raw bytes into `LoadedSource` objects (TXT, PDF, CSV). No cleaning happens here."""

import csv
import io
from pathlib import Path

import pdfplumber

from app.ingestion.models import LoadedSource, Page, SourceType, Table


class LoadError(Exception):
    """A file could not be read (corrupt, wrong type, undecodable)."""


def source_type_for(path: Path) -> SourceType:
    suffix = path.suffix.lower().lstrip(".")
    try:
        return SourceType(suffix)
    except ValueError as exc:
        raise LoadError(f"unsupported file type: {path.suffix!r}") from exc


def decode_text(data: bytes) -> tuple[str, str]:
    """Decode as UTF-8 (BOM tolerated); fall back to Windows-1254, the legacy Turkish encoding."""
    try:
        return data.decode("utf-8-sig"), "utf-8"
    except UnicodeDecodeError:
        try:
            return data.decode("cp1254"), "cp1254"
        except UnicodeDecodeError as exc:
            raise LoadError("text is neither UTF-8 nor Windows-1254") from exc


def load_txt(data: bytes) -> LoadedSource:
    text, encoding = decode_text(data)
    return LoadedSource(source_type=SourceType.TXT, text=text, encoding=encoding)


def load_pdf(data: bytes) -> LoadedSource:
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            pages = [
                Page(number=i, text=page.extract_text() or "", image_count=len(page.images))
                for i, page in enumerate(pdf.pages, start=1)
            ]
    except Exception as exc:
        raise LoadError(f"could not read PDF: {exc}") from exc
    return LoadedSource(
        source_type=SourceType.PDF, text="\n".join(p.text for p in pages), pages=pages
    )


def _detect_delimiter(header_line: str) -> str:
    counts = {d: header_line.count(d) for d in (";", ",", "\t")}
    best = max(counts, key=lambda d: counts[d])
    return best if counts[best] > 0 else ";"


def load_csv(data: bytes) -> LoadedSource:
    text, encoding = decode_text(data)
    lines = text.splitlines()
    if not lines:
        return LoadedSource(source_type=SourceType.CSV, table=Table([], []), encoding=encoding)
    delimiter = _detect_delimiter(lines[0])
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = [[cell.strip() for cell in row] for row in reader]
    header, body = rows[0], rows[1:]
    body = [row for row in body if any(cell for cell in row)]  # drop blank trailing rows
    return LoadedSource(
        source_type=SourceType.CSV, table=Table(header=header, rows=body), encoding=encoding
    )


def load_bytes(path: Path, data: bytes) -> LoadedSource:
    kind = source_type_for(path)
    if kind is SourceType.TXT:
        return load_txt(data)
    if kind is SourceType.PDF:
        return load_pdf(data)
    return load_csv(data)
