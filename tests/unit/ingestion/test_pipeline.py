import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from app.ingestion.__main__ import main
from app.ingestion.checks import check_pages, check_table, check_text
from app.ingestion.manifest import Manifest, parse_manifest
from app.ingestion.models import Page, ProcessedDocument, Severity, Table
from app.ingestion.pipeline import Outcome, fingerprint, process_file, run
from app.ingestion.report import render_markdown, to_json

MANIFEST = """
[defaults]
academic_year = "2025-2026"

[[source]]
name = "sss_ornek.pdf"
kind = "faq"
title = "Örnek SSS"

[[source]]
name = "ders_plani_ornek.csv"
kind = "tabular"

[[source]]
name = "MezuniyetKosulları.txt"
kind = "narrative"
skip = "yanlış bilgi"

[[source]]
name = "Kayıp.pdf"
kind = "faq"

[[pattern]]
glob = "*.txt"
kind = "course_package"
"""


@dataclass
class FakeStore:
    docs: dict[str, tuple[str, ProcessedDocument]] = field(default_factory=dict)
    active: set[str] = field(default_factory=set)
    writes: int = 0

    async def get_fingerprint(self, source_name: str) -> str | None:
        if source_name not in self.active:
            return None
        return self.docs[source_name][0]

    async def upsert(self, document: ProcessedDocument, fingerprint: str) -> None:
        self.docs[document.entry.name] = (fingerprint, document)
        self.active.add(document.entry.name)
        self.writes += 1

    async def deactivate_missing(self, keep: set[str], *, prune: bool) -> list[str]:
        gone = sorted(self.active - keep)
        self.active -= set(gone)
        return gone


@pytest.fixture
def source_dir(tmp_path: Path, fixtures: Path) -> Path:
    for name in ("Ornek Planlama.txt", "sss_ornek.pdf", "ders_plani_ornek.csv"):
        shutil.copy(fixtures / name, tmp_path / name)
    (tmp_path / "MezuniyetKosulları.txt").write_text("60 iş günü", encoding="utf-8")
    (tmp_path / "notlar.docx").write_bytes(b"x")
    (tmp_path / "Bozuk Ders.txt").write_text("Bu bir ders paketi değil.", encoding="utf-8")
    (tmp_path / "arsiv").mkdir()
    (tmp_path / "arsiv" / "StajSSS.txt").write_text("eski", encoding="utf-8")
    return tmp_path


@pytest.fixture
def manifest() -> Manifest:
    return parse_manifest(MANIFEST)


async def test_run_classifies_every_file(source_dir: Path, manifest: Manifest) -> None:
    result = await run(source_dir, manifest, FakeStore())

    outcomes = {r.name: r.outcome for r in result.files}
    assert outcomes == {
        "Bozuk Ders.txt": Outcome.REJECTED,  # matched the course pattern but did not parse
        "MezuniyetKosulları.txt": Outcome.SKIPPED,
        "Ornek Planlama.txt": Outcome.INGESTED,
        "ders_plani_ornek.csv": Outcome.INGESTED,
        "notlar.docx": Outcome.UNREGISTERED,
        "sss_ornek.pdf": Outcome.INGESTED,
    }  # the arsiv/ sub-folder is not scanned
    assert result.missing == ["Kayıp.pdf"]


async def test_rerun_is_idempotent_and_detects_changes(
    source_dir: Path, manifest: Manifest
) -> None:
    store = FakeStore()
    await run(source_dir, manifest, store)
    writes = store.writes

    second = await run(source_dir, manifest, store)
    assert store.writes == writes
    assert {
        r.outcome for r in second.files if r.document and r.outcome is not Outcome.REJECTED
    } == {Outcome.UNCHANGED}

    (source_dir / "sss_ornek.pdf").unlink()
    with (source_dir / "ders_plani_ornek.csv").open("a", encoding="utf-8") as f:
        f.write("2. Yarıyıl;ENM 998;Yeni Ders;Zorunlu;Türkçe;3+0;3;4;x\n")
    third = await run(source_dir, manifest, store)

    outcomes = {r.name: r.outcome for r in third.files}
    assert outcomes["ders_plani_ornek.csv"] is Outcome.UPDATED
    assert third.deactivated == ["sss_ornek.pdf"]


async def test_manifest_change_alone_triggers_update(source_dir: Path, manifest: Manifest) -> None:
    store = FakeStore()
    await run(source_dir, manifest, store)
    changed = parse_manifest(MANIFEST.replace('title = "Örnek SSS"', 'title = "Yeni başlık"'))

    result = await run(source_dir, changed, store)

    outcomes = {r.name: r.outcome for r in result.files}
    assert outcomes["sss_ornek.pdf"] is Outcome.UPDATED


async def test_dry_run_writes_nothing(source_dir: Path, manifest: Manifest) -> None:
    result = await run(source_dir, manifest, None)

    assert result.dry_run
    assert Outcome.PROCESSED in {r.outcome for r in result.files}


def test_process_faq_pdf_tracks_pages(fixtures: Path, manifest: Manifest) -> None:
    path = fixtures / "sss_ornek.pdf"
    entry = manifest.resolve(path.name)
    assert entry is not None

    doc = process_file(path, entry, path.read_bytes())

    assert len(doc.chunks) == 2
    saturday = doc.chunks[1]
    assert saturday.content.startswith("Soru: Şirket Cumartesi çalışıyorsa ne olur?")
    assert saturday.content.endswith("teslim edin.")  # answer continues on page 2
    assert (saturday.page_start, saturday.page_end) == (1, 2)
    assert saturday.header.startswith("Örnek SSS | 2025-2026 | ")


def test_process_course_package(fixtures: Path, manifest: Manifest) -> None:
    path = fixtures / "Ornek Planlama.txt"
    entry = manifest.resolve(path.name)
    assert entry is not None

    doc = process_file(path, entry, path.read_bytes())

    assert doc.title == "Örnek Planlama (ENM 999)"
    assert doc.academic_year == "2025-2026"
    assert doc.duplicate_chars_removed > 0
    assert doc.metadata["ebs_course_id"] == "123456"
    assert "ects_workload_mismatch" in {f.code for f in doc.findings}


def test_fingerprint_is_stable(fixtures: Path, manifest: Manifest) -> None:
    path = fixtures / "sss_ornek.pdf"
    entry = manifest.resolve(path.name)
    assert entry is not None
    a = process_file(path, entry, path.read_bytes())
    b = process_file(path, entry, path.read_bytes())

    assert fingerprint(a) == fingerprint(b)


async def test_report_renders_markdown_and_json(source_dir: Path, manifest: Manifest) -> None:
    result = await run(source_dir, manifest, None)

    markdown = render_markdown(result)
    payload = json.loads(to_json(result))

    assert "# Ingestion report" in markdown
    assert "unparsed_course_package" in markdown
    assert "## Course packages (review these)" in markdown
    assert "`notlar.docx`" in markdown
    assert {f["name"] for f in payload["files"]} >= {"Ornek Planlama.txt", "sss_ornek.pdf"}


def test_cli_dry_run_writes_reports(source_dir: Path, tmp_path: Path) -> None:
    manifest_path = tmp_path / "sources.toml"
    manifest_path.write_text(MANIFEST, encoding="utf-8")
    reports = tmp_path / "reports"

    code = main(
        [
            "--source-dir",
            str(source_dir),
            "--manifest",
            str(manifest_path),
            "--report-dir",
            str(reports),
            "--dry-run",
        ]
    )

    assert code == 1  # the unparsable course package is an error
    assert len(list(reports.glob("ingestion-*.md"))) == 1
    assert len(list(reports.glob("ingestion-*.json"))) == 1


def test_cli_rejects_missing_folder(tmp_path: Path) -> None:
    assert main(["--source-dir", str(tmp_path / "yok"), "--dry-run"]) == 2


def test_check_text_flags_quality_problems() -> None:
    assert check_text("")[0].code == "empty_text"
    codes = {f.code for f in check_text("Kısa metin � ĠġĢ", expected_year="2025-2026")}
    assert {"short_text", "replacement_characters", "garbled_text"} <= codes
    other = check_text("Akademik yıl: 2024-2025 " * 20, expected_year="2025-2026")
    assert other[0].code == "mentions_other_academic_year"
    assert other[0].severity is Severity.INFO


def test_check_pages_and_table() -> None:
    pages = [Page(1, "metin " * 20), Page(2, ""), Page(3, "", 1), Page(4, "kısa", 3)]
    codes = {f.code: f.message for f in check_pages(pages)}
    assert codes["empty_page"].endswith("2-3")
    assert codes["image_heavy_page"].endswith("4")

    table = Table(["Kodu", "Ders"], [["", "A"], ["", "A"], ["X 1"]])
    table_codes = {f.code for f in check_table(table)}
    assert table_codes == {"ragged_rows", "duplicate_rows", "empty_cells"}


def test_process_announcement_txt_keeps_date_table_together(tmp_path: Path) -> None:
    path = tmp_path / "Duyuru.txt"
    path.write_text(
        "BÖLÜM Staj Duyurusu\n\n"
        "Staj yapabileceğiniz tarihler aşağıdadır ve sisteme tanıtılmıştır.\n\n"
        "Staj Başlangıç Staj Bitiş Son Başvuru Tarihi\n"
        "22.06.2026 20.07.2026 12.06.2026 Yaz-1\n"
        "06.07.2026 03.08.2026 26.06.2026 Yaz-2\n\n"
        "Akademik yıl: 2024-2025 \\*\\*Kaşe ve imza ORT \\> 2.00 olmalıdır\\!\n",
        encoding="utf-8",
    )
    manifest = parse_manifest(
        '[[source]]\nname = "Duyuru.txt"\nkind = "announcement"\nacademic_year = "2025-2026"'
    )
    entry = manifest.resolve("Duyuru.txt")
    assert entry is not None

    doc = process_file(path, entry, path.read_bytes())

    text = "\n".join(c.content for c in doc.chunks)
    assert "22.06.2026 20.07.2026 12.06.2026 Yaz-1\n06.07.2026" in text
    assert "ORT > 2.00 olmalıdır!" in text  # markdown escapes removed
    assert "mentions_other_academic_year" in {f.code for f in doc.findings}
