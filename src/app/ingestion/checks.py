"""Quality checks that feed the ingestion report. Checks never modify data, they only report."""

import re
from collections import Counter
from hashlib import sha256

from app.ingestion.cleaning import count_mojibake
from app.ingestion.models import Chunk, Finding, Page, Severity, Table

_TURKISH_LETTERS = frozenset("çğıöşüÇĞİÖŞÜ")
_YEAR_RANGE_RE = re.compile(r"\b(20\d{2}) ?[-–/] ?(20\d{2})\b")
SHORT_TEXT_CHARS = 200
TINY_CHUNK_CHARS = 60
IMAGE_ONLY_PAGE_CHARS = 80


def content_hash(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def check_text(text: str, *, expected_year: str | None = None) -> list[Finding]:
    findings: list[Finding] = []
    stripped = text.strip()
    if not stripped:
        return [Finding(Severity.ERROR, "empty_text", "no text after cleaning")]
    if len(stripped) < SHORT_TEXT_CHARS:
        findings.append(
            Finding(Severity.WARNING, "short_text", f"only {len(stripped)} characters of text")
        )
    if "�" in stripped:
        findings.append(
            Finding(
                Severity.WARNING,
                "replacement_characters",
                f"{stripped.count(chr(0xFFFD))} U+FFFD characters (lost during decoding)",
            )
        )
    if count_mojibake(stripped):
        findings.append(
            Finding(Severity.WARNING, "garbled_text", "broken Turkish encoding remains (Ġ/ġ/Ģ)")
        )
    letters = [c for c in stripped if c.isalpha()]
    if len(letters) >= 500:
        ratio = sum(c in _TURKISH_LETTERS for c in letters) / len(letters)
        if ratio < 0.01:
            findings.append(
                Finding(
                    Severity.WARNING,
                    "low_turkish_letter_ratio",
                    f"Turkish letters are {ratio:.1%} of letters; possible encoding problem",
                )
            )
    if expected_year:
        other = sorted(
            {
                f"{a}-{b}"
                for a, b in _YEAR_RANGE_RE.findall(stripped)
                if int(b) == int(a) + 1 and f"{a}-{b}" != expected_year
            }
        )
        if other:
            findings.append(
                Finding(
                    Severity.INFO,
                    "mentions_other_academic_year",
                    f"text mentions {', '.join(other)} (document year {expected_year})",
                )
            )
    return findings


def check_pages(pages: list[Page]) -> list[Finding]:
    findings: list[Finding] = []
    empty = [p.number for p in pages if not p.text.strip()]
    image_only = [
        p.number for p in pages if p.image_count and 0 < len(p.text.strip()) < IMAGE_ONLY_PAGE_CHARS
    ]
    if empty:
        findings.append(
            Finding(Severity.INFO, "empty_page", f"pages without text: {_ranges(empty)}")
        )
    if image_only:
        findings.append(
            Finding(
                Severity.INFO,
                "image_heavy_page",
                f"pages with images and under {IMAGE_ONLY_PAGE_CHARS} characters of text "
                f"(content may be in images): {_ranges(image_only)}",
            )
        )
    return findings


def check_chunks(chunks: list[Chunk], max_chars: int) -> list[Finding]:
    findings: list[Finding] = []
    if not chunks:
        return [Finding(Severity.ERROR, "no_chunks", "document produced no chunks")]
    counts = Counter(content_hash(c.content) for c in chunks)
    duplicates = sum(n - 1 for n in counts.values() if n > 1)
    if duplicates:
        findings.append(
            Finding(Severity.WARNING, "duplicate_chunk", f"{duplicates} duplicate chunk(s)")
        )
    oversized = [c.ordinal for c in chunks if c.char_count > max_chars]
    if oversized:
        findings.append(
            Finding(
                Severity.WARNING,
                "oversized_chunk",
                f"chunks over {max_chars} characters: {oversized}",
            )
        )
    tiny = [c.ordinal for c in chunks if c.char_count < TINY_CHUNK_CHARS]
    if tiny:
        findings.append(
            Finding(
                Severity.INFO, "tiny_chunk", f"chunks under {TINY_CHUNK_CHARS} characters: {tiny}"
            )
        )
    return findings


def check_table(table: Table) -> list[Finding]:
    findings: list[Finding] = []
    if not table.header or not table.rows:
        return [Finding(Severity.ERROR, "empty_table", "CSV has no header or no rows")]
    width = len(table.header)
    ragged = sum(1 for row in table.rows if len(row) != width)
    if ragged:
        findings.append(
            Finding(
                Severity.WARNING,
                "ragged_rows",
                f"{ragged} row(s) do not have {width} cells",
            )
        )
    duplicates = sum(n - 1 for n in Counter(tuple(r) for r in table.rows).values() if n > 1)
    if duplicates:
        findings.append(
            Finding(Severity.INFO, "duplicate_rows", f"{duplicates} exact duplicate row(s)")
        )
    for index, column in enumerate(table.header):
        empty = sum(1 for row in table.rows if index < len(row) and not row[index])
        if empty and column:
            findings.append(
                Finding(
                    Severity.INFO,
                    "empty_cells",
                    f"column {column!r}: {empty} of {len(table.rows)} rows empty",
                )
            )
    return findings


def _ranges(numbers: list[int]) -> str:
    """[1, 2, 3, 7] -> '1-3, 7'."""
    groups: list[list[int]] = []
    for n in numbers:
        if groups and n == groups[-1][-1] + 1:
            groups[-1].append(n)
        else:
            groups.append([n])
    return ", ".join(str(g[0]) if len(g) == 1 else f"{g[0]}-{g[-1]}" for g in groups)
