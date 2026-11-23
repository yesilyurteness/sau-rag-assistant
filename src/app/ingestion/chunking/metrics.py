"""Structural metrics for comparing chunkers before the eval runner exists (step 3).

All functions are pure. The caller supplies the unit boundaries (for example one FAQ
question with its answer, one numbered decision, one course-package section) as the unit
texts; a unit is "kept whole" when one chunk contains all of it. Whitespace is normalized
before comparing, so line breaks a chunker moved do not count as a split.
"""

import re
import statistics
from collections.abc import Sequence
from dataclasses import dataclass

# Chunks shorter than this carry too little context to answer from. A starting value, to be
# revisited with the real files in step 1c-4.
DEFAULT_SMALL_CHUNK = 100

_WHITESPACE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip()


@dataclass(frozen=True, slots=True)
class SizeSummary:
    """Chunk lengths in characters. All zero when there are no chunks."""

    count: int
    minimum: int
    p25: float
    median: float
    p75: float
    maximum: int


@dataclass(frozen=True, slots=True)
class StructuralReport:
    units: int
    units_kept_whole: int
    size: SizeSummary
    empty_chunks: int
    small_chunks: int

    @property
    def kept_whole_ratio(self) -> float:
        """Share of units found complete inside a single chunk; 1.0 when there are no units."""
        return self.units_kept_whole / self.units if self.units else 1.0


def count_units_kept_whole(units: Sequence[str], chunks: Sequence[str]) -> int:
    """How many units appear complete inside at least one chunk."""
    normalized_chunks = [_normalize(chunk) for chunk in chunks]
    return sum(
        1
        for unit in units
        if (target := _normalize(unit)) and any(target in chunk for chunk in normalized_chunks)
    )


def summarize_sizes(chunks: Sequence[str]) -> SizeSummary:
    lengths = sorted(len(chunk) for chunk in chunks)
    if not lengths:
        return SizeSummary(0, 0, 0.0, 0.0, 0.0, 0)
    if len(lengths) == 1:
        only = lengths[0]
        return SizeSummary(1, only, float(only), float(only), float(only), only)
    p25, median, p75 = statistics.quantiles(lengths, n=4, method="inclusive")
    return SizeSummary(len(lengths), lengths[0], p25, median, p75, lengths[-1])


def count_empty(chunks: Sequence[str]) -> int:
    """Chunks with no text other than whitespace."""
    return sum(1 for chunk in chunks if not chunk.strip())


def count_small(chunks: Sequence[str], threshold: int = DEFAULT_SMALL_CHUNK) -> int:
    """Non-empty chunks shorter than `threshold` characters."""
    return sum(1 for chunk in chunks if chunk.strip() and len(chunk.strip()) < threshold)


def structural_report(
    units: Sequence[str], chunks: Sequence[str], small_threshold: int = DEFAULT_SMALL_CHUNK
) -> StructuralReport:
    return StructuralReport(
        units=len(units),
        units_kept_whole=count_units_kept_whole(units, chunks),
        size=summarize_sizes(chunks),
        empty_chunks=count_empty(chunks),
        small_chunks=count_small(chunks, small_threshold),
    )
