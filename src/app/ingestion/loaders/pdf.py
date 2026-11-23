"""PDF loader (regulations, FAQs, slide decks).

Each page with text becomes one `Segment` carrying its 1-based page number, so answers can
cite "page 3". Pages without text are skipped with a warning; there is no OCR. Rules that only
PDFs need (font repairs, broken lines) are added after measuring the real files (step 1a-2c).
"""

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


def load_pdf(path: Path) -> LoadedDocument:
    """Read a PDF page by page, clean each page and return one segment per page with text.

    Raises `DocumentReadError` if the file cannot be parsed and `EmptyDocumentError` if no
    page has text after cleaning.
    """
    segments: list[Segment] = []
    warnings: list[str] = []
    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                text = clean_text(page.extract_text())
                if text:
                    segments.append(Segment(text=text, page=page.page_number))
                else:
                    warnings.append(f"page {page.page_number}: no text (possibly scanned)")
    except _READ_ERRORS as exc:
        raise DocumentReadError(path, f"could not read PDF: {exc}") from exc

    if not segments:
        raise EmptyDocumentError(path, "no text on any page")

    return LoadedDocument(
        source=path,
        file_type="pdf",
        segments=tuple(segments),
        warnings=tuple(warnings),
    )
