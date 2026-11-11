"""CLI: `python -m app.ingestion --source-dir data/raw/v1-kaynaklar [--dry-run] [--prune]`."""

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import get_settings
from app.ingestion.manifest import load_manifest
from app.ingestion.models import Severity
from app.ingestion.pipeline import RunResult, run
from app.ingestion.report import render_markdown, to_json
from app.storage.db import create_engine
from app.storage.documents import SqlDocumentStore


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m app.ingestion", description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=Path("config/sources.toml"))
    parser.add_argument("--report-dir", type=Path, default=Path("data/processed/reports"))
    parser.add_argument("--dry-run", action="store_true", help="process and report, no database")
    parser.add_argument("--prune", action="store_true", help="delete documents no longer present")
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> RunResult:
    manifest = load_manifest(args.manifest)
    if args.dry_run:
        return await run(args.source_dir, manifest, None)

    engine = create_engine(get_settings())
    try:
        store = SqlDocumentStore(engine)
        return await run(args.source_dir, manifest, store, prune=args.prune)
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if not args.source_dir.is_dir():
        print(f"source folder not found: {args.source_dir}", file=sys.stderr)
        return 2
    result = asyncio.run(_run(args))
    args.report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    md_path = args.report_dir / f"ingestion-{stamp}.md"
    md_path.write_text(render_markdown(result), encoding="utf-8")
    (args.report_dir / f"ingestion-{stamp}.json").write_text(to_json(result), encoding="utf-8")
    errors = sum(1 for r in result.files for f in r.all_findings if f.severity is Severity.ERROR)
    print(f"report: {md_path}")
    print(f"files: {len(result.files)}, errors: {errors}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
