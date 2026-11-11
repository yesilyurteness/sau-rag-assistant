from pathlib import Path

import pytest

from app.ingestion.errors import DocumentDecodeError, EmptyDocumentError, IngestionError
from app.ingestion.loaders import load_txt

SAMPLE = "Ders Adı: İstatistik ve Olasılık 1\nAKTS: 5\nÖn Koşul: Yok"


def _write(tmp_path: Path, data: bytes, name: str = "Ders.txt") -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


def test_utf8_file_is_loaded(tmp_path: Path) -> None:
    path = _write(tmp_path, SAMPLE.encode("utf-8"))

    doc = load_txt(path)

    assert doc.text == SAMPLE
    assert doc.file_type == "txt"
    assert doc.encoding == "utf-8-sig"
    assert doc.source == path
    assert doc.warnings == ()
    assert len(doc.segments) == 1
    assert doc.segments[0].page is None


def test_utf8_bom_is_dropped(tmp_path: Path) -> None:
    path = _write(tmp_path, SAMPLE.encode("utf-8-sig"))

    assert load_txt(path).text == SAMPLE


def test_windows_turkish_file_falls_back_to_cp1254(tmp_path: Path) -> None:
    path = _write(tmp_path, SAMPLE.encode("cp1254"))

    doc = load_txt(path)

    assert doc.text == SAMPLE
    assert doc.encoding == "cp1254"
    assert doc.warnings == ("decoded as cp1254, not UTF-8",)


def test_text_is_cleaned(tmp_path: Path) -> None:
    path = _write(tmp_path, "  AKTS:\t5  \r\n\r\n\r\n\r\nÖn Koşul: Yok \r\n".encode())

    assert load_txt(path).text == "AKTS: 5\n\nÖn Koşul: Yok"


@pytest.mark.parametrize("data", [b"", b"   \r\n\t\n", "﻿".encode()])
def test_empty_file_raises(tmp_path: Path, data: bytes) -> None:
    path = _write(tmp_path, data, name="BolumTanitimi.txt")

    with pytest.raises(EmptyDocumentError) as exc_info:
        load_txt(path)

    assert exc_info.value.source == path
    assert "BolumTanitimi.txt" in str(exc_info.value)


def test_undecodable_file_raises(tmp_path: Path) -> None:
    # 0x81 is invalid as a UTF-8 start byte and undefined in cp1254.
    path = _write(tmp_path, b"AKTS \x81 5")

    with pytest.raises(DocumentDecodeError):
        load_txt(path)


def test_loader_errors_share_a_base_class(tmp_path: Path) -> None:
    path = _write(tmp_path, b"")

    with pytest.raises(IngestionError):
        load_txt(path)
