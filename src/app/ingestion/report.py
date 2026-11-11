"""Render a pipeline run as a Markdown report (for review) and JSON (for diffs between runs)."""

import json
import statistics
from collections import Counter
from typing import Any

from app.ingestion.models import Severity, SourceKind, Target
from app.ingestion.pipeline import FileResult, Outcome, RunResult

_SEVERITY_ORDER = {Severity.ERROR: 0, Severity.WARNING: 1, Severity.INFO: 2}


def _sizes(results: list[FileResult]) -> list[int]:
    return [c.char_count for r in results if r.document for c in r.document.chunks]


def _dist(sizes: list[int]) -> str:
    if not sizes:
        return "n/a"
    if len(sizes) == 1:
        return str(sizes[0])
    q = statistics.quantiles(sizes, n=10, method="inclusive")
    return f"min {min(sizes)} / p10 {q[0]:.0f} / median {statistics.median(sizes):.0f} / p90 {q[8]:.0f} / max {max(sizes)}"  # noqa: E501


def render_markdown(run: RunResult) -> str:
    files = run.files
    outcomes = Counter(r.outcome for r in files)
    processed = [r for r in files if r.document is not None]
    stored = [r for r in processed if r.outcome is not Outcome.REJECTED]
    sizes = _sizes(stored)
    severities = Counter(f.severity for r in files for f in r.all_findings)

    lines = [
        "# Ingestion report",
        "",
        f"- Run: {run.started_at:%Y-%m-%d %H:%M} UTC, {(run.finished_at - run.started_at).total_seconds():.1f} s",  # noqa: E501
        f"- Source folder: `{run.source_dir}`",
        f"- Mode: {'dry run (nothing written)' if run.dry_run else 'database write'}",
        f"- Pipeline version: {run.pipeline_version}",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Files in folder | {len(files)} |",
    ]
    lines += [f"| {o.value} | {outcomes[o]} |" for o in Outcome if outcomes[o]]
    lines += [
        f"| Chunks (stored or processed) | {len(sizes)} |",
        f"| Chunk size, characters | {_dist(sizes)} |",
        f"| Findings | {severities[Severity.ERROR]} error, {severities[Severity.WARNING]} warning, {severities[Severity.INFO]} info |",  # noqa: E501
        "",
        "## By kind",
        "",
        "| Kind | Files | Chunks | Chunk size (characters) |",
        "|---|---|---|---|",
    ]
    by_kind: dict[SourceKind, list[FileResult]] = {}
    for r in stored:
        assert r.document is not None  # noqa: S101
        by_kind.setdefault(r.document.entry.kind, []).append(r)
    for kind, group in sorted(by_kind.items()):
        lines.append(
            f"| {kind.value} | {len(group)} | {len(_sizes(group))} | {_dist(_sizes(group))} |"
        )

    problems = sorted(
        ((f, r.name) for r in files for f in r.all_findings if f.severity is not Severity.INFO),
        key=lambda x: (_SEVERITY_ORDER[x[0].severity], x[1]),
    )
    lines += ["", "## Errors and warnings", ""]
    lines += [f"- **{f.severity.value}** `{n}`: {f.code}: {f.message}" for f, n in problems]
    if not problems:
        lines.append("None.")

    lines += [
        "",
        "## Documents",
        "",
        "| File | Kind | Year | Status | Outcome | Chars raw → clean | Duplicate removed | Chunks | Findings |",  # noqa: E501
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in processed:
        d = r.document
        assert d is not None  # noqa: S101
        codes = ", ".join(sorted({f.code for f in d.findings})) or "-"
        target = "SQL" if d.target is Target.SQL else str(len(d.chunks))
        lines.append(
            f"| {r.name} | {d.entry.kind.value} | {d.academic_year or '-'} "
            f"| {d.entry.status.value} "
            f"| {r.outcome.value} | {d.raw_chars} → {d.clean_chars} | {d.duplicate_chars_removed} "
            f"| {target} | {codes} |"
        )

    courses = [
        r for r in processed if r.document and r.document.entry.kind is SourceKind.COURSE_PACKAGE
    ]
    if courses:
        lines += [
            "",
            "## Course packages (review these)",
            "",
            "| File | Code | ECTS | Workload/25 | Year | Weeks | Outcomes | Sections | Chunks |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for r in courses:
            d = r.document
            assert d is not None  # noqa: S101
            m = d.metadata
            lines.append(
                f"| {r.name} | {m.get('course_code', '-')} | {m.get('ects', '-')} "
                f"| {m.get('workload_hours_div_25') or '-'} | {d.academic_year or '-'} "
                f"| {m.get('weeks', '-')} | {m.get('outcomes', '-')} "
                f"| {len(m.get('sections', []))} | {len(d.chunks)} |"
            )

    def listing(title: str, items: list[str]) -> None:
        lines.extend(["", f"## {title}", ""])
        lines.extend([f"- `{i}`" for i in items] or ["None."])

    listing("Unregistered files (not in config/sources.toml, ignored)",
            [r.name for r in files if r.outcome is Outcome.UNREGISTERED])  # fmt: skip
    listing("Skipped by the manifest",
            [f"{r.name}: {r.reason}" for r in files if r.outcome is Outcome.SKIPPED])  # fmt: skip
    listing("Listed in the manifest but not in the folder", run.missing)
    listing("Deactivated (no longer in the source set)", run.deactivated)
    return "\n".join(lines) + "\n"


def to_json(run: RunResult) -> str:
    def doc(r: FileResult) -> dict[str, Any]:
        d = r.document
        out: dict[str, Any] = {
            "name": r.name,
            "outcome": r.outcome.value,
            "reason": r.reason,
            "findings": [
                {"severity": f.severity.value, "code": f.code, "message": f.message}
                for f in r.all_findings
            ],
        }
        if d is not None:
            out |= {
                "kind": d.entry.kind.value,
                "academic_year": d.academic_year,
                "status": d.entry.status.value,
                "target": d.target.value,
                "content_hash": d.content_hash,
                "raw_chars": d.raw_chars,
                "clean_chars": d.clean_chars,
                "duplicate_chars_removed": d.duplicate_chars_removed,
                "chunks": [
                    {"ordinal": c.ordinal, "section": c.section, "chars": c.char_count}
                    for c in d.chunks
                ],
                "metadata": d.metadata,
            }
        return out

    payload = {
        "source_dir": run.source_dir,
        "dry_run": run.dry_run,
        "pipeline_version": run.pipeline_version,
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat(),
        "files": [doc(r) for r in run.files],
        "missing": run.missing,
        "deactivated": run.deactivated,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)
