from app.ingestion.cleaning import (
    base_clean,
    clean_course_package,
    normalize_whitespace,
    repair_mojibake,
    strip_markdown_escapes,
)


def test_repairs_broken_turkish_font_encoding() -> None:
    text, fixed = repair_mojibake("ÖNEMLĠ BĠLGĠLER: ġubat tatilinde iĢletmede staj yapılamaz.")

    assert text == "ÖNEMLİ BİLGİLER: Şubat tatilinde işletmede staj yapılamaz."
    assert fixed == 5


def test_leading_private_use_glyph_becomes_bullet_and_icon_lines_disappear() -> None:
    raw = " Staj süresi yirmi iş günüdür\n  \nMetin devam"

    result = base_clean(raw)

    assert result.text == "- Staj süresi yirmi iş günüdür\n\nMetin devam"
    assert result.pua_removed == 5


def test_normalize_whitespace_collapses_blank_lines_and_crlf() -> None:
    assert normalize_whitespace("a  b \r\n\r\n\r\n c\xa0d ") == "a b\n\nc d"


def test_strip_markdown_escapes() -> None:
    assert (
        strip_markdown_escapes(r"ORT \> 2.00 \*\*Not\! 1\. madde") == "ORT > 2.00 **Not! 1. madde"
    )


def test_course_package_drops_flat_print_copies_and_reads_metadata(fixtures) -> None:  # type: ignore[no-untyped-def]
    raw = (fixtures / "Ornek Planlama.txt").read_text(encoding="utf-8")

    result, meta = clean_course_package(raw)

    assert meta.academic_year == "2025-2026"
    assert meta.title == "Örnek Planlama"
    assert meta.ebs_course_id == "123456"
    assert meta.printed_at == "30.11.2025 16:02"
    assert result.removed_chars > 0
    assert "Eğitim Bilgi Sistemi" not in result.text  # stamps, titles and footers are gone
    assert "ebs.sakarya.edu.tr" not in result.text
    assert "2/" not in result.text.split("\n")
    assert result.text.count("Ders Adı | Kodu") == 1  # only the pipe-table copy remains


def test_course_package_keeps_text_when_a_flat_copy_has_no_footer() -> None:
    raw = (
        "Ders Adı | Kodu | Yarıyıl | T+U Saat | Kredi | AKTS\n"
        "30.11.2025 16:02 Eğitim Bilgi Sistemi\nMetin"
    )

    result, _ = clean_course_package(raw)

    assert "Metin" in result.text
    assert result.removed_chars == 0
