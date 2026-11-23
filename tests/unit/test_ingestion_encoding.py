from pathlib import Path

import pytest

from app.ingestion.encoding import ENCODINGS, decode_bytes, encoding_warnings
from app.ingestion.errors import DocumentDecodeError

SOURCE = Path("Ders.csv")
SAMPLE = "Dönem;Kodu;Ders\n1. Yarıyıl;MAT 111;Matematik 1\nĞ ğ İ ı Ş ş"


def test_utf8_is_tried_first() -> None:
    assert ENCODINGS[0] == "utf-8-sig"
    assert decode_bytes(SAMPLE.encode("utf-8"), SOURCE) == (SAMPLE, "utf-8-sig")


def test_utf8_bom_is_dropped() -> None:
    assert decode_bytes(SAMPLE.encode("utf-8-sig"), SOURCE) == (SAMPLE, "utf-8-sig")


def test_windows_turkish_falls_back_to_cp1254() -> None:
    assert decode_bytes(SAMPLE.encode("cp1254"), SOURCE) == (SAMPLE, "cp1254")


def test_undecodable_bytes_raise_with_the_source() -> None:
    # 0x81 is invalid as a UTF-8 start byte and undefined in cp1254.
    with pytest.raises(DocumentDecodeError) as exc_info:
        decode_bytes(b"AKTS \x81 5", SOURCE)

    assert exc_info.value.source == SOURCE
    assert "utf-8-sig, cp1254" in str(exc_info.value)


def test_no_warning_for_utf8() -> None:
    assert encoding_warnings("utf-8-sig") == ()


def test_warning_for_a_fallback_encoding() -> None:
    assert encoding_warnings("cp1254") == ("decoded as cp1254, not UTF-8",)
