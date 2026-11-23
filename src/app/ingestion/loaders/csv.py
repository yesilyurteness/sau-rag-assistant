"""CSV loader (course plan, electives, staff, committees, calendar, counts).

Returns rows as raw strings for the SQL step. The rules come from measuring the 8 source
files in step 1a-3a: all use ";" and every row is as wide as its header.
"""

import csv
import io
from pathlib import Path

from app.ingestion.encoding import decode_bytes, encoding_warnings
from app.ingestion.errors import DocumentReadError, EmptyDocumentError
from app.ingestion.models import LoadedTable

DELIMITER = ";"


def _is_blank(row: list[str]) -> bool:
    """True for an empty line or a line of only delimiters and spaces."""
    return not any(cell.strip() for cell in row)


def _check_columns(columns: tuple[str, ...], path: Path) -> None:
    if len(columns) < 2:
        raise DocumentReadError(
            path, f"header has only one column; the delimiter must be {DELIMITER!r}"
        )
    empty = [str(position) for position, name in enumerate(columns, start=1) if not name.strip()]
    if empty:
        raise DocumentReadError(path, f"empty column name at position {', '.join(empty)}")
    duplicates = sorted({name for name in columns if columns.count(name) > 1})
    if duplicates:
        raise DocumentReadError(path, f"duplicate column names: {', '.join(duplicates)}")


def load_csv(path: Path) -> LoadedTable:
    """Read a ";"-separated file: the first non-blank row is the header, the rest are rows.

    Empty and separator-only rows are dropped (anywhere in the file) and counted in a warning.
    Raises `DocumentDecodeError` if no supported encoding fits, `DocumentReadError` for a bad
    header, a row of the wrong width or unparsable CSV, and `EmptyDocumentError` if there is
    no header or no data row.
    """
    text, encoding = decode_bytes(path.read_bytes(), path)
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=DELIMITER)

    columns: tuple[str, ...] | None = None
    rows: list[tuple[str, ...]] = []
    dropped = 0
    try:
        for row in reader:
            if _is_blank(row):
                dropped += 1
            elif columns is None:
                columns = tuple(row)
                _check_columns(columns, path)
            elif len(row) != len(columns):
                raise DocumentReadError(
                    path,
                    f"row at line {reader.line_num} has {len(row)} columns, "
                    f"expected {len(columns)}",
                )
            else:
                rows.append(tuple(row))
    except csv.Error as exc:
        raise DocumentReadError(path, f"could not parse CSV: {exc}") from exc

    if columns is None:
        raise EmptyDocumentError(path, "no header row")
    if not rows:
        raise EmptyDocumentError(path, "no data rows after the header")

    warnings = encoding_warnings(encoding)
    if dropped:
        warnings += (f"dropped {dropped} empty or separator-only rows",)

    return LoadedTable(
        source=path,
        columns=columns,
        rows=tuple(rows),
        encoding=encoding,
        warnings=warnings,
    )
