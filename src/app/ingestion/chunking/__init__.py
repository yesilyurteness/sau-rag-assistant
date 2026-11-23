"""Chunkers turn a loaded document into `TextChunk`s; `metrics` compares chunkers.

`fixed_window` is the v1-like baseline. It stays selectable so step 3 can compare it with the
structure-aware chunkers on the same eval set. Both always receive the same cleaned input.
"""

from app.ingestion.chunking.fixed_window import chunk_fixed_window

__all__ = ["chunk_fixed_window"]
