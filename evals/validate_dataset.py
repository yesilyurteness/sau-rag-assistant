"""Validate golden evaluation datasets.

Usage: python -m evals.validate_dataset evals/datasets

Checks:
  - every line parses and matches the EvalItem schema
  - ids are unique across all splits
  - no question appears in both dev and test (split leakage)
"""

import json
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from evals.schema import EvalItem


@dataclass
class Report:
    items: dict[str, list[EvalItem]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _normalize(text: str) -> str:
    """Case/whitespace-insensitive key for duplicate detection (Turkish-aware lowercasing)."""
    text = unicodedata.normalize("NFC", text).replace("I", "ı").replace("İ", "i").lower()
    return " ".join(text.split())


def load_split(path: Path, report: Report) -> list[EvalItem]:
    items: list[EvalItem] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            items.append(EvalItem.model_validate(json.loads(line)))
        except (json.JSONDecodeError, ValidationError) as exc:
            first_error = str(exc).splitlines()[0:3]
            report.errors.append(f"{path.name}:{line_no}: {' | '.join(first_error)}")
    return items


def validate(directory: Path) -> Report:
    report = Report()
    files = sorted(directory.glob("*.jsonl"))
    if not files:
        report.errors.append(f"no .jsonl files in {directory}")
        return report

    for path in files:
        report.items[path.stem] = load_split(path, report)

    id_counts = Counter(item.id for items in report.items.values() for item in items)
    report.errors += [f"duplicate id: {i}" for i, n in id_counts.items() if n > 1]

    dev = {_normalize(i.question) for i in report.items.get("dev", [])}
    test = {_normalize(i.question) for i in report.items.get("test", [])}
    report.errors += [f"question in both dev and test: {q!r}" for q in sorted(dev & test)]
    return report


def main(argv: list[str]) -> int:
    directory = Path(argv[1]) if len(argv) > 1 else Path("evals/datasets")
    report = validate(directory)

    for split, items in report.items.items():
        by_category = Counter(i.category for i in items)
        print(f"{split}: {len(items)} items  {dict(sorted(by_category.items()))}")
    for error in report.errors:
        print(f"ERROR {error}", file=sys.stderr)
    print("OK" if report.ok else f"FAILED ({len(report.errors)} errors)")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
