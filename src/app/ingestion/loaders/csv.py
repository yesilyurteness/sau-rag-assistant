"""CSV loader (course plan, electives, staff, committees, calendar, counts).

Returns rows as strings for the SQL step. The rules come from measuring the 8 source files in
step 1a-3a: all use ";" and every row is as wide as its header. Every column name and cell is
passed through `clean_text`, which fixes form only (for example the 31 trailing spaces found
in 1a-3a); types and the meaning of empty cells are left to the SQL step.
"""

import csv
import io
from pathlib import Path

from app.ingestion.cleaning import clean_text
from app.ingestion.encoding import decode_bytes, encoding_warnings
from app.ingestion.errors import DocumentReadError, EmptyDocumentError
from app.ingestion.models import LoadedTable

DELIMITER = ";"


def _clean_row(row: list[str]) -> tuple[tuple[str, ...], int]:
    """Clean every cell; return the cleaned cells and how many of them changed."""
    cells = tuple(clean_text(cell) for cell in row)
    changed = sum(1 for raw, cleaned in zip(row, cells, strict=True) if raw != cleaned)
    return cells, changed


def _check_columns(columns: tuple[str, ...], path: Path) -> None:
    """Checks run on cleaned names, so "Kodu" and "Kodu " count as the same name."""
    if len(columns) < 2:
        raise DocumentReadError(
            path, f"header has only one column; the delimiter must be {DELIMITER!r}"
        )
    empty = [str(position) for position, name in enumerate(columns, start=1) if not name]
    if empty:
        raise DocumentReadError(path, f"empty column name at position {', '.join(empty)}")
    duplicates = sorted({name for name in columns if columns.count(name) > 1})
    if duplicates:
        raise DocumentReadError(path, f"duplicate column names: {', '.join(duplicates)}")


def load_csv(path: Path) -> LoadedTable:
    """Read a ";"-separated file: the first non-blank row is the header, the rest are rows.

    Column names and cells are cleaned with `clean_text`; the number of changed ones (in the
    header and the kept rows) is reported in a warning. Rows whose cells are all empty after
    cleaning are dropped (anywhere in the file) and counted in a warning.
    Raises `DocumentDecodeError` if no supported encoding fits, `DocumentReadError` for a bad
    header, a row of the wrong width or unparsable CSV, and `EmptyDocumentError` if there is
    no header or no data row.
    """
    text, encoding = decode_bytes(path.read_bytes(), path)
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=DELIMITER)

    columns: tuple[str, ...] | None = None
    rows: list[tuple[str, ...]] = []
    dropped = 0
    cleaned = 0
    try:
        for row in reader:
            cells, changed = _clean_row(row)
            if not any(cells):
                dropped += 1
            elif columns is None:
                _check_columns(cells, path)
                columns = cells
                cleaned += changed
            elif len(cells) != len(columns):
                raise DocumentReadError(
                    path,
                    f"row at line {reader.line_num} has {len(cells)} columns, "
                    f"expected {len(columns)}",
                )
            else:
                rows.append(cells)
                cleaned += changed
    except csv.Error as exc:
        raise DocumentReadError(path, f"could not parse CSV: {exc}") from exc

    if columns is None:
        raise EmptyDocumentError(path, "no header row")
    if not rows:
        raise EmptyDocumentError(path, "no data rows after the header")

    warnings = encoding_warnings(encoding)
    if cleaned:
        warnings += (f"cleaned {cleaned} cells",)
    if dropped:
        warnings += (f"dropped {dropped} empty or separator-only rows",)

    return LoadedTable(
        source=path,
        columns=columns,
        rows=tuple(rows),
        encoding=encoding,
        warnings=warnings,
    )
