"""Source manifest: which files are part of the corpus and what we know about each.

The manifest (`config/sources.toml`) is the single place where the project owner declares the
document kind, academic year, status and access level. A file that is not listed (explicitly or by a
pattern rule) is reported as unregistered and never ingested.
"""

import fnmatch
import re
import tomllib
import unicodedata
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path
from typing import Any

from app.ingestion.models import DocStatus, ManifestEntry, SourceKind

_YEAR_RE = re.compile(r"^(\d{4})-(\d{4})$")


class ManifestError(ValueError):
    """The manifest file is malformed."""


def normalize_name(name: str) -> str:
    """NFC-normalise a file name (OneDrive/macOS may hand out decomposed Turkish letters)."""
    return unicodedata.normalize("NFC", name)


def validate_academic_year(value: str) -> str:
    match = _YEAR_RE.match(value)
    if not match or int(match.group(2)) != int(match.group(1)) + 1:
        raise ManifestError(f"academic_year must look like '2025-2026', got {value!r}")
    return value


@dataclass(frozen=True)
class Manifest:
    sources: dict[str, ManifestEntry] = field(default_factory=dict)
    patterns: list[ManifestEntry] = field(default_factory=list)  # `name` holds the glob

    def resolve(self, file_name: str) -> ManifestEntry | None:
        """Entry for a file: an exact name wins over a glob pattern; None if unregistered."""
        name = normalize_name(file_name)
        exact = self.sources.get(name)
        if exact is not None:
            return exact
        for pattern in self.patterns:
            if fnmatch.fnmatchcase(name, pattern.name):
                return replace(pattern, name=name)
        return None

    def missing_files(self, present: set[str]) -> list[str]:
        """Explicitly listed, non-skipped sources that are not on disk."""
        names = {normalize_name(n) for n in present}
        return sorted(n for n, e in self.sources.items() if not e.skipped and n not in names)


def _entry(raw: dict[str, Any], defaults: dict[str, Any], *, key: str) -> ManifestEntry:
    merged = {**defaults, **raw}
    name = merged.get(key)
    if not isinstance(name, str) or not name:
        raise ManifestError(f"entry is missing {key!r}: {raw}")
    try:
        kind = SourceKind(merged["kind"])
        status = DocStatus(merged.get("status", DocStatus.CURRENT))
    except (KeyError, ValueError) as exc:
        raise ManifestError(f"{name}: invalid or missing kind/status ({exc})") from exc

    year = merged.get("academic_year")
    if year is not None:
        validate_academic_year(str(year))
    valid_from = merged.get("valid_from")
    valid_until = merged.get("valid_until")
    for label, value in (("valid_from", valid_from), ("valid_until", valid_until)):
        if value is not None and not isinstance(value, date):
            raise ManifestError(f"{name}: {label} must be a TOML date, got {value!r}")
    if valid_from and valid_until and valid_from > valid_until:
        raise ManifestError(f"{name}: valid_from is after valid_until")

    return ManifestEntry(
        name=normalize_name(name),
        kind=kind,
        title=merged.get("title"),
        academic_year=str(year) if year is not None else None,
        status=status,
        access=str(merged.get("access", "public")),
        valid_from=valid_from,
        valid_until=valid_until,
        skip_reason=merged.get("skip"),
        notes=merged.get("notes"),
    )


def parse_manifest(text: str) -> Manifest:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ManifestError(f"invalid TOML: {exc}") from exc

    defaults: dict[str, Any] = data.get("defaults", {})
    sources: dict[str, ManifestEntry] = {}
    for raw in data.get("source", []):
        entry = _entry(raw, defaults, key="name")
        if entry.name in sources:
            raise ManifestError(f"duplicate manifest entry: {entry.name}")
        sources[entry.name] = entry
    patterns = [_entry(raw, defaults, key="glob") for raw in data.get("pattern", [])]
    return Manifest(sources=sources, patterns=patterns)


def load_manifest(path: Path) -> Manifest:
    return parse_manifest(path.read_text(encoding="utf-8"))
