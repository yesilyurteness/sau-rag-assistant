"""Ingestion pipeline: manifest -> load -> clean -> chunk -> check -> store, plus the run report.

`process_file` is a pure function of (file bytes, manifest entry). `run` adds discovery and the
idempotent write through a `DocumentStore`, which is a protocol so tests can use an in-memory fake.
"""

import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import Any, Protocol

from app.ingestion import chunking
from app.ingestion.checks import check_chunks, check_pages, check_table, check_text
from app.ingestion.cleaning import base_clean, clean_course_package, strip_markdown_escapes
from app.ingestion.course_package import course_chunks, course_context, parse_course_package
from app.ingestion.loaders import LoadError, load_bytes
from app.ingestion.manifest import Manifest, normalize_name
from app.ingestion.models import (
    PIPELINE_VERSION,
    Chunk,
    Finding,
    LoadedSource,
    ManifestEntry,
    Page,
    ProcessedDocument,
    Severity,
    SourceKind,
    Target,
)

_DECISION_MARKER = re.compile(r"^\d+\.\s")
_PROCEDURE_MARKER = re.compile(r"^(?:\d+(?:[.-]\d+)*-\s|\d+-\d+\s)")


class Outcome(StrEnum):
    INGESTED = "ingested"  # new document written
    UPDATED = "updated"  # content, manifest metadata or pipeline version changed
    UNCHANGED = "unchanged"  # same fingerprint, nothing written
    PROCESSED = "processed"  # dry run: processed, not written
    REJECTED = "rejected"  # processed but has an error finding, not written
    FAILED = "failed"  # could not be read
    SKIPPED = "skipped"  # manifest says skip
    UNREGISTERED = "unregistered"  # not in the manifest


@dataclass
class FileResult:
    name: str
    outcome: Outcome
    document: ProcessedDocument | None = None
    findings: list[Finding] = field(default_factory=list)
    reason: str | None = None

    @property
    def all_findings(self) -> list[Finding]:
        return (self.document.findings if self.document else []) + self.findings


class DocumentStore(Protocol):
    async def get_fingerprint(self, source_name: str) -> str | None:
        """Fingerprint of the active stored document, or None if absent or inactive."""

    async def upsert(self, document: ProcessedDocument, fingerprint: str) -> None:
        """Insert or replace a document and all its chunks in one transaction."""

    async def deactivate_missing(self, keep: set[str], *, prune: bool) -> list[str]:
        """Deactivate (or delete with prune) documents not in `keep`; return their names."""


def fingerprint(document: ProcessedDocument) -> str:
    """Changes when the bytes, the manifest metadata or the pipeline version change."""
    entry = asdict(document.entry)
    payload = json.dumps(
        {"hash": document.content_hash, "pipeline": PIPELINE_VERSION, "entry": entry},
        sort_keys=True,
        default=str,
    )
    return sha256(payload.encode()).hexdigest()


# --- processing a single file --------------------------------------------------------------------


def process_file(path: Path, entry: ManifestEntry, data: bytes) -> ProcessedDocument:
    """Load, clean, chunk and check one file. Raises LoadError if the file cannot be read."""
    loaded = load_bytes(path, data)
    handler = _HANDLERS[entry.kind]
    result = handler(loaded, entry, path)
    findings = list(result.findings)
    if loaded.encoding != "utf-8":
        findings.append(Finding(Severity.INFO, "legacy_encoding", f"decoded as {loaded.encoding}"))
    if result.target is Target.VECTOR:
        findings.extend(check_chunks(result.chunks, chunking.MAX_CHARS + chunking.MIN_CHARS))
    if loaded.pages:
        findings.extend(check_pages(loaded.pages))
    year = result.academic_year
    if not year:
        findings.append(Finding(Severity.WARNING, "missing_academic_year", "no academic year"))
    return ProcessedDocument(
        entry=entry,
        source_type=loaded.source_type,
        target=result.target,
        title=result.title,
        academic_year=year,
        content_hash=sha256(data).hexdigest(),
        raw_chars=len(loaded.text),
        clean_chars=result.clean_chars,
        duplicate_chars_removed=result.duplicate_chars_removed,
        page_count=len(loaded.pages) or None,
        chunks=result.chunks,
        metadata=result.metadata,
        findings=findings,
    )


@dataclass
class _HandlerResult:
    title: str
    target: Target
    chunks: list[Chunk]
    academic_year: str | None
    clean_chars: int = 0
    duplicate_chars_removed: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)


def _title(entry: ManifestEntry, path: Path) -> str:
    return entry.title or path.stem


def _cleaned_pages(pages: list[Page]) -> tuple[list[Page], int, int]:
    out: list[Page] = []
    repaired = pua = 0
    for page in pages:
        result = base_clean(page.text)
        repaired += result.mojibake_repaired
        pua += result.pua_removed
        out.append(Page(page.number, result.text, page.image_count))
    return out, repaired, pua


def _repair_findings(repaired: int) -> list[Finding]:
    if not repaired:
        return []
    return [
        Finding(
            Severity.INFO,
            "mojibake_repaired",
            f"{repaired} characters of broken Turkish encoding repaired (Ġ/ġ/Ģ)",
        )
    ]


def _locate_pages(chunks: list[Chunk], pages: list[Page]) -> list[Chunk]:
    """Best-effort page range for each chunk, by matching its first and last characters."""
    if not pages:
        return chunks

    def squash(text: str) -> str:
        return re.sub(r"\s+|^(Soru|Cevap|Cevap \(devam\)):", "", text)

    page_texts = [(p.number, squash(p.text)) for p in pages]

    def find(snippet: str) -> int | None:
        return next((n for n, t in page_texts if snippet and snippet in t), None)

    out: list[Chunk] = []
    for c in chunks:
        body = squash(re.sub(r"^Soru: .*?\n(Cevap|Cevap \(devam\)): ", "", c.content, flags=re.S))
        start, end = find(body[:25]), find(body[-25:])
        out.append(
            Chunk(c.ordinal, c.section, c.header, c.content, start, end or start, c.metadata)
        )
    return out


def _tabular(loaded: LoadedSource, entry: ManifestEntry, path: Path) -> _HandlerResult:
    table = loaded.table
    assert table is not None  # noqa: S101 - load_csv always sets it
    return _HandlerResult(
        title=_title(entry, path),
        target=Target.SQL,
        chunks=[],
        academic_year=entry.academic_year,
        metadata={"columns": table.header, "row_count": len(table.rows)},
        findings=check_table(table),
    )


def _course(loaded: LoadedSource, entry: ManifestEntry, path: Path) -> _HandlerResult:
    cleaned, meta = clean_course_package(loaded.text)
    findings = check_text(cleaned.text)
    pkg = parse_course_package(cleaned.text)
    if pkg is None:
        findings.append(
            Finding(
                Severity.ERROR,
                "unparsed_course_package",
                "no 'Ders Adı | Kodu | ...' header table; not a course package or a new layout",
            )
        )
        return _HandlerResult(
            _title(entry, path), Target.VECTOR, [], entry.academic_year, len(cleaned.text),
            cleaned.removed_chars, findings=findings,
        )  # fmt: skip

    year = meta.academic_year or entry.academic_year
    if meta.academic_year is None:
        findings.append(
            Finding(
                Severity.WARNING,
                "course_year_not_found",
                f"no '(YYYY - YYYY)' title line; using the manifest year {entry.academic_year}",
            )
        )
    if cleaned.removed_chars == 0:
        findings.append(
            Finding(Severity.INFO, "no_print_copy_removed", "no duplicate flat copy was found")
        )
    findings.extend(pkg.findings)
    findings.extend(_course_findings(pkg.metadata(), pkg))
    chunks = course_chunks(pkg, course_context(pkg, year))
    metadata = {
        **pkg.metadata(),
        "ebs_course_id": meta.ebs_course_id,
        "ebs_printed_at": meta.printed_at,
        "sections": sorted({str(c.metadata.get("course_section")) for c in chunks}),
        "weeks": len(pkg.weekly),
        "outcomes": len(pkg.outcomes),
    }
    return _HandlerResult(
        title=f"{pkg.name} ({pkg.code})",
        target=Target.VECTOR,
        chunks=chunks,
        academic_year=year,
        clean_chars=len(cleaned.text),
        duplicate_chars_removed=cleaned.removed_chars,
        metadata=metadata,
        findings=findings + _repair_findings(cleaned.mojibake_repaired),
    )


def _course_findings(meta: dict[str, Any], pkg: Any) -> list[Finding]:
    findings: list[Finding] = []
    if not meta["course_code"]:
        findings.append(Finding(Severity.WARNING, "missing_course_code", "course code is empty"))
    if not pkg.weekly:
        findings.append(Finding(Severity.WARNING, "no_weekly_plan", "no weekly plan rows parsed"))
    if not pkg.outcomes:
        findings.append(Finding(Severity.INFO, "no_learning_outcomes", "no outcome rows parsed"))
    per_25 = meta.get("workload_hours_div_25")
    try:
        ects = float(str(meta["ects"]).replace(",", "."))
    except ValueError:
        findings.append(Finding(Severity.WARNING, "ects_not_numeric", f"ECTS {meta['ects']!r}"))
        return findings
    if per_25 is not None and abs(per_25 - ects) >= 0.5:
        findings.append(
            Finding(
                Severity.INFO,
                "ects_workload_mismatch",
                f"declared ECTS {meta['ects']} vs workload/25 = {per_25:g}",
            )
        )
    return findings


def _pdf_text_kind(loaded: LoadedSource, entry: ManifestEntry, path: Path) -> _HandlerResult:
    pages, repaired, _ = _cleaned_pages(loaded.pages)
    text = "\n\n".join(p.text for p in pages if p.text)
    ctx = chunking.ChunkContext(title=_title(entry, path), academic_year=entry.academic_year)
    if entry.kind is SourceKind.SLIDES:
        chunks = chunking.chunk_slides(pages, ctx)
    else:
        chunks = _locate_pages(_chunk_text(entry.kind, text, ctx), pages)
    return _HandlerResult(
        title=ctx.title,
        target=Target.VECTOR,
        chunks=chunks,
        academic_year=entry.academic_year,
        clean_chars=len(text),
        findings=check_text(text, expected_year=entry.academic_year) + _repair_findings(repaired),
    )


def _txt_kind(loaded: LoadedSource, entry: ManifestEntry, path: Path) -> _HandlerResult:
    cleaned = base_clean(loaded.text)
    text = cleaned.text
    if entry.kind is SourceKind.ANNOUNCEMENT:
        text = strip_markdown_escapes(text)
    ctx = chunking.ChunkContext(title=_title(entry, path), academic_year=entry.academic_year)
    return _HandlerResult(
        title=ctx.title,
        target=Target.VECTOR,
        chunks=_chunk_text(entry.kind, text, ctx),
        academic_year=entry.academic_year,
        clean_chars=len(text),
        findings=check_text(text, expected_year=entry.academic_year)
        + _repair_findings(cleaned.mojibake_repaired),
    )


def _chunk_text(kind: SourceKind, text: str, ctx: chunking.ChunkContext) -> list[Chunk]:
    if kind is SourceKind.FAQ:
        return chunking.chunk_faq(text, ctx)
    if kind is SourceKind.DECISIONS:
        return chunking.chunk_numbered(
            text,
            ctx,
            _DECISION_MARKER,
            item_label=lambda line: f"Karar {line.split('.', 1)[0]}",
            pack_items=False,
        )
    if kind is SourceKind.PROCEDURE:
        return chunking.chunk_numbered(
            text,
            ctx,
            _PROCEDURE_MARKER,
            item_label=lambda line: f"Adım {re.split(r'[- ]', line, maxsplit=1)[0]}",
            pack_items=True,
        )
    return chunking.chunk_narrative(text, ctx)


def _for_source(
    loaded: LoadedSource, entry: ManifestEntry, path: Path
) -> _HandlerResult:  # pragma: no cover - dispatch only
    if loaded.pages:
        return _pdf_text_kind(loaded, entry, path)
    return _txt_kind(loaded, entry, path)


_Handler = Callable[[LoadedSource, ManifestEntry, Path], _HandlerResult]
_HANDLERS: dict[SourceKind, _Handler] = {
    SourceKind.TABULAR: _tabular,
    SourceKind.COURSE_PACKAGE: _course,
    SourceKind.SLIDES: _pdf_text_kind,
    SourceKind.FAQ: _for_source,
    SourceKind.DECISIONS: _for_source,
    SourceKind.PROCEDURE: _for_source,
    SourceKind.NARRATIVE: _for_source,
    SourceKind.ANNOUNCEMENT: _for_source,
}


# --- running over a folder ---------------------------------------------------------------------


def discover(source_dir: Path) -> list[Path]:
    """Top-level regular files only (sub-folders such as `arsiv/` are ignored), sorted by name."""
    return sorted(
        (p for p in source_dir.iterdir() if p.is_file() and not p.name.startswith(".")),
        key=lambda p: normalize_name(p.name),
    )


@dataclass
class RunResult:
    source_dir: str
    dry_run: bool
    started_at: datetime
    finished_at: datetime
    files: list[FileResult]
    missing: list[str]
    deactivated: list[str]
    pipeline_version: str = PIPELINE_VERSION


async def run(
    source_dir: Path,
    manifest: Manifest,
    store: DocumentStore | None,
    *,
    prune: bool = False,
) -> RunResult:
    """Process every file in `source_dir`; write through `store` unless it is None (dry run)."""
    started = datetime.now(UTC)
    paths = discover(source_dir)
    results: list[FileResult] = []
    keep: set[str] = set()

    for path in paths:
        name = normalize_name(path.name)
        entry = manifest.resolve(name)
        if entry is None:
            results.append(FileResult(name, Outcome.UNREGISTERED))
            continue
        if entry.skipped:
            results.append(FileResult(name, Outcome.SKIPPED, reason=entry.skip_reason))
            continue
        try:
            document = process_file(path, entry, path.read_bytes())
        except LoadError as exc:
            finding = Finding(Severity.ERROR, "load_failed", str(exc))
            results.append(FileResult(name, Outcome.FAILED, findings=[finding]))
            continue

        if any(f.severity is Severity.ERROR for f in document.findings):
            results.append(FileResult(name, Outcome.REJECTED, document))
            continue
        keep.add(name)
        if store is None:
            results.append(FileResult(name, Outcome.PROCESSED, document))
            continue
        fp = fingerprint(document)
        stored = await store.get_fingerprint(name)
        if stored == fp:
            results.append(FileResult(name, Outcome.UNCHANGED, document))
            continue
        await store.upsert(document, fp)
        outcome = Outcome.INGESTED if stored is None else Outcome.UPDATED
        results.append(FileResult(name, outcome, document))

    deactivated = await store.deactivate_missing(keep, prune=prune) if store else []
    return RunResult(
        source_dir=str(source_dir),
        dry_run=store is None,
        started_at=started,
        finished_at=datetime.now(UTC),
        files=results,
        missing=manifest.missing_files({p.name for p in paths}),
        deactivated=deactivated,
    )
