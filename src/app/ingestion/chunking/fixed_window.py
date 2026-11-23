"""v1-like baseline: a recursive character splitter with a fixed size and overlap.

v1 used n8n's "Recursive Character Text Splitter" with 1000 characters and 200 characters of
overlap for PDF and TXT sources (TasarımDokuman.pdf, pages 11 and 15). This is a small,
dependency-free version of the same idea:

1. Split on the first separator that occurs in the text: a blank line, then a line break,
   then a space, and as a last resort between characters.
2. Pieces that fit are merged back, with the separator between them, up to `size`.
   When a chunk is full, it starts the next one with the last pieces of the previous one,
   at most `overlap` characters, so a sentence on the boundary appears in both.
3. A piece that is still too long is split again with the next separator.

The splitter works on character offsets, so every chunk is an exact slice of the input and
the page it starts on is known. Page boundaries are deliberately ignored, as in v1.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from app.ingestion.models import Segment, TextChunk

SEPARATORS: tuple[str, ...] = ("\n\n", "\n", " ", "")
DEFAULT_SIZE = 1000
DEFAULT_OVERLAP = 200
# Segments (PDF pages) are joined like `LoadedDocument.text` does.
SEGMENT_JOINER = "\n\n"


@dataclass(frozen=True, slots=True)
class _Span:
    start: int
    end: int

    @property
    def length(self) -> int:
        return self.end - self.start


def _split(text: str, span: _Span, separator: str) -> list[_Span]:
    """Pieces of `span` between occurrences of `separator`; empty pieces are dropped."""
    if separator == "":
        return [_Span(i, i + 1) for i in range(span.start, span.end)]
    pieces: list[_Span] = []
    start = span.start
    while True:
        found = text.find(separator, start, span.end)
        end = span.end if found == -1 else found
        if end > start:
            pieces.append(_Span(start, end))
        if found == -1:
            return pieces
        start = found + len(separator)


def _merge(pieces: list[_Span], separator: str, size: int, overlap: int) -> list[_Span]:
    """Merge consecutive pieces of one parent into windows of at most `size` characters."""
    windows: list[_Span] = []
    current: list[_Span] = []
    gap = len(separator)

    def length(spans: list[_Span]) -> int:
        return sum(s.length for s in spans) + gap * max(len(spans) - 1, 0)

    for piece in pieces:
        if current and length([*current, piece]) > size:
            windows.append(_Span(current[0].start, current[-1].end))
            # Keep the tail of the window as overlap, but leave room for the next piece.
            while current and (length(current) > overlap or length([*current, piece]) > size):
                current.pop(0)
        current.append(piece)
    if current:
        windows.append(_Span(current[0].start, current[-1].end))
    return windows


def _split_recursive(
    text: str, span: _Span, separators: Sequence[str], size: int, overlap: int
) -> list[_Span]:
    separator = next(
        (sep for sep in separators if sep == "" or sep in text[span.start : span.end]), ""
    )
    remaining = separators[separators.index(separator) + 1 :]
    windows: list[_Span] = []
    fitting: list[_Span] = []
    for piece in _split(text, span, separator):
        if piece.length <= size:
            fitting.append(piece)
            continue
        windows += _merge(fitting, separator, size, overlap)
        fitting = []
        windows += _split_recursive(text, piece, remaining, size, overlap)
    windows += _merge(fitting, separator, size, overlap)
    return windows


def _page_at(offset: int, page_starts: Sequence[tuple[int, int | None]]) -> int | None:
    page: int | None = None
    for start, segment_page in page_starts:
        if start > offset:
            break
        page = segment_page
    return page


def chunk_fixed_window(
    segments: Sequence[Segment], size: int = DEFAULT_SIZE, overlap: int = DEFAULT_OVERLAP
) -> tuple[TextChunk, ...]:
    """Split the document into windows of at most `size` characters with `overlap`.

    Each chunk carries the page it starts on (None for TXT) and no section.
    """
    if size <= 0:
        raise ValueError("size must be positive")
    if not 0 <= overlap < size:
        raise ValueError("overlap must be at least 0 and smaller than size")

    texts = [segment.text for segment in segments]
    text = SEGMENT_JOINER.join(texts)
    page_starts: list[tuple[int, int | None]] = []
    offset = 0
    for segment in segments:
        page_starts.append((offset, segment.page))
        offset += len(segment.text) + len(SEGMENT_JOINER)

    chunks: list[TextChunk] = []
    for window in _split_recursive(text, _Span(0, len(text)), SEPARATORS, size, overlap):
        raw = text[window.start : window.end]
        stripped = raw.strip()
        if not stripped:
            continue
        start = window.start + (len(raw) - len(raw.lstrip()))
        chunks.append(
            TextChunk(text=stripped, position=len(chunks), page=_page_at(start, page_starts))
        )
    return tuple(chunks)
