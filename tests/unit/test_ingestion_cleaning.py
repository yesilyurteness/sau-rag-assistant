import unicodedata

import pytest

from app.ingestion.cleaning import clean_text


def test_turkish_letters_are_kept() -> None:
    text = "Çağrı ŞİMŞEK, ığüşöç İĞÜŞÖÇ"
    assert clean_text(text) == text


def test_decomposed_dotted_i_is_composed() -> None:
    decomposed = "İstatistik"  # "I" + combining dot above, as some PDFs store "İ"
    assert clean_text(decomposed) == "İstatistik"
    assert unicodedata.is_normalized("NFC", clean_text(decomposed))


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("satır 1\r\nsatır 2", "satır 1\nsatır 2"),
        ("satır 1\rsatır 2", "satır 1\nsatır 2"),
    ],
)
def test_line_endings_are_normalized(raw: str, expected: str) -> None:
    assert clean_text(raw) == expected


def test_invisible_characters_are_removed() -> None:
    raw = "﻿Staj​ Yöner­gesi⁠"
    assert clean_text(raw) == "Staj Yönergesi"


def test_control_characters_are_removed() -> None:
    assert clean_text("AKTS\x00 5\x07") == "AKTS 5"


def test_horizontal_whitespace_is_collapsed() -> None:
    raw = "Ders  Adı:\t\tMatematik 1   "
    assert clean_text(raw) == "Ders Adı: Matematik 1"


def test_blank_lines_are_limited_and_edges_stripped() -> None:
    raw = "\n\n  Başlık  \n\n\n\n\nGövde\n\n"
    assert clean_text(raw) == "Başlık\n\nGövde"


def test_single_blank_line_is_kept() -> None:
    assert clean_text("Paragraf 1\n\nParagraf 2") == "Paragraf 1\n\nParagraf 2"


def test_whitespace_only_becomes_empty() -> None:
    assert clean_text(" \t\n​\n ") == ""


def test_cleaning_is_idempotent() -> None:
    raw = "﻿  Staj\t süresi:\r\n\r\n\r\n40  iş günü  "
    once = clean_text(raw)
    assert clean_text(once) == once
