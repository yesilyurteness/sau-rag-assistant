"""Text cleaning that applies to every source, plus the course-package specific cleaner.

Cleaning is deliberately conservative: it removes layout noise (icon glyphs, page markers, duplicate
print copies) and repairs known encoding damage, but never rewrites wording.
"""

import re
import unicodedata
from dataclasses import dataclass

# Characters in the Unicode private-use area: icon fonts, Wingdings and Symbol bullets.
_PUA_RE = re.compile("[\ue000-\uf8ff]")
# A private-use glyph at line start followed by real text is a bullet; icon-only lines are dropped.
_LEADING_PUA_BULLET_RE = re.compile(
    r"^([ \t]*)[\ue000-\uf8ff]+[ \t]*(?=[^\s\ue000-\uf8ff])", re.MULTILINE
)
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u200b\u200e\u200f\ufeff]")

# PDF fonts with a broken encoding map Turkish letters onto Latin Extended-A. None of these letters
# occur in Turkish, so the repair is safe: Ġ -> İ, ġ -> Ş, Ģ -> ş.
_MOJIBAKE_TABLE = str.maketrans({"Ġ": "İ", "ġ": "Ş", "Ģ": "ş"})
_MOJIBAKE_CHARS = frozenset("ĠġĢ")

# Markdown escapes left behind by a copy through a markdown converter: "\>", "\*", "\-", "\!" ...
_MD_ESCAPE_RE = re.compile(r"\\([>*\-#!.&_()\[\]|+~`])")


@dataclass(frozen=True)
class CleanResult:
    text: str
    removed_chars: int = 0  # characters dropped as duplicate copies (course packages)
    mojibake_repaired: int = 0
    pua_removed: int = 0


def count_mojibake(text: str) -> int:
    return sum(ch in _MOJIBAKE_CHARS for ch in text)


def repair_mojibake(text: str) -> tuple[str, int]:
    """Fix the Ġ/ġ/Ģ encoding damage; returns the new text and the number of characters fixed."""
    count = count_mojibake(text)
    return (text.translate(_MOJIBAKE_TABLE), count) if count else (text, 0)


def strip_markdown_escapes(text: str) -> str:
    return _MD_ESCAPE_RE.sub(r"\1", text)


def normalize_whitespace(text: str) -> str:
    """Unix newlines, no trailing spaces, at most one blank line in a row, no outer blank lines."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    out: list[str] = []
    for line in lines:
        if not line and out and not out[-1]:
            continue
        out.append(line)
    return "\n".join(out).strip()


def base_clean(text: str) -> CleanResult:
    """NFC, control characters, private-use glyphs (leading ones become '- ' bullets), mojibake."""
    text = unicodedata.normalize("NFC", text)
    text = _CONTROL_RE.sub("", text)
    pua_total = len(_PUA_RE.findall(text))
    text = _LEADING_PUA_BULLET_RE.sub(r"\1- ", text)
    text = _PUA_RE.sub("", text)
    text, fixed = repair_mojibake(text)
    return CleanResult(
        text=normalize_whitespace(text), mojibake_repaired=fixed, pua_removed=pua_total
    )


# --- Course packages (EBS prints) ----------------------------------------------------------------

_STAMP_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4} \d{2}:\d{2} Eğitim Bilgi Sistemi$")
_EBS_FOOTER_RE = re.compile(r"^https?://ebs\.sakarya\.edu\.tr/\S+ \d+/\d+$")
_PAGE_MARKER_RE = re.compile(r"^\d+/$")
_PIPE_NOISE_RE = re.compile(r"^[\s|]*(\d+/)?[\s|]*$")
_TITLE_RE = re.compile(
    r"^Eğitim Bilgi Sistemi (?P<unit>.+?) Bölümü (?P<title>.+?) "
    r"\((?P<y1>\d{4}) ?- ?(?P<y2>\d{4})\)$"
)
_EBS_ID_RE = re.compile(r"/Ders/Detay/(\d+)")


@dataclass(frozen=True)
class CourseMeta:
    title: str | None = None
    academic_year: str | None = None
    ebs_course_id: str | None = None
    printed_at: str | None = None


def clean_course_package(text: str) -> tuple[CleanResult, CourseMeta]:
    """Drop the flat print copy of every page and the page noise; keep the pipe-table copy.

    Each EBS page was printed twice: a pipe-table copy, then a flat copy that starts at a stamp
    line (`30.11.2025 16:27 Eğitim Bilgi Sistemi`) and ends at the `ebs.sakarya.edu.tr` footer.
    The flat copy carries the course title with the academic year, so metadata is read from it
    before it is discarded. A flat copy without a footer is kept (nothing is dropped blindly).
    """
    base = base_clean(text)
    lines = base.text.split("\n")

    kept: list[str] = []
    removed = 0
    meta = CourseMeta()
    i = 0
    while i < len(lines):
        line = lines[i]
        if _STAMP_RE.match(line):
            end = next(
                (j for j in range(i + 1, len(lines)) if _EBS_FOOTER_RE.match(lines[j])), None
            )
            if end is not None:
                meta = _merge_meta(meta, lines[i : end + 1])
                removed += sum(len(x) + 1 for x in lines[i : end + 1])
                i = end + 1
                continue
        kept.append(line)
        i += 1

    cleaned: list[str] = []
    for line in kept:
        if line and (_PAGE_MARKER_RE.match(line) or _PIPE_NOISE_RE.match(line)):
            continue  # page markers ("2/") and rows made only of pipes
        cleaned.append(line)
    text_out = normalize_whitespace("\n".join(cleaned))
    return (
        CleanResult(
            text=text_out,
            removed_chars=removed,
            mojibake_repaired=base.mojibake_repaired,
            pua_removed=base.pua_removed,
        ),
        meta,
    )


def _merge_meta(meta: CourseMeta, flat_lines: list[str]) -> CourseMeta:
    title, year, ebs_id, printed = (
        meta.title,
        meta.academic_year,
        meta.ebs_course_id,
        meta.printed_at,
    )
    for line in flat_lines:
        if printed is None and _STAMP_RE.match(line):
            printed = line.removesuffix(" Eğitim Bilgi Sistemi")
        match = _TITLE_RE.match(line)
        if match and title is None:
            title = match.group("title")
            year = f"{match.group('y1')}-{match.group('y2')}"
        id_match = _EBS_ID_RE.search(line)
        if id_match and ebs_id is None:
            ebs_id = id_match.group(1)
    return CourseMeta(title=title, academic_year=year, ebs_course_id=ebs_id, printed_at=printed)
