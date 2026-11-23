"""Chunker for EBS course packages, run on the text `app.ingestion.ebs.clean_ebs` returns.

Measured in step 1c-4b on the 82 cleaned packages: every package has the same eight
sections in the same order. The short identity fields ("künye": title, course name, code,
language, coordinator ...) form one chunk; every main section forms one chunk whose
`section` is the section name. A section longer than `size` is split only where a line
starts, and in the two tables (learning outcomes, weekly topics) only where a table row
starts, because one learning outcome spans several lines. A continuation chunk of a table
starts with that table's header row, so its columns stay readable; such a chunk is
therefore not one contiguous slice of the source. The workload table ("AKTS - İş Yükü") is
never split: it is where v1 confused the 6,08 workload with the 5 ECTS.
"""

import re
from dataclasses import dataclass
from itertools import pairwise

from app.ingestion.models import TextChunk

DEFAULT_SIZE = 1500

IDENTITY = "Künye"
LEARNING_OUTCOMES = "Ders Öğrenme Çıktıları"
WEEKLY_TOPICS = "Haftalık Konular"
WORKLOAD = "AKTS - İş Yükü"
# (line prefix, section), checked in this order. Lines before the first match (the title
# and the identity fields) belong to the identity chunk.
SECTION_STARTS: tuple[tuple[str, str], ...] = (
    ("Dersin Amacı", "Dersin Amacı"),
    ("Dersin İçeriği", "Dersin İçeriği"),
    ("# | Ders Öğrenme Çıktıları", LEARNING_OUTCOMES),
    ("Hafta | Ders Konuları", WEEKLY_TOPICS),
    ("Kaynaklar", "Kaynaklar"),
    ("Değerlendirme Sistemi", "Değerlendirme Sistemi"),
    ("Yarıyıl Çalışmaları", "Değerlendirme Sistemi"),
    ("AKTS - İş Yükü", WORKLOAD),
)
TABLES = frozenset({LEARNING_OUTCOMES, WEEKLY_TOPICS})
NEVER_SPLIT = frozenset({WORKLOAD})

_TABLE_ROW = re.compile(r"^\d+ \|")
_IDENTITY_HEADER = "Ders Adı | Kodu"


@dataclass(frozen=True, slots=True)
class ChunkingResult:
    chunks: tuple[TextChunk, ...]
    warnings: tuple[str, ...] = ()


def split_sections(text: str) -> list[tuple[str, list[str]]]:
    """(section, lines) in reading order; a heading seen again continues its section."""
    sections: dict[str, list[str]] = {IDENTITY: []}
    current = IDENTITY
    for line in text.split("\n"):
        if not line.strip():
            continue
        current = next(
            (name for prefix, name in SECTION_STARTS if line.startswith(prefix)), current
        )
        sections.setdefault(current, []).append(line)
    return [(name, lines) for name, lines in sections.items() if lines]


def table_rows(lines: list[str]) -> list[str]:
    """Group a table's lines into rows: a row runs until the next line that starts "N |".

    The first row is the table header. A later row equal to it is the header repeated at
    the top of a new page and is dropped.
    """
    rows: list[str] = []
    for line in lines:
        # The header's first line also starts a row, so a repeated header is recognised.
        if rows and not _TABLE_ROW.match(line) and line != lines[0]:
            rows[-1] += "\n" + line
        else:
            rows.append(line)
    header = rows[0] if rows else None
    return [row for i, row in enumerate(rows) if i == 0 or row != header]


def _pack(rows: list[str], size: int, repeat_header: bool) -> list[str]:
    """Greedily join rows into chunks of at most `size` characters (a single longer row
    stays whole). With `repeat_header`, every chunk after the first starts with row 0."""
    chunks: list[list[str]] = [[]]
    for row in rows:
        current = chunks[-1]
        if current and len("\n".join([*current, row])) > size:
            current = [rows[0]] if repeat_header else []
            chunks.append(current)
        current.append(row)
    return ["\n".join(chunk) for chunk in chunks]


def chunk_section(name: str, lines: list[str], size: int) -> tuple[list[str], list[str]]:
    """Chunk texts for one section, and warnings."""
    rows = table_rows(lines) if name in TABLES else list(lines)
    whole = "\n".join(rows)
    if len(whole) <= size:
        return [whole], []
    if name in NEVER_SPLIT:
        return [whole], [f"{name} is {len(whole)} characters, over {size}, kept whole"]
    texts = _pack(rows, size, repeat_header=name in TABLES)
    warnings = [
        f"{name} has a line or row of {len(text)} characters, over {size}"
        for text in texts
        if len(text) > size
    ]
    return texts, warnings


def chunk_course_package(text: str, size: int = DEFAULT_SIZE) -> ChunkingResult:
    """Chunks for one cleaned course package; `page` is None (the source is TXT)."""
    chunks: list[TextChunk] = []
    warnings: list[str] = []
    for name, lines in split_sections(text):
        texts, section_warnings = chunk_section(name, lines, size)
        warnings += section_warnings
        for chunk_text in texts:
            chunks.append(TextChunk(text=chunk_text, position=len(chunks), section=name))
    return ChunkingResult(tuple(chunks), tuple(warnings))


def course_title(text: str) -> str | None:
    """ "Ad (KOD)" from the identity table: the row after "Ders Adı | Kodu | ..."."""
    lines = [line for line in text.split("\n") if line.strip()]
    for header, values in pairwise(lines):
        if header.startswith(_IDENTITY_HEADER):
            cells = [cell.strip() for cell in values.split("|")]
            if len(cells) >= 2 and cells[0] and cells[1]:
                return f"{cells[0]} ({cells[1]})"
            return None
    return None
