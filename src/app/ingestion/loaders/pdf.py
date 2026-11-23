"""PDF loader (regulations, FAQs, slide decks).

Each page with text becomes one `Segment` carrying its 1-based page number, so answers can
cite "page 3". Pages without text are skipped with a warning; there is no OCR.

After `clean_text`, PDF-only fixes run on each page. Each fixes one problem measured on the
real files in step 1a-2b and reports how many changes it made. Lines broken in the middle of
a sentence are deliberately left as they are.
"""

import re
from collections.abc import Callable
from pathlib import Path

import pdfplumber
from pdfminer.psexceptions import PSException
from pdfplumber.utils.exceptions import MalformedPDFException, PdfminerException

from app.ingestion.cleaning import clean_text
from app.ingestion.errors import DocumentReadError, EmptyDocumentError
from app.ingestion.models import LoadedDocument, Segment

# pdfplumber wraps pdfminer errors raised while opening a file in `PdfminerException`, but a
# page can still raise its own `MalformedPDFException` or an unwrapped pdfminer error while its
# text is read. `PSException` is the base class of every pdfminer error. An encrypted file
# arrives as a wrapped `PDFPasswordIncorrect`.
_READ_ERRORS = (PdfminerException, MalformedPDFException, PSException)

# A broken font encoding maps Turkish letters onto Latin Extended-A letters that Turkish never
# uses. Only the pairs seen in the real files are listed (StajBilgilendirmeSunumu1.pdf).
_BROKEN_TURKISH = {"Ġ": "İ", "ġ": "Ş", "Ģ": "ş"}
_BROKEN_TURKISH_TABLE = str.maketrans(_BROKEN_TURKISH)

# Icon fonts (Wingdings, Symbol) put bullet glyphs in the Unicode private-use area.
_PRIVATE_USE = "-"
_PRIVATE_USE_CHAR = re.compile(f"[{_PRIVATE_USE}]")
_LONE_GLYPH_LINE = re.compile(f"^[ \\t]*[{_PRIVATE_USE}][ \\t]*$")
# One glyph at line start followed by real text (not another glyph).
_LEADING_GLYPH = re.compile(f"^[ \\t]*[{_PRIVATE_USE}][ \\t]*(?=[^\\s{_PRIVATE_USE}])", re.M)
_MANY_BLANK_LINES = re.compile(r"\n{3,}")


def repair_turkish_letters(text: str) -> tuple[str, int]:
    """Replace Ġ, ġ, Ģ with İ, Ş, ş. Returns the new text and the number of letters fixed."""
    fixed = sum(text.count(broken) for broken in _BROKEN_TURKISH)
    return text.translate(_BROKEN_TURKISH_TABLE), fixed


def remove_lone_glyph_lines(text: str) -> tuple[str, int]:
    """Drop lines that hold a single private-use glyph and nothing else.

    In the measured slide deck such a glyph belongs to the line above it (pdfplumber puts it
    on its own line because it sits a little lower), so it cannot simply be joined to the next
    line. Placing it by its coordinates is a known limitation for now.
    """
    lines = text.split("\n")
    kept = [line for line in lines if not _LONE_GLYPH_LINE.match(line)]
    removed = len(lines) - len(kept)
    if not removed:
        return text, 0
    return _MANY_BLANK_LINES.sub("\n\n", "\n".join(kept)).strip(), removed


def convert_leading_glyphs(text: str) -> tuple[str, int]:
    """Turn a private-use glyph at the start of a line with text into a "- " bullet."""
    return _LEADING_GLYPH.subn("- ", text)


def count_private_use(text: str) -> int:
    """Count private-use glyphs; after the fixes above these are the ones inside lines."""
    return len(_PRIVATE_USE_CHAR.findall(text))


# Run in this order: a lone glyph line must be removed before leading glyphs are converted.
_FIXES: tuple[tuple[Callable[[str], tuple[str, int]], str], ...] = (
    (repair_turkish_letters, "fixed {} broken Turkish characters"),
    (remove_lone_glyph_lines, "removed {} lines holding only a bullet glyph"),
    (convert_leading_glyphs, "converted {} bullet glyphs at line start to '- '"),
)


def load_pdf(path: Path) -> LoadedDocument:
    """Read a PDF page by page, clean and fix each page, return one segment per page with text.

    Raises `DocumentReadError` if the file cannot be parsed and `EmptyDocumentError` if no
    page has text after cleaning.
    """
    segments: list[Segment] = []
    warnings: list[str] = []
    fix_counts = [0] * len(_FIXES)
    left_inside = 0
    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                text = clean_text(page.extract_text())
                for index, (fix, _) in enumerate(_FIXES):
                    text, changed = fix(text)
                    fix_counts[index] += changed
                left_inside += count_private_use(text)
                if text:
                    segments.append(Segment(text=text, page=page.page_number))
                else:
                    warnings.append(f"page {page.page_number}: no text (possibly scanned)")
    except _READ_ERRORS as exc:
        raise DocumentReadError(path, f"could not read PDF: {exc}") from exc

    warnings.extend(
        message.format(count)
        for count, (_, message) in zip(fix_counts, _FIXES, strict=True)
        if count
    )
    if left_inside:
        warnings.append(f"{left_inside} private-use characters left inside lines")

    if not segments:
        raise EmptyDocumentError(path, "no text on any page")

    return LoadedDocument(
        source=path,
        file_type="pdf",
        segments=tuple(segments),
        warnings=tuple(warnings),
    )
