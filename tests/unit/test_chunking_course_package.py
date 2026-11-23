"""Course-package chunker on made-up text shaped like a cleaned EBS package."""

from app.ingestion.chunking.course_package import (
    DEFAULT_SIZE,
    chunk_course_package,
    course_title,
    is_heading_only,
    table_rows,
)

NL = "\n"
TITLE = "Eğitim Bilgi Sistemi Endüstri Mühendisliği Bölümü Örnek Ders I (2025 - 2026)"
OUTCOMES_HEADER = ["# | Ders Öğrenme Çıktıları | Öğretim Yöntemleri | Ölçme", "Yöntemleri"]
WEEKS_HEADER = "Hafta | Ders Konuları | Ön Hazırlık"


def _outcome(number: int) -> list[str]:
    # One learning outcome spans two lines, like in the real packages.
    return [
        f"{number} | Öğrenci örnek konu {number} hakkındaki temel kavramları açıklayabilir ve",
        f"uygulayabilir ({number}). | Anlatım, Soru-Cevap, Tartışma, | Yazılı Sınav, |",
    ]


IDENTITY = [
    TITLE,
    "Ders Adı | Kodu | Yarıyıl | T+U Saat | Kredi | AKTS",
    "Örnek Ders I | ENM 999 | 3 | 3 + 0 | 3 | 5",
    "Dersin Dili | Türkçe",
    "Dersin Koordinatörü | Dr.Öğr.Üyesi ÖRNEK KİŞİ",
]
OUTCOMES = [*OUTCOMES_HEADER, *_outcome(1), *_outcome(2), *OUTCOMES_HEADER, *_outcome(3)]
WEEKS = [WEEKS_HEADER, "1 | Giriş |", "2 | Olasılık |", WEEKS_HEADER, "3 | Rassal Değişkenler |"]
SOURCES = ["Kaynaklar |", "Ders Notu | Ders notları", "Ders Kaynakları | Örnek Kitap, 2014."]
ASSESSMENT = [
    "Değerlendirme Sistemi | | |",
    "Yarıyıl Çalışmaları | | Katkı Oranı |",
    "1. Ara Sınav | | 50 |",
]
WORKLOAD = [
    "AKTS - İş Yükü Etkinlik | Sayı | Süre (Saat) | Toplam İş Yükü (Saat)",
    "Ara Sınav | 1 | 10 | 10",
    "Toplam İş Yükü / 25 (Saat) | | | 6,08",
    "dersAKTSKredisi | | | 5",
]
PACKAGE = [
    *IDENTITY,
    "Dersin Amacı | Örnek dersin amacı.",
    "Dersin İçeriği | Örnek içerik.",
    *OUTCOMES,
    *WEEKS,
    *SOURCES,
    *ASSESSMENT,
    *WORKLOAD,
]
TEXT = "\n".join(PACKAGE)


def test_default_size_is_1500() -> None:
    assert DEFAULT_SIZE == 1500


def test_one_chunk_per_section_in_reading_order() -> None:
    result = chunk_course_package(TEXT)

    assert [chunk.section for chunk in result.chunks] == [
        "Künye",
        "Dersin Amacı",
        "Dersin İçeriği",
        "Ders Öğrenme Çıktıları",
        "Haftalık Konular",
        "Kaynaklar",
        "Değerlendirme Sistemi",
        "AKTS - İş Yükü",
    ]
    assert [chunk.position for chunk in result.chunks] == list(range(8))
    assert all(chunk.page is None for chunk in result.chunks)
    assert result.warnings == ()


def test_identity_chunk_holds_the_title_and_short_fields() -> None:
    identity = chunk_course_package(TEXT).chunks[0]

    assert identity.text == "\n".join(IDENTITY)


def test_workload_table_is_one_chunk_with_ects_and_workload_together() -> None:
    workload = chunk_course_package(TEXT).chunks[-1]

    assert workload.text == "\n".join(WORKLOAD)
    assert "6,08" in workload.text and "dersAKTSKredisi | | | 5" in workload.text


def test_header_repeated_at_a_page_top_is_dropped() -> None:
    weeks = chunk_course_package(TEXT).chunks[4]

    assert weeks.text == "\n".join(
        [WEEKS_HEADER, "1 | Giriş |", "2 | Olasılık |", "3 | Rassal Değişkenler |"]
    )


def test_table_rows_span_lines_until_the_next_number() -> None:
    rows = table_rows(OUTCOMES)

    assert rows == [
        "\n".join(OUTCOMES_HEADER),
        "\n".join(_outcome(1)),
        "\n".join(_outcome(2)),
        "\n".join(_outcome(3)),
    ]


def test_long_table_is_split_at_row_starts_with_the_header_repeated() -> None:
    size = 400
    chunks = [
        c
        for c in chunk_course_package(TEXT, size=size).chunks
        if c.section == "Ders Öğrenme Çıktıları"
    ]

    assert len(chunks) == 2
    first, second = (chunk.text for chunk in chunks)
    assert first == "\n".join([*OUTCOMES_HEADER, *_outcome(1), *_outcome(2)])
    assert second == "\n".join([*OUTCOMES_HEADER, *_outcome(3)])
    assert all(len(chunk.text) <= size for chunk in chunks)
    # Every learning outcome stays whole: its number and its continuation line together.
    for number in (1, 2, 3):
        assert sum("\n".join(_outcome(number)) in chunk.text for chunk in chunks) == 1


def test_continuation_chunk_is_not_a_contiguous_slice_of_the_source() -> None:
    # No page-top header before outcome 3 here, so the repeated header is really added.
    outcomes = [*OUTCOMES_HEADER, *_outcome(1), *_outcome(2), *_outcome(3)]
    text = NL.join([*IDENTITY, *outcomes, *WORKLOAD])

    chunks = [
        c
        for c in chunk_course_package(text, size=400).chunks
        if c.section == "Ders Öğrenme Çıktıları"
    ]

    assert len(chunks) == 2
    assert chunks[0].text in text  # the first chunk is a plain slice of the source
    assert chunks[1].text == NL.join([*OUTCOMES_HEADER, *_outcome(3)])
    assert chunks[1].text not in text  # header + a later row: built, not sliced


def test_other_sections_split_only_at_line_starts_without_a_header() -> None:
    sources = [
        "Kaynaklar |",
        *[f"Kaynak {i} | Yazar {i}, Örnek Kitap Başlığı {i}, 2014." for i in range(1, 9)],
    ]
    text = "\n".join([*IDENTITY, *sources, *WORKLOAD])

    chunks = [c for c in chunk_course_package(text, size=150).chunks if c.section == "Kaynaklar"]

    assert len(chunks) > 1
    assert "\n".join(chunk.text for chunk in chunks) == "\n".join(sources)
    assert all(len(chunk.text) <= 150 for chunk in chunks)


def test_workload_table_over_the_size_is_kept_whole_with_a_warning() -> None:
    result = chunk_course_package(TEXT, size=60)

    workload = [c for c in result.chunks if c.section == "AKTS - İş Yükü"]
    assert [c.text for c in workload] == ["\n".join(WORKLOAD)]
    assert any(
        w.startswith("AKTS - İş Yükü is ") and w.endswith("kept whole") for w in result.warnings
    )


def test_a_single_line_longer_than_the_size_stays_whole_with_a_warning() -> None:
    long_line = "Dersin İçeriği | " + "uzun içerik " * 30
    text = "\n".join([*IDENTITY, long_line, *WORKLOAD])

    result = chunk_course_package(text, size=200)

    content = [c for c in result.chunks if c.section == "Dersin İçeriği"]
    assert [c.text for c in content] == [long_line]
    assert any(w.startswith("Dersin İçeriği has a line or row of") for w in result.warnings)


def test_assessment_without_its_heading_starts_at_semester_work() -> None:
    text = "\n".join([*IDENTITY, *ASSESSMENT[1:], *WORKLOAD])

    sections = [c.section for c in chunk_course_package(text).chunks]

    assert sections == ["Künye", "Değerlendirme Sistemi", "AKTS - İş Yükü"]


def test_course_title_is_name_and_code() -> None:
    assert course_title(TEXT) == "Örnek Ders I (ENM 999)"


def test_course_title_is_none_without_the_identity_table() -> None:
    assert course_title("Dersin Amacı | Örnek") is None
    assert course_title("Ders Adı | Kodu | Yarıyıl\n | | 3") is None


# --- sections that are empty in the source (decision after 1c-4b)

EMPTY_SECTIONS = [
    "Dersin Amacı |",
    "Dersin İçeriği |",
    *OUTCOMES_HEADER,
    WEEKS_HEADER,
    WEEKS_HEADER,  # the page-top repeat of an empty table
    "Kaynaklar |",
    "Ders Notu |",
    "Kaynaklar |",
    "Ders Kaynakları |",
    "AKTS - İş Yükü Etkinlik | Sayı | Süre (Saat) | Toplam İş Yükü (Saat)",
]


def test_heading_only_sections_get_no_chunk_and_are_counted() -> None:
    result = chunk_course_package(NL.join([*IDENTITY, *EMPTY_SECTIONS]))

    assert [chunk.section for chunk in result.chunks] == ["Künye"]
    assert result.warnings == ("skipped 6 sections that are empty in the source",)
    assert [chunk.position for chunk in result.chunks] == [0]


def test_short_sections_with_real_content_stay() -> None:
    short = [
        "Dersin Amacı | Ergonomi.",
        "Dersin İçeriği | Ölçme ve birim sistemleri.",
        "Kaynaklar |",
        "Ders Notu | Ders notları",
    ]

    result = chunk_course_package(NL.join([*IDENTITY, *short]))

    assert [chunk.section for chunk in result.chunks] == [
        "Künye",
        "Dersin Amacı",
        "Dersin İçeriği",
        "Kaynaklar",
    ]
    assert result.warnings == ()


def test_a_zero_total_row_is_content_not_a_heading() -> None:
    # Two real packages have an assessment table with only "Toplam | 0" rows. By the
    # decision's definition (headings, sub-headings and table headers only) that is a row.
    assessment = ["Değerlendirme Sistemi |", "Yarıyıl Çalışmaları | Katkı Oranı", "Toplam | 0"]

    assert not is_heading_only("Değerlendirme Sistemi", assessment)
    assert is_heading_only("Değerlendirme Sistemi", assessment[:2])


def test_identity_is_never_heading_only() -> None:
    assert not is_heading_only("Künye", IDENTITY)
