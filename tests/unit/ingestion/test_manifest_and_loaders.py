from datetime import date
from pathlib import Path

import pytest

from app.ingestion.loaders import LoadError, decode_text, load_csv, load_pdf, source_type_for
from app.ingestion.manifest import ManifestError, load_manifest, parse_manifest
from app.ingestion.models import DocStatus, SourceKind, SourceType

MANIFEST = """
[defaults]
academic_year = "2025-2026"

[[source]]
name = "StajSSS.pdf"
kind = "faq"
title = "SSS"

[[source]]
name = "Eski.pdf"
kind = "slides"
academic_year = "2013-2014"
status = "superseded"
valid_from = 2014-01-01

[[source]]
name = "MezuniyetKosulları.txt"
kind = "narrative"
skip = "yanlış bilgi"

[[pattern]]
glob = "*.txt"
kind = "course_package"
"""


def test_manifest_resolves_exact_names_before_patterns() -> None:
    manifest = parse_manifest(MANIFEST)

    faq = manifest.resolve("StajSSS.pdf")
    old = manifest.resolve("Eski.pdf")
    course = manifest.resolve("Matematik 1.txt")
    skipped = manifest.resolve("MezuniyetKosulları.txt")

    assert faq is not None and faq.kind is SourceKind.FAQ and faq.academic_year == "2025-2026"
    assert old is not None and old.status is DocStatus.SUPERSEDED
    assert old.valid_from == date(2014, 1, 1)
    assert course is not None and course.kind is SourceKind.COURSE_PACKAGE
    assert course.name == "Matematik 1.txt"
    assert skipped is not None and skipped.skipped
    assert manifest.resolve("notlar.docx") is None


def test_manifest_matches_decomposed_unicode_file_names() -> None:
    manifest = parse_manifest(MANIFEST)
    decomposed = "MezuniyetKosulları.txt".replace("ı", "ı")  # ı has no decomposition
    nfd = "Ög".replace("Ö", "Ö")

    assert manifest.resolve(decomposed) is not None
    assert manifest.resolve(f"{nfd}.txt") is not None


def test_manifest_reports_missing_files() -> None:
    manifest = parse_manifest(MANIFEST)

    assert manifest.missing_files({"StajSSS.pdf"}) == ["Eski.pdf"]


@pytest.mark.parametrize(
    "bad",
    [
        '[[source]]\nname = "a.pdf"\nkind = "poem"',
        '[[source]]\nname = "a.pdf"\nkind = "faq"\nacademic_year = "2025-2027"',
        '[[source]]\nname = "a.pdf"\nkind = "faq"\nstatus = "old"',
        '[[source]]\nname = "a.pdf"\nkind = "faq"\n[[source]]\nname = "a.pdf"\nkind = "faq"',
        "not = [toml",
    ],
)
def test_manifest_rejects_invalid_entries(bad: str) -> None:
    with pytest.raises(ManifestError):
        parse_manifest(bad)


def test_repository_manifest_is_valid() -> None:
    manifest = load_manifest(Path("config/sources.toml"))

    sunum = manifest.resolve("StajBilgilendirmeSunumu1.pdf")
    assert sunum is not None and sunum.status is DocStatus.SUPERSEDED
    mezuniyet = manifest.resolve("MezuniyetKosulları.txt")
    assert mezuniyet is not None and mezuniyet.skipped


def test_decode_text_falls_back_to_windows_1254() -> None:
    assert decode_text("Öğrenci".encode("utf-8-sig")) == ("Öğrenci", "utf-8")
    assert decode_text("Öğrenci şart".encode("cp1254")) == ("Öğrenci şart", "cp1254")


def test_load_csv_handles_bom_semicolons_and_blank_rows(fixtures: Path) -> None:
    loaded = load_csv((fixtures / "ders_plani_ornek.csv").read_bytes())

    assert loaded.table is not None
    assert loaded.table.header[0] == "Dönem"
    assert len(loaded.table.rows) == 3  # trailing ";;;;" row dropped


def test_load_pdf_returns_pages(fixtures: Path) -> None:
    loaded = load_pdf((fixtures / "sss_ornek.pdf").read_bytes())

    assert [p.number for p in loaded.pages] == [1, 2]
    assert "Cumartesi" in loaded.pages[0].text
    assert loaded.source_type is SourceType.PDF


def test_load_pdf_rejects_garbage() -> None:
    with pytest.raises(LoadError):
        load_pdf(b"not a pdf")


def test_unsupported_suffix() -> None:
    with pytest.raises(LoadError):
        source_type_for(Path("a.docx"))
