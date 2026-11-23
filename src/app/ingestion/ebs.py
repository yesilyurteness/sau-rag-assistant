"""Cleanup of course information packages printed from EBS (Eğitim Bilgi Sistemi).

Each EBS page appears twice in these files: first as a table copy, whose cells are separated
by " | ", then as a flat copy. A timestamp line ends the table copy and the page URL ends the
flat copy:

    [table copy] / "30.11.2025 16:02 Eğitim Bilgi Sistemi" / [flat copy] / "https://ebs... 1/3"

Measured in step 1c-4a on the 82 course packages: the table copy keeps the links between
columns (learning outcome and method, workload columns) while the flat copy loses them, so
the table copy is kept. Only the flat copy has the title line with the academic year, so that
line is taken from it. Every function here is pure; `clean_ebs` reports its changes as
warnings, and the flat copy is used only to measure how many words the result lost.
"""

import re
from collections import Counter
from dataclasses import dataclass

TITLE_PREFIX = "Eğitim Bilgi Sistemi Endüstri Mühendisliği Bölümü"
WORD_LOSS_WARNING = 0.02

_TIMESTAMP = re.compile(r"^\d{2}\.\d{2}\.\d{4} \d{2}:\d{2} Eğitim Bilgi Sistemi$")
_PAGE_URL = re.compile(r"^https://ebs\.sakarya\.edu\.tr/\S+ \d+/\d+$")
_PRIVATE_USE = re.compile("[\ue000-\uf8ff]")
# EBS wraps collapsible rows of the assessment table in these two glyphs.
ROW_OPEN, ROW_CLOSE = "\uedd9", "\uedda"
# "1/", "| | 2/ |", "| | 3/3": the page counter, alone on its line between pipes.
_PAGE_MARK = re.compile(r"^[|\s]*\d+/\d*[|\s]*$")
# A first cell of at most four characters ending in a letter, then a cell starting with a
# letter: the table copy cut the first word of a wrapped row ("1. Y | ıl", "AK | TS").
_SPLIT_FIRST_WORD = re.compile(r"^(\s*[^|]{0,3}[^\W\d_]) \| ([^\W\d_])")
_YEAR = re.compile(r"\((\d{4}) - (\d{4})\)")
_SPACES = re.compile(r"[ \t]+")

# Program outcomes ("Program Çıktıları") are the same department-wide list in every package;
# only the contribution marks differ. The section is skipped (decision 1c-4a) and ends at the
# next of these headings, which may be on a later page.
_TABLE_OUTCOMES_START = ("Sıra | Program Çıktıları",)
_FLAT_OUTCOMES_START = ("Katkı Düzeyi", "Sıra Program Çıktıları")
_OUTCOMES_END = (
    "# | Ders Öğrenme Çıktılarının Program Çıktılarına Katkısı",
    "# Ders Öğrenme Çıktılarının Program Çıktılarına Katkısı",
    "Değerlendirme Sistemi",
    "Yarıyıl Çalışmaları",
    "AKTS - İş Yükü",
    "Kaynaklar",
)
# The matrix "Ders Öğrenme Çıktılarının Program Çıktılarına Katkısı" maps each learning outcome
# to program outcome numbers; it is skipped too (decision 1c-4b) and ends at the next heading.
_TABLE_MATRIX_START = ("# | Ders Öğrenme Çıktılarının Program Çıktılarına Katkısı",)
_FLAT_MATRIX_START = ("# Ders Öğrenme Çıktılarının Program Çıktılarına Katkısı",)
_MATRIX_END = ("Değerlendirme Sistemi", "Yarıyıl Çalışmaları", "AKTS - İş Yükü", "Kaynaklar")
# A contribution mark: an "X" cell in the table copy.
_MARK = re.compile(r"(^|\|)\s*X\s*(\||$)")


class NotAnEbsPrintoutError(ValueError):
    """The text does not have the EBS page structure (timestamp and URL lines)."""


@dataclass(frozen=True, slots=True)
class EbsCopies:
    table: tuple[str, ...]
    flat: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EbsResult:
    text: str
    title: str | None
    academic_year: str | None
    word_loss: float
    warnings: tuple[str, ...]


def split_copies(text: str) -> EbsCopies:
    """Separate the table-copy lines from the flat-copy lines of every page."""
    table: list[str] = []
    flat: list[str] = []
    in_flat = False
    timestamps = urls = 0
    for line in text.split("\n"):
        if _TIMESTAMP.match(line.strip()):
            timestamps += 1
            in_flat = True
        elif _PAGE_URL.match(line.strip()):
            urls += 1
            in_flat = False
        else:
            (flat if in_flat else table).append(line)
    if timestamps == 0 or timestamps != urls:
        raise NotAnEbsPrintoutError(
            f"expected one timestamp and one URL line per page, got {timestamps} and {urls}"
        )
    return EbsCopies(tuple(table), tuple(flat))


def find_title(flat: tuple[str, ...]) -> str | None:
    """The flat copy's title, e.g. "... Bölümü İstatistik Olasılık I (2025 - 2026)".

    A long course name wraps: the title then continues on the next content lines (after the
    toolbar glyphs) until the "(YYYY - YYYY)" year; at most two more lines are joined.
    """
    start = next((i for i, line in enumerate(flat) if line.strip().startswith(TITLE_PREFIX)), None)
    if start is None:
        return None
    parts = [flat[start].strip()]
    following = (line.strip() for line in flat[start + 1 :] if not is_layout_line(line))
    for line in following:
        if _YEAR.search(parts[-1]) or len(parts) == 3:
            break
        parts.append(line)
    return " ".join(parts) if _YEAR.search(parts[-1]) else parts[0]


def title_academic_year(title: str) -> str | None:
    """ "(2025 - 2026)" in the title as "2025-2026"; compared with the manifest in step 1d."""
    match = _YEAR.search(title)
    return f"{match.group(1)}-{match.group(2)}" if match else None


def is_layout_line(line: str) -> bool:
    """Page counters and lines of only pipes or private-use glyphs: no content."""
    stripped = line.strip()
    if _PAGE_MARK.match(stripped):
        return True
    return not _PRIVATE_USE.sub("", stripped).replace("|", "").strip()


def rejoin_wrapped_row(line: str) -> tuple[str, int]:
    """Drop the collapsible-row glyphs and rejoin a first word the table copy cut in two.

    Only rows wrapped in U+EDD9 ... U+EDDA are touched; the two real cases are
    "1. Y | ıl İçinin Başarıya" and "AK | TS - İş Yükü". Returns the line and 0 or 1.
    """
    if ROW_OPEN not in line:
        return line, 0
    inner = line.replace(ROW_OPEN, "").replace(ROW_CLOSE, "")
    return _SPLIT_FIRST_WORD.subn(r"\1\2", inner, count=1)


def skip_section(
    lines: tuple[str, ...], starts: tuple[str, ...], ends: tuple[str, ...]
) -> tuple[list[str], int]:
    """Drop lines from a line starting with `starts` up to the next line starting with `ends`.

    Returns the kept lines and how many dropped lines carried a contribution mark ("X").
    """
    kept: list[str] = []
    marked = 0
    skipping = False
    for line in lines:
        text = _PRIVATE_USE.sub("", line).strip()
        if not skipping and text.startswith(starts):
            skipping = True
        elif skipping and text.startswith(ends):
            skipping = False
        if skipping:
            marked += bool(_MARK.search(text))
        else:
            kept.append(line)
    return kept, marked


def _words(lines: list[str]) -> Counter[str]:
    # Commas count as separators: the table copy writes "TORKUL,Öğr.Gör." where the flat
    # copy writes "TORKUL, Öğr.Gör.", and that is not a lost word.
    return Counter(
        word
        for line in lines
        if not is_layout_line(line)
        for word in _PRIVATE_USE.sub(" ", line.replace("|", " ").replace(",", " ")).split()
    )


def word_loss(result_lines: list[str], flat_lines: list[str]) -> float:
    """Share of the flat copy's words (counted with repeats) missing from the result."""
    flat_words = _words(flat_lines)
    total = sum(flat_words.values())
    if not total:
        return 0.0
    return sum((flat_words - _words(result_lines)).values()) / total


def clean_ebs(text: str) -> EbsResult:
    """Title line plus the cleaned table copy, without program outcomes and their matrix."""
    copies = split_copies(text)
    title = find_title(copies.flat)

    table, marked_rows = skip_section(copies.table, _TABLE_OUTCOMES_START, _OUTCOMES_END)
    before_matrix = len(table)
    table, _ = skip_section(tuple(table), _TABLE_MATRIX_START, _MATRIX_END)
    matrix_lines = before_matrix - len(table)
    flat, _ = skip_section(copies.flat, _FLAT_OUTCOMES_START, _OUTCOMES_END)
    flat, _ = skip_section(tuple(flat), _FLAT_MATRIX_START, _MATRIX_END)

    glyphs = sum(len(_PRIVATE_USE.findall(line)) for line in table)
    lines: list[str] = [title] if title else []
    layout_lines = rejoined = 0
    for line in table:
        if is_layout_line(line):
            layout_lines += 1
            continue
        line, fixed = rejoin_wrapped_row(line)
        rejoined += fixed
        line = _SPACES.sub(" ", _PRIVATE_USE.sub("", line)).strip()
        if line:
            lines.append(line)

    loss = word_loss(lines, [line for line in flat if line.strip() != title])

    warnings = [f"kept the table copy; removed {layout_lines} layout lines"]
    if glyphs:
        warnings.append(f"removed {glyphs} private-use glyphs")
    if rejoined:
        warnings.append(f"rejoined {rejoined} words split inside a collapsible row")
    warnings.append(f"skipped the program outcomes section ({marked_rows} rows with a mark)")
    if matrix_lines:
        warnings.append(
            f"skipped the learning outcome to program outcome matrix ({matrix_lines} lines)"
        )
    if title is None:
        warnings.append("no EBS title line, academic year unknown")
    if loss > WORD_LOSS_WARNING:
        warnings.append(f"{loss:.1%} of the flat copy's words are missing from the table copy")

    year = title_academic_year(title) if title else None
    return EbsResult("\n".join(lines), title, year, loss, tuple(warnings))
