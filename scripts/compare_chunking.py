"""Compare structure-aware chunking with a fixed-window baseline on the real source files.

Usage (from the repository root, source files are not in git):
    uv run python scripts/compare_chunking.py --source-dir data/raw/v1-kaynaklar

Structural metrics only; retrieval metrics (Recall@5, MRR) come with the eval runner in step 3.
- unit integrity: share of FAQ answers, committee decisions and procedure steps that sit whole
  inside a single chunk (a split rule can be retrieved without its condition);
- context: share of chunks whose embedded text names the document and the academic year;
- duplicate text: share of chunk characters that repeat the EBS flat print copy;
- size: chunk count and median characters.
"""

import argparse
import re
import statistics
from dataclasses import dataclass
from pathlib import Path

from app.ingestion.loaders import load_bytes
from app.ingestion.manifest import load_manifest
from app.ingestion.models import SourceKind, Target
from app.ingestion.pipeline import discover, process_file

WINDOW, OVERLAP = 1000, 200
_LABELS = re.compile(r"^(Soru|Cevap|Cevap \(devam\)):\s?", re.MULTILINE)  # added by the FAQ chunker


def norm(text: str) -> str:
    return re.sub(r"[^0-9a-zçğıöşü]", "", text.lower())


def fixed_windows(text: str, size: int = WINDOW, overlap: int = OVERLAP) -> list[str]:
    """v1-style splitter: fixed character windows with overlap, cut at the last space."""
    chunks, start = [], 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            space = text.rfind(" ", start + size // 2, end)
            end = space if space > 0 else end
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def units(kind: SourceKind, text: str) -> list[str]:
    """Ground-truth units taken from the source text itself (questions, decisions, steps)."""
    if kind is SourceKind.FAQ:
        parts = re.split(r"\n\s*•", "\n" + text)
    elif kind is SourceKind.DECISIONS:
        parts = re.split(r"\n(?=\d+\.\s)", text)[1:]
    elif kind is SourceKind.PROCEDURE:
        parts = re.split(r"\n(?=\d+(?:[.-]\d+)*-\s|\d+-\d+\s)", text)[1:]
    else:
        return []
    return [p for p in (norm(x) for x in parts) if len(p) > 40]


@dataclass
class Tally:
    units: int = 0
    intact_structured: int = 0
    intact_fixed: int = 0
    chunks_structured: int = 0
    chunks_fixed: int = 0
    context_structured: int = 0
    context_fixed: int = 0
    sizes_structured: list[int] | None = None
    sizes_fixed: list[int] | None = None
    dup_chars_fixed: int = 0
    chars_fixed: int = 0

    def __post_init__(self) -> None:
        self.sizes_structured, self.sizes_fixed = [], []


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=Path("config/sources.toml"))
    parser.add_argument("--verbose", action="store_true", help="list units split by v2")
    args = parser.parse_args()
    manifest = load_manifest(args.manifest)
    t = Tally()

    for path in discover(args.source_dir):
        entry = manifest.resolve(path.name)
        if entry is None or entry.skipped or entry.kind is SourceKind.TABULAR:
            continue
        data = path.read_bytes()
        doc = process_file(path, entry, data)
        if doc.target is not Target.VECTOR or not doc.chunks:
            continue
        raw = load_bytes(path, data).text
        fixed = fixed_windows(raw)
        structured = [norm(_LABELS.sub("", c.embedding_text)) for c in doc.chunks]
        fixed_norm = [norm(c) for c in fixed]

        for unit in units(entry.kind, raw):
            if args.verbose and not any(unit in c for c in structured):
                print(f"split in v2: {path.name}: {unit[:70]}")
            t.units += 1
            t.intact_structured += any(unit in c for c in structured)
            t.intact_fixed += any(unit in c for c in fixed_norm)

        title_year = [norm(doc.title)[:20], norm(doc.academic_year or "")]
        t.chunks_structured += len(doc.chunks)
        t.chunks_fixed += len(fixed)
        t.context_structured += sum(all(k in c for k in title_year) for c in structured)
        t.context_fixed += sum(all(k in c for k in title_year) for c in fixed_norm)
        assert t.sizes_structured is not None and t.sizes_fixed is not None  # noqa: S101
        t.sizes_structured += [c.char_count for c in doc.chunks]
        t.sizes_fixed += [len(c) for c in fixed]

        if entry.kind is SourceKind.COURSE_PACKAGE:
            t.chars_fixed += len(raw)
            t.dup_chars_fixed += doc.duplicate_chars_removed

    def pct(a: int, b: int) -> str:
        return f"{a / b:.0%} ({a}/{b})" if b else "n/a"

    print("| Metric | Fixed 1000/200 (v1-style) | Structure-aware (v2) |")
    print("|---|---|---|")
    print(f"| Units kept whole (FAQ, decisions, steps) | {pct(t.intact_fixed, t.units)} "
          f"| {pct(t.intact_structured, t.units)} |")  # fmt: skip
    print(f"| Chunks naming document and year | {pct(t.context_fixed, t.chunks_fixed)} "
          f"| {pct(t.context_structured, t.chunks_structured)} |")  # fmt: skip
    print(f"| Chunks | {t.chunks_fixed} | {t.chunks_structured} |")
    print(f"| Median chunk characters | {statistics.median(t.sizes_fixed or [0]):.0f} "
          f"| {statistics.median(t.sizes_structured or [0]):.0f} |")  # fmt: skip
    print(f"| Course-package raw characters that are duplicate print copies | "
          f"{pct(t.dup_chars_fixed, t.chars_fixed)} | 0% (removed) |")  # fmt: skip


if __name__ == "__main__":
    main()
