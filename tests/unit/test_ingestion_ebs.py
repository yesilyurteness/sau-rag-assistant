"""EBS cleanup on made-up text that imitates the real course-package layout."""

import pytest

from app.ingestion.ebs import (
    ROW_CLOSE,
    ROW_OPEN,
    NotAnEbsPrintoutError,
    clean_ebs,
    find_title,
    is_layout_line,
    rejoin_wrapped_row,
    skip_section,
    split_copies,
    title_academic_year,
    word_loss,
)

ICON = chr(0xEDDB)  # page and table header icon
TOOLBAR = chr(0xE606)  # three toolbar icons under the title (flat copy only)
TIMESTAMP = "30.11.2025 16:02 Eğitim Bilgi Sistemi"
TITLE = "Eğitim Bilgi Sistemi Endüstri Mühendisliği Bölümü Örnek Ders (2025 - 2026)"


def _url(page: int, pages: int) -> str:
    return f"https://ebs.sakarya.edu.tr/Ders/Detay/1?dil=tr&yazdir=true {page}/{pages}"


PAGE_1_TABLE = [
    ICON,
    "1/",
    "|",
    "Ders Adı | Kodu | Yarıyıl | T+U Saat | Kredi | AKTS",
    "Örnek Ders | ENM 999 | 3 | 3 + 0 | 3 | 5",
    "Hafta | Ders Konuları | Ön Hazırlık",
    "1 | Giriş |",
    "2 | Olasılık |",
    "Sıra | Program Çıktıları | Katkı Düzeyi | | | |",
    "| | 1 | 2 | 3 | 4 | 5",
    "1 a | Matematik bilgisi. | | | | |",
]
PAGE_1_FLAT = [
    ICON,
    TITLE,
    f"{TOOLBAR} {TOOLBAR} {TOOLBAR}",
    "Ders Adı Kodu Yarıyıl T+U Saat Kredi AKTS",
    "Örnek Ders ENM 999 3 3 + 0 3 5",
    "Hafta Ders Konuları Ön Hazırlık",
    "1 Giriş",
    "2 Olasılık",
    f"Katkı Düzeyi {ICON}",
    "Sıra Program Çıktıları",
    "1 2 3 4 5",
    "1 a Matematik bilgisi.",
]
# The program outcomes table continues on page 2, then the assessment table follows.
PAGE_2_TABLE = [
    "| | 2/ |",
    "3 | Tasarlama becerisi. | | X | | |",
    "Değerlendirme Sistemi | | |",
    "Yarıyıl Çalışmaları | | Katkı Oranı |",
    "1. Ara Sınav | | 50 |",
    f"{ROW_OPEN}1. Y | ıl İçinin Başarıya | 50 | {ROW_CLOSE}",
    f"{ROW_OPEN} | | {ROW_CLOSE}",
    f"{ROW_OPEN}AK | TS - İş Yükü Etkinlik | Sayı | Süre (Saat) | {ROW_CLOSE}",
    "Ara Sınav | 1 | 10 | 10",
    "dersAKTSKredisi | | | 5",
]
PAGE_2_FLAT = [
    "3 X",
    "Tasarlama becerisi.",
    "Değerlendirme Sistemi",
    "Yarıyıl Çalışmaları Katkı Oranı",
    "1. Ara Sınav 50",
    f"{ROW_OPEN}1. Yıl İçinin Başarıya 50 {ROW_CLOSE}",
    f"{ROW_OPEN}AKTS - İş Yükü Etkinlik Sayı Süre (Saat) {ROW_CLOSE}",
    "Ara Sınav 1 10 10",
    "dersAKTSKredisi 5",
]


def _printout(page_2_flat: list[str] = PAGE_2_FLAT, page_1_flat: list[str] = PAGE_1_FLAT) -> str:
    lines = [*PAGE_1_TABLE, TIMESTAMP, *page_1_flat, _url(1, 2)]
    lines += [*PAGE_2_TABLE, TIMESTAMP, *page_2_flat, _url(2, 2)]
    return "\n".join(lines)


def test_result_is_the_title_and_the_cleaned_table_copy() -> None:
    result = clean_ebs(_printout())

    assert result.text.split("\n") == [
        TITLE,
        "Ders Adı | Kodu | Yarıyıl | T+U Saat | Kredi | AKTS",
        "Örnek Ders | ENM 999 | 3 | 3 + 0 | 3 | 5",
        "Hafta | Ders Konuları | Ön Hazırlık",
        "1 | Giriş |",
        "2 | Olasılık |",
        "Değerlendirme Sistemi | | |",
        "Yarıyıl Çalışmaları | | Katkı Oranı |",
        "1. Ara Sınav | | 50 |",
        "1. Yıl İçinin Başarıya | 50 |",
        "AKTS - İş Yükü Etkinlik | Sayı | Süre (Saat) |",
        "Ara Sınav | 1 | 10 | 10",
        "dersAKTSKredisi | | | 5",
    ]
    assert result.title == TITLE
    assert result.academic_year == "2025-2026"
    assert result.word_loss == 0.0


def test_changes_are_reported_as_warnings() -> None:
    # Layout lines: the icon, "1/", "|" and the empty wrapped row; "| | 2/ |" falls inside
    # the program outcomes section that crosses the page, so it is skipped with it.
    assert clean_ebs(_printout()).warnings == (
        "kept the table copy; removed 4 layout lines",
        "removed 7 private-use glyphs",
        "rejoined 2 words split inside a collapsible row",
        "skipped the program outcomes section (1 rows with a mark)",
    )


def test_word_loss_above_two_percent_is_reported() -> None:
    extra = "Bu cümle yalnızca düz kopyada geçiyor ve tablo kopyasında hiç yok."
    result = clean_ebs(_printout(page_2_flat=[*PAGE_2_FLAT, extra]))

    assert result.word_loss > 0.02
    assert result.warnings[-1].endswith("of the flat copy's words are missing from the table copy")
    assert "Bu cümle" not in result.text  # no automatic filling from the flat copy


def test_missing_title_is_reported() -> None:
    result = clean_ebs(_printout(page_1_flat=[line for line in PAGE_1_FLAT if line != TITLE]))

    assert (result.title, result.academic_year) == (None, None)
    assert "no EBS title line, academic year unknown" in result.warnings
    assert result.text.startswith("Ders Adı | Kodu")


@pytest.mark.parametrize(
    "text",
    ["Düz bir metin, EBS değil.", f"satır\n{TIMESTAMP}\nsatır"],
    ids=["no-page-lines", "timestamp-without-url"],
)
def test_text_without_the_ebs_page_structure_is_rejected(text: str) -> None:
    with pytest.raises(NotAnEbsPrintoutError):
        clean_ebs(text)


def test_copies_are_separated_page_by_page() -> None:
    copies = split_copies(_printout())

    assert copies.table == (*PAGE_1_TABLE, *PAGE_2_TABLE)
    assert copies.flat == (*PAGE_1_FLAT, *PAGE_2_FLAT)


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        (
            f"{ROW_OPEN}1. Y | ıl İçinin Başarıya | 50 | {ROW_CLOSE}",
            "1. Yıl İçinin Başarıya | 50 | ",
        ),
        (
            f"{ROW_OPEN}AK | TS - İş Yükü Etkinlik | Sayı | {ROW_CLOSE}",
            "AKTS - İş Yükü Etkinlik | Sayı | ",
        ),
    ],
    ids=["yil", "akts"],
)
def test_the_two_real_split_words_are_rejoined(line: str, expected: str) -> None:
    assert rejoin_wrapped_row(line) == (expected, 1)


@pytest.mark.parametrize(
    "line",
    [
        f"{ROW_OPEN} | Toplam | 100 | {ROW_CLOSE}",  # the row starts with an empty cell
        f"{ROW_OPEN}Yarıyıl Çalışmaları | Katkı Oranı | {ROW_CLOSE}",  # a long first cell
        f"{ROW_OPEN}1. Final | 50 | {ROW_CLOSE}",  # second cell is a number
    ],
    ids=["empty-first-cell", "long-first-cell", "number-cell"],
)
def test_real_cell_boundaries_in_wrapped_rows_stay(line: str) -> None:
    rejoined, count = rejoin_wrapped_row(line)

    assert count == 0
    assert rejoined == line.replace(ROW_OPEN, "").replace(ROW_CLOSE, "")


def test_rows_outside_the_glyphs_are_never_rejoined() -> None:
    assert rejoin_wrapped_row("AK | TS - İş Yükü") == ("AK | TS - İş Yükü", 0)


@pytest.mark.parametrize(
    ("line", "layout"),
    [
        (ICON, True),
        ("1/", True),
        ("| | 2/ |", True),
        ("| | | | |", True),
        (f"{ROW_OPEN} | | {ROW_CLOSE}", True),
        (f"{TOOLBAR} {TOOLBAR} {TOOLBAR}", True),
        ("1 | Giriş |", False),
        ("3/4 oranında devam zorunludur", False),
    ],
)
def test_layout_lines(line: str, layout: bool) -> None:
    assert is_layout_line(line) is layout


def test_skipped_section_may_cross_a_page() -> None:
    lines = ("önce", "Başlangıç", "1 | X |", "sayfa sonu", "2 | | X", "Bitiş", "sonra")

    kept, marked = skip_section(lines, ("Başlangıç",), ("Bitiş",))

    assert kept == ["önce", "Bitiş", "sonra"]
    assert marked == 2


@pytest.mark.parametrize(
    ("title", "year"),
    [(TITLE, "2025-2026"), ("Eğitim Bilgi Sistemi Endüstri Mühendisliği Bölümü Ders", None)],
)
def test_academic_year_from_the_title(title: str, year: str | None) -> None:
    assert title_academic_year(title) == year


def test_word_loss_counts_repeated_words() -> None:
    assert word_loss(["staj staj"], ["staj staj staj staj"]) == 0.5
    assert word_loss(["a | b"], ["a b", "1/"]) == 0.0
    assert word_loss([], []) == 0.0


def test_wrapped_title_is_joined_across_the_toolbar_line() -> None:
    flat = (
        ICON,
        "Eğitim Bilgi Sistemi Endüstri Mühendisliği Bölümü",
        f"{TOOLBAR} {TOOLBAR}",
        "Uzun Bir Ders Adı İle Veri Odaklı Strateji (2025 - 2026)",
        "Ders Adı Kodu Yarıyıl",
    )

    title = find_title(flat)

    assert title == (
        "Eğitim Bilgi Sistemi Endüstri Mühendisliği Bölümü "
        "Uzun Bir Ders Adı İle Veri Odaklı Strateji (2025 - 2026)"
    )
    assert title_academic_year(title) == "2025-2026"


def test_title_without_a_year_nearby_stays_one_line() -> None:
    flat = ("Eğitim Bilgi Sistemi Endüstri Mühendisliği Bölümü Ders", "Ders Adı", "Kodu", "AKTS")

    assert find_title(flat) == "Eğitim Bilgi Sistemi Endüstri Mühendisliği Bölümü Ders"


def test_names_without_a_space_after_the_comma_are_not_lost() -> None:
    table = ["Dersi Verenler | Prof.Dr. ORHAN TORKUL,Öğr.Gör. KAZIM GÜRKAN,"]
    flat = ["Dersi Verenler Prof.Dr. ORHAN TORKUL, Öğr.Gör. KAZIM GÜRKAN,"]

    assert word_loss(table, flat) == 0.0


def test_learning_outcome_matrix_is_skipped_and_counted() -> None:
    matrix_table = [
        "# | Ders Öğrenme Çıktılarının Program Çıktılarına Katkısı | |",
        "| | |",
        "1 | Matematik bilgisi. | 3 |",
        "2 | Tasarlama becerisi. | 4 |",
    ]
    matrix_flat = [
        "# Ders Öğrenme Çıktılarının Program Çıktılarına Katkısı",
        "1 Matematik bilgisi. 3",
    ]
    lines = [*PAGE_1_TABLE, TIMESTAMP, *PAGE_1_FLAT, _url(1, 2)]
    split_at = PAGE_2_TABLE.index("Değerlendirme Sistemi | | |")
    lines += [*PAGE_2_TABLE[:split_at], *matrix_table, *PAGE_2_TABLE[split_at:], TIMESTAMP]
    flat_at = PAGE_2_FLAT.index("Değerlendirme Sistemi")
    lines += [*PAGE_2_FLAT[:flat_at], *matrix_flat, *PAGE_2_FLAT[flat_at:], _url(2, 2)]

    result = clean_ebs("\n".join(lines))

    assert "Program Çıktılarına Katkısı" not in result.text
    assert "Matematik bilgisi" not in result.text
    assert "skipped the learning outcome to program outcome matrix (4 lines)" in result.warnings
    assert result.word_loss == 0.0  # the flat copy's matrix is left out of the loss too
