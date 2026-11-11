from pathlib import Path

from app.ingestion.chunking import ChunkContext
from app.ingestion.cleaning import clean_course_package
from app.ingestion.course_package import (
    CoursePackage,
    course_chunks,
    parse_course_package,
)


def _parse(fixtures: Path) -> CoursePackage:
    cleaned, _ = clean_course_package((fixtures / "Ornek Planlama.txt").read_text(encoding="utf-8"))
    pkg = parse_course_package(cleaned.text)
    assert pkg is not None
    return pkg


def test_parses_header_table_and_key_values(fixtures: Path) -> None:
    pkg = _parse(fixtures)

    assert (pkg.name, pkg.code, pkg.semester, pkg.credit, pkg.ects) == (
        "Örnek Planlama",
        "ENM 999",
        "5",
        "4",
        "5",
    )
    assert pkg.kv["Dersin Dili"] == "Türkçe"
    assert pkg.kv["Ön Koşul Dersleri"] == ""
    assert pkg.kv["Dersi Verenler"] == "Doç.Dr. ÖRNEK KOORDİNATÖR, Dr.Öğr.Üyesi DENEME HOCA"
    assert pkg.kv["Dersin Amacı"].endswith("uygulatmaktır.")


def test_parses_wrapped_tables_across_pages(fixtures: Path) -> None:
    pkg = _parse(fixtures)

    assert [(o.number, o.text) for o in pkg.outcomes] == [
        (1, "Talep tahmin yöntemlerini açıklayabilir."),
        (2, "Kapasite planı hazırlayabilir."),
    ]
    assert pkg.outcomes[0].methods == "Anlatım, Soru-Cevap, Tartışma,"
    assert [w[0] for w in pkg.weekly] == [1, 2, 3, 4]  # week 4 is on the second page
    assert pkg.weekly[1] == (2, "Talep tahmini", "Okuma: bölüm 1")
    # rows without an X are dropped; "10" + "a | ..." on two lines is joined
    assert pkg.program_outcomes == [
        ("3", "Karmaşık bir sistemi tasarlama becerisi.", 3),
        ("10a", "Proje yönetimi hakkında bilgi;", 4),
    ]


def test_metadata_exposes_workload_ects_conflict(fixtures: Path) -> None:
    meta = _parse(fixtures).metadata()

    assert meta["ects"] == "5"
    assert meta["workload_total_hours"] == 152
    assert meta["workload_hours_div_25"] == 6.08


def test_returns_none_without_header_table() -> None:
    assert parse_course_package("Bölüm Başkanından\nMetin") is None


def test_chunks_cover_sections_with_course_header(fixtures: Path) -> None:
    pkg = _parse(fixtures)

    chunks = course_chunks(
        pkg, ChunkContext(title="Ders: Örnek Planlama (ENM 999)", academic_year="2025-2026")
    )

    sections = [c.metadata["course_section"] for c in chunks]
    assert sections == [
        "card",
        "instructors",
        "purpose",
        "outcomes",
        "weekly",
        "resources",
        "assessment",
        "program_outcomes",
    ]
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))
    card, assessment = chunks[0], chunks[6]
    assert card.header == "Ders: Örnek Planlama (ENM 999) | 2025-2026 | Ders bilgileri"
    assert "AKTS: 5" in card.content
    assert "Ön koşul dersleri: yok" in card.content
    # both ECTS facts stay together so the 6,08 vs 5 conflict can be answered correctly
    assert "Toplam İş Yükü / 25 (Saat): 6,08" in assessment.content
    assert "Dersin AKTS kredisi (ders bilgileri tablosu): 5" in assessment.content
    workload_row = (
        "Ders Süresi (Sınav haftası dahildir: 16x toplam ders saati): "
        "sayı 16; süre (saat) 4; toplam iş yükü (saat) 64"
    )
    assert workload_row in assessment.content
    assert "Hafta 4: Çizelgeleme" in chunks[4].content
    assert chunks[4].section == "Haftalık plan (hafta 1-4)"
