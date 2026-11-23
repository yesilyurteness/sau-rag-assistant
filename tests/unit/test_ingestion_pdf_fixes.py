from pathlib import Path

import pytest
from pdfplumber.page import Page

from app.ingestion.errors import EmptyDocumentError
from app.ingestion.loaders import load_pdf
from app.ingestion.loaders.pdf import (
    convert_leading_glyphs,
    count_private_use,
    remove_lone_glyph_lines,
    repair_turkish_letters,
)

SAMPLE = Path(__file__).parents[1] / "fixtures" / "ingestion" / "ornek_yonerge.pdf"
GLYPH = "\uf0a2"  # bullet glyph seen in StajBilgilendirmeSunumu1.pdf
OTHER_GLYPH = "\uf0b7"  # bullet glyph seen in the Ara Dönem PDF


# --- broken Turkish letters


def test_broken_turkish_letters_are_repaired() -> None:
    text, fixed = repair_turkish_letters("ÖNEMLĠ BĠLGĠLER\nĠġLEMLER ġubat\niĢletme Ģekilde")

    assert text == "ÖNEMLİ BİLGİLER\nİŞLEMLER Şubat\nişletme şekilde"
    assert fixed == 8


def test_text_without_broken_letters_is_unchanged() -> None:
    text = "İşletme ŞUBAT ğ Ğ ı İ"

    assert repair_turkish_letters(text) == (text, 0)


def test_unmeasured_letter_g_cedilla_is_left_alone() -> None:
    # ģ was not seen in the real files, so it is not part of the mapping.
    assert repair_turkish_letters("ģ") == ("ģ", 0)


# --- lines holding only a bullet glyph


def test_lone_glyph_lines_are_removed() -> None:
    text = f"Atölye Stajı, 4. yarıyıl\n{GLYPH}\nÜretim Stajı\n  {GLYPH} \nyapılabilir."

    assert remove_lone_glyph_lines(text) == (
        "Atölye Stajı, 4. yarıyıl\nÜretim Stajı\nyapılabilir.",
        2,
    )


def test_removing_a_lone_glyph_line_leaves_at_most_one_blank_line() -> None:
    text, removed = remove_lone_glyph_lines(f"gerçekleştirilecektir.\n\n{GLYPH}\n\nSTAJ")

    assert text == "gerçekleştirilecektir.\n\nSTAJ"
    assert removed == 1


def test_page_of_only_a_glyph_becomes_empty() -> None:
    assert remove_lone_glyph_lines(GLYPH) == ("", 1)


def test_line_of_two_glyphs_is_not_a_lone_glyph_line() -> None:
    text = f"{GLYPH}{GLYPH}"

    assert remove_lone_glyph_lines(text) == (text, 0)


def test_text_without_lone_glyphs_is_unchanged() -> None:
    text = "Staj\n\n•X işletmesinde stajımı yapmam uygun olur mu?"

    assert remove_lone_glyph_lines(text) == (text, 0)


# --- glyph at the start of a line with text


def test_leading_glyph_becomes_a_dash_bullet() -> None:
    text = f"{OTHER_GLYPH} Başvuru yapılır.\n{OTHER_GLYPH}Belge yüklenir.\nSon satır"

    assert convert_leading_glyphs(text) == (
        "- Başvuru yapılır.\n- Belge yüklenir.\nSon satır",
        2,
    )


def test_glyph_inside_a_line_is_not_converted() -> None:
    text = f"Adım 1 {OTHER_GLYPH} Adım 2"

    assert convert_leading_glyphs(text) == (text, 0)


def test_ordinary_bullet_character_is_not_touched() -> None:
    # U+2022, used by StajSSS.pdf, is a real character, not a private-use glyph.
    text = "•X işletmesinde stajımı yapmam uygun olur mu?"

    assert convert_leading_glyphs(text) == (text, 0)


def test_private_use_glyphs_are_counted() -> None:
    assert count_private_use(f"a {GLYPH} b {OTHER_GLYPH} c") == 2
    assert count_private_use("• düz metin") == 0


# --- fixes inside load_pdf


def _patch_page_text(monkeypatch: pytest.MonkeyPatch, pages: dict[int, str]) -> None:
    def fake_extract_text(self: Page, **kwargs: object) -> str:
        return pages.get(self.page_number, "")

    monkeypatch.setattr(Page, "extract_text", fake_extract_text)


def test_load_pdf_applies_the_fixes_and_reports_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_page_text(
        monkeypatch,
        {
            1: f"ÖNEMLĠ BĠLGĠLER\nAtölye Stajı\n{GLYPH}\n{OTHER_GLYPH} Başvuru yapılır.",
            2: GLYPH,
            3: f"Adım 1 {OTHER_GLYPH} Adım 2 iĢletme",
        },
    )

    doc = load_pdf(SAMPLE)

    assert [segment.page for segment in doc.segments] == [1, 3]
    assert doc.segments[0].text == "ÖNEMLİ BİLGİLER\nAtölye Stajı\n- Başvuru yapılır."
    assert doc.segments[1].text == f"Adım 1 {OTHER_GLYPH} Adım 2 işletme"
    assert doc.warnings == (
        "page 2: no text (possibly scanned)",
        "fixed 4 broken Turkish characters",
        "removed 2 lines holding only a bullet glyph",
        "converted 1 bullet glyphs at line start to '- '",
        "1 private-use characters left inside lines",
    )


def test_load_pdf_reports_nothing_when_no_fix_applies() -> None:
    assert load_pdf(SAMPLE).warnings == ("page 2: no text (possibly scanned)",)


def test_pdf_of_only_lone_glyphs_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_page_text(monkeypatch, {1: GLYPH, 2: GLYPH, 3: GLYPH})

    with pytest.raises(EmptyDocumentError):
        load_pdf(SAMPLE)
