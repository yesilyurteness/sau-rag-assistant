"""Structure-aware chunking for the non-course sources (FAQ, numbered items, narrative, slides).

Every chunk keeps a context header (document title, academic year, section) separate from its
body, so a rule never loses the document it came from. Sizes are measured in characters (about
3.3 characters per token for Turkish), which avoids a tokenizer dependency in the core.
"""

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from app.ingestion.models import Chunk, Page

MAX_CHARS = 1200
MIN_CHARS = 120
CHARS_PER_TOKEN = 3.3  # rough Turkish average, only used for the stored token estimate

_LIST_START_RE = re.compile(r"^(?:[-•·Ø➢*]\s|\d+(?:[.-]\d+)*[.)-]\s|ADIM \d+|SORU \d+|CEVAP:)")
_DATE_ROW_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4}\s")
_UPPER_HEADING_RE = re.compile(r"^[A-ZÇĞİÖŞÜ0-9][A-ZÇĞİÖŞÜ0-9 .,()/:'’!&-]{7,}$")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÇĞİÖŞÜ0-9•\-(\"“])")
_PAGE_NUMBER_RE = re.compile(r"^\d{1,3}(?:/\d{1,3})?$")


@dataclass(frozen=True)
class ChunkContext:
    title: str
    academic_year: str | None = None
    max_chars: int = MAX_CHARS

    def header(self, section: str | None = None) -> str:
        return " | ".join(p for p in (self.title, self.academic_year, section) if p)


def estimate_tokens(text: str) -> int:
    return max(1, round(len(text) / CHARS_PER_TOKEN))


# --- text helpers ------------------------------------------------------------------------------


def split_long(text: str, max_chars: int) -> list[str]:
    """Split into pieces of at most `max_chars`, keeping line breaks.

    Lines are the units; a line longer than the limit is split at sentence boundaries, and a
    sentence longer than the limit is hard-split at a space as a last resort.
    """
    if len(text) <= max_chars:
        return [text]
    units: list[str] = []
    for line in text.split("\n"):
        units.extend(_split_line(line, max_chars) if len(line) > max_chars else [line])
    pieces: list[str] = []
    current = ""
    for unit in units:
        candidate = f"{current}\n{unit}" if current else unit
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                pieces.append(current)
            current = unit
    if current:
        pieces.append(current)
    return [p.strip() for p in pieces if p.strip()]


def _split_line(line: str, max_chars: int) -> list[str]:
    pieces: list[str] = []
    current = ""
    for sentence in _SENTENCE_SPLIT_RE.split(line):
        candidate = f"{current} {sentence}" if current else sentence
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            pieces.append(current)
        current = sentence
        while len(current) > max_chars:
            cut = current.rfind(" ", 0, max_chars)
            cut = cut if cut > 0 else max_chars
            pieces.append(current[:cut].strip())
            current = current[cut:].strip()
    if current:
        pieces.append(current)
    return pieces


def pack(blocks: Iterable[str], max_chars: int, joiner: str = "\n") -> list[str]:
    """Greedily combine blocks into pieces of at most `max_chars`; oversized blocks are split."""
    out: list[str] = []
    current = ""
    for block in blocks:
        for part in split_long(block, max_chars):
            candidate = f"{current}{joiner}{part}" if current else part
            if len(candidate) <= max_chars:
                current = candidate
            else:
                if current:
                    out.append(current)
                current = part
    if current:
        out.append(current)
    return out


def _starts_item(line: str) -> bool:
    return bool(_LIST_START_RE.match(line) or _DATE_ROW_RE.match(line))


def reflow(text: str) -> str:
    """Re-join lines wrapped at the page width; list items and table rows keep their own line."""
    paragraphs = re.split(r"\n\s*\n", text.strip())
    out: list[str] = []
    for para in paragraphs:
        lines = [ln.strip() for ln in para.split("\n") if ln.strip()]
        merged: list[str] = []
        for index, line in enumerate(lines):
            next_is_row = index + 1 < len(lines) and bool(_DATE_ROW_RE.match(lines[index + 1]))
            if not merged or _starts_item(line) or next_is_row:
                merged.append(line)
                continue
            prev = merged[-1]
            wrapped = len(prev) >= 40 and prev[-1] not in ".!?:;" and not _DATE_ROW_RE.match(prev)
            if wrapped:
                merged[-1] = f"{prev} {line}"
            else:
                merged.append(line)
        out.append("\n".join(merged))
    return "\n\n".join(out)


def is_heading(block: str) -> bool:
    """A short single line without sentence punctuation, e.g. 'Tarihçe' or 'Misyon ve Vizyon'."""
    if "\n" in block or len(block) > 70:
        return False
    return block[-1] not in ".:;,!?" and not _starts_item(block)


# --- chunk assembly ----------------------------------------------------------------------------


def _chunk(
    ctx: ChunkContext,
    section: str,
    content: str,
    page_start: int | None = None,
    page_end: int | None = None,
) -> Chunk:
    return Chunk(
        ordinal=0,
        section=section,
        header=ctx.header(section),
        content=content,
        page_start=page_start,
        page_end=page_end,
    )


def finalize(
    chunks: list[Chunk], min_chars: int = MIN_CHARS, max_chars: int = MAX_CHARS
) -> list[Chunk]:
    """Merge chunks shorter than `min_chars` into a neighbour, drop empty ones, and number them.

    A merge never makes a chunk longer than `max_chars + min_chars`; if it would, the short
    chunk stays on its own.
    """
    merged: list[Chunk] = []
    pending: Chunk | None = None
    for chunk in (c for c in chunks if c.content.strip()):
        if pending is not None:
            chunk = _join(pending, chunk, keep_first_header=False)
            pending = None
        if chunk.char_count < min_chars:
            if merged and merged[-1].char_count + chunk.char_count < max_chars + min_chars:
                merged[-1] = _join(merged[-1], chunk, keep_first_header=True)
            elif not merged:
                pending = chunk
            else:
                merged.append(chunk)
            continue
        merged.append(chunk)
    if pending is not None:
        merged.append(pending)
    return [
        Chunk(i, c.section, c.header, c.content, c.page_start, c.page_end, c.metadata)
        for i, c in enumerate(merged)
    ]


def _join(first: Chunk, second: Chunk, *, keep_first_header: bool) -> Chunk:
    base = first if keep_first_header else second
    pages = [p for p in (first.page_start, second.page_start) if p is not None]
    page_ends = [p for p in (first.page_end, second.page_end) if p is not None]
    return Chunk(
        ordinal=0,
        section=base.section,
        header=base.header,
        content=f"{first.content}\n{second.content}",
        page_start=min(pages) if pages else None,
        page_end=max(page_ends) if page_ends else None,
        metadata=base.metadata,
    )


# --- strategies --------------------------------------------------------------------------------


def chunk_faq(text: str, ctx: ChunkContext) -> list[Chunk]:
    """One chunk per `•Question?` and its answer; the question repeats if the answer splits."""
    items: list[tuple[str, list[str]]] = []
    question: list[str] | None = None
    answer: list[str] = []
    for line in (ln.strip() for ln in text.split("\n")):
        if line.startswith("•") or (_is_soru(line)):
            if question is not None:
                items.append((" ".join(question), answer))
            question, answer = [re.sub(r"^•\s*|^SORU \d+:\s*", "", line)], []
        elif question is not None and not answer and not question[-1].endswith("?") and line:
            question.append(line)  # question wrapped onto the next line
        elif question is not None:
            answer.append(re.sub(r"^CEVAP:\s*", "", line))
    if question is not None:
        items.append((" ".join(question), answer))

    chunks: list[Chunk] = []
    for question_text, answer_lines in items:
        body = reflow("\n".join(answer_lines)).strip()
        for n, part in enumerate(split_long(body, ctx.max_chars - len(question_text) - 12)):
            label = "Cevap" if n == 0 else "Cevap (devam)"
            content = f"Soru: {question_text}\n{label}: {part}"
            chunks.append(_chunk(ctx, question_text[:90], content))
    return finalize(chunks)


def _is_soru(line: str) -> bool:
    return bool(re.match(r"^SORU \d+:", line))


def chunk_numbered(
    text: str,
    ctx: ChunkContext,
    marker: re.Pattern[str],
    *,
    item_label: Callable[[str], str],
    pack_items: bool,
) -> list[Chunk]:
    """Split text at numbered items; an upper-case heading line starts a new section.

    `pack_items=False` keeps each item in its own chunk (committee decisions, each is a rule);
    `True` packs consecutive items up to the size limit (procedure steps), and the section label
    names the first and last item in the chunk.
    """
    sections: list[tuple[str, list[list[str]]]] = [("Giriş", [[]])]
    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            continue
        if marker.match(line):
            sections[-1][1].append([line])
        elif _UPPER_HEADING_RE.match(line) and not _DATE_ROW_RE.match(line):
            current = sections[-1][1][-1]
            if current and _mostly_upper(current[-1]):
                line = f"{current.pop()} {line}"  # heading wrapped over two lines
            sections.append((line, [[]]))
        else:
            sections[-1][1][-1].append(line)

    chunks: list[Chunk] = []
    for section_name, items in sections:
        blocks = [
            (item_label(i[0]) if marker.match(i[0]) else "", reflow("\n".join(i)))
            for i in items
            if i
        ]
        if not pack_items:
            for label, body in blocks:
                for part in split_long(body, ctx.max_chars):
                    chunks.append(_chunk(ctx, label or section_name, part))
            continue
        group: list[tuple[str, str]] = []
        for label, body in blocks:
            for part in split_long(body, ctx.max_chars):
                size = sum(len(b) + 1 for _, b in group) + len(part)
                if group and size > ctx.max_chars:
                    chunks.append(_numbered_group(ctx, section_name, group))
                    group = []
                group.append((label, part))
        if group:
            chunks.append(_numbered_group(ctx, section_name, group))
    return finalize(chunks)


def _numbered_group(ctx: ChunkContext, section: str, group: list[tuple[str, str]]) -> Chunk:
    labels = [label for label, _ in group if label]
    if not labels:
        name = section
    elif labels[0] == labels[-1]:
        name = f"{section} / {labels[0]}"
    else:
        name = f"{section} / {labels[0]} - {labels[-1].split(' ', 1)[-1]}"
    return _chunk(ctx, name, "\n".join(b for _, b in group))


def _mostly_upper(line: str) -> bool:
    letters = [c for c in line if c.isalpha()]
    words = [w for w in line.split() if any(c.isalpha() for c in w)]
    upper = [w for w in words if w.isupper()]
    return len(letters) >= 8 and len(words) >= 2 and len(upper) / len(words) >= 0.6


def chunk_narrative(text: str, ctx: ChunkContext) -> list[Chunk]:
    """Headings and paragraphs: each section becomes one or more chunks."""
    blocks: list[str] = []
    for block in (b.strip() for b in re.split(r"\n\s*\n", reflow(text)) if b.strip()):
        first, _, rest = block.partition("\n")
        if rest and is_heading(first):
            blocks.extend([first, rest])  # "Tarihçe\nParagraph..." without a blank line
        else:
            blocks.append(block)
    sections: list[tuple[str, list[str]]] = []
    heading_stack: list[str] = []
    body: list[str] = []
    for block in blocks:
        if is_heading(block) or (_UPPER_HEADING_RE.match(block) and "\n" not in block):
            if body:
                sections.append((" > ".join(heading_stack) or ctx.title, body))
                body, heading_stack = [], []
            heading_stack.append(block)
        else:
            body.append(block)
    if body or heading_stack:
        sections.append((" > ".join(heading_stack) or ctx.title, body))

    chunks: list[Chunk] = []
    for section, paragraphs in sections:
        for part in pack(paragraphs, ctx.max_chars, joiner="\n"):
            chunks.append(_chunk(ctx, section, part))
    return finalize(chunks)


def clean_slide_text(text: str) -> str:
    """Drop the slide number printed at the top or bottom of the page."""
    lines = [ln for ln in text.split("\n")]
    while lines and (not lines[-1].strip() or _PAGE_NUMBER_RE.match(lines[-1].strip())):
        lines.pop()
    while lines and (not lines[0].strip() or _PAGE_NUMBER_RE.match(lines[0].strip())):
        lines.pop(0)
    if lines and re.search(r"\s\d{1,3}$", lines[-1]) and len(lines) > 1:
        lines[-1] = re.sub(r"\s\d{1,3}$", "", lines[-1])  # "...önerilir. 15"
    return "\n".join(lines).strip()


def chunk_slides(pages: list[Page], ctx: ChunkContext) -> list[Chunk]:
    """Pack consecutive slides into chunks; a slide is never split unless it exceeds the limit."""
    slides: list[tuple[int, str]] = []
    for page in pages:
        text = reflow(clean_slide_text(page.text))
        if text:
            slides.append((page.number, f"Slayt {page.number}: {text}"))

    chunks: list[Chunk] = []
    group: list[tuple[int, str]] = []

    def flush() -> None:
        if not group:
            return
        first, last = group[0][0], group[-1][0]
        label = f"Slayt {first}" if first == last else f"Slayt {first}-{last}"
        chunks.append(_chunk(ctx, label, "\n".join(t for _, t in group), first, last))
        group.clear()

    for number, text in slides:
        size = sum(len(t) + 1 for _, t in group) + len(text)
        if group and size > ctx.max_chars:
            flush()
        if len(text) > ctx.max_chars:
            for n, part in enumerate(split_long(text, ctx.max_chars)):
                chunks.append(_chunk(ctx, f"Slayt {number} ({n + 1})", part, number, number))
            continue
        group.append((number, text))
    flush()
    return finalize(chunks)
