"""Byte decoding shared by the text-based loaders (TXT, CSV)."""

from pathlib import Path

from app.ingestion.errors import DocumentDecodeError

# Tried in order. "utf-8-sig" is UTF-8 that also drops a leading byte order mark.
# cp1254 is the Windows Turkish code page, used by files saved with old Windows editors.
ENCODINGS: tuple[str, ...] = ("utf-8-sig", "cp1254")


def decode_bytes(raw: bytes, source: Path) -> tuple[str, str]:
    """Decode with the first encoding in `ENCODINGS` that fits; return the text and its name.

    Raises `DocumentDecodeError` if none fits.
    """
    for encoding in ENCODINGS:
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise DocumentDecodeError(source, f"not decodable as any of {', '.join(ENCODINGS)}")


def encoding_warnings(encoding: str) -> tuple[str, ...]:
    """The warning a loader reports when a file was not UTF-8; empty for UTF-8."""
    if encoding == ENCODINGS[0]:
        return ()
    return (f"decoded as {encoding}, not UTF-8",)
