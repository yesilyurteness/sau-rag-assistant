import csv
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.ingestion.errors import (
    DocumentDecodeError,
    DocumentReadError,
    EmptyDocumentError,
    IngestionError,
)
from app.ingestion.loaders import load_csv

HEADER = "Öğrenim Türü;Kız;Erkek;Metin"
ROW_1 = "1. Öğretim;368;258;1. Öğretimde 368 kız öğrenci var."
ROW_2 = "2. Öğretim;184;179;2. Öğretimde 184 kız öğrenci var."


def _write(tmp_path: Path, text: str, encoding: str = "utf-8-sig") -> Path:
    # The real files are UTF-8 with a BOM and CRLF line endings.
    path = tmp_path / "ogrenciSayilari.csv"
    path.write_bytes(text.replace("\n", "\r\n").encode(encoding))
    return path


def test_rows_are_read_as_raw_strings(tmp_path: Path) -> None:
    path = _write(tmp_path, f"{HEADER}\n{ROW_1}\n{ROW_2}\n")

    table = load_csv(path)

    assert table.source == path
    assert table.columns == ("Öğrenim Türü", "Kız", "Erkek", "Metin")
    assert table.rows == (
        ("1. Öğretim", "368", "258", "1. Öğretimde 368 kız öğrenci var."),
        ("2. Öğretim", "184", "179", "2. Öğretimde 184 kız öğrenci var."),
    )
    assert table.encoding == "utf-8-sig"
    assert table.warnings == ()


def test_empty_cells_are_kept_as_empty_strings(tmp_path: Path) -> None:
    # Elective slots in DersPlan.csv have no code, hours or credit.
    path = _write(tmp_path, "Dönem;Kodu;Ders;Kredi\n7. Yarıyıl;;MF-Teknik Seçmeli;\n")

    assert load_csv(path).rows == (("7. Yarıyıl", "", "MF-Teknik Seçmeli", ""),)


def test_quoted_cell_may_contain_the_delimiter(tmp_path: Path) -> None:
    path = _write(tmp_path, f'{HEADER}\n1. Öğretim;368;258;"Kız: 368; erkek: 258"\n')

    assert load_csv(path).rows == (("1. Öğretim", "368", "258", "Kız: 368; erkek: 258"),)


def test_blank_and_separator_only_rows_are_dropped_anywhere(tmp_path: Path) -> None:
    path = _write(tmp_path, f"\n{HEADER}\n{ROW_1}\n;;;\n\n ; ;;\n{ROW_2}\n;;;\n")

    table = load_csv(path)

    assert [row[0] for row in table.rows] == ["1. Öğretim", "2. Öğretim"]
    assert table.warnings == ("dropped 5 empty or separator-only rows",)


def test_windows_turkish_file_is_decoded_with_a_warning(tmp_path: Path) -> None:
    path = _write(tmp_path, f"{HEADER}\n{ROW_1}\n", encoding="cp1254")

    table = load_csv(path)

    assert table.columns[0] == "Öğrenim Türü"
    assert table.rows[0][3] == "1. Öğretimde 368 kız öğrenci var."
    assert table.encoding == "cp1254"
    assert table.warnings == ("decoded as cp1254, not UTF-8",)


def test_row_of_wrong_width_names_its_line(tmp_path: Path) -> None:
    # Line 1 header, line 2 ok, line 3 blank (dropped), line 4 has one cell too few.
    path = _write(tmp_path, f"{HEADER}\n{ROW_1}\n;;;\n2. Öğretim;184;179\n")

    with pytest.raises(DocumentReadError) as exc_info:
        load_csv(path)

    assert exc_info.value.reason == "row at line 4 has 3 columns, expected 4"


def test_row_with_too_many_cells_is_rejected(tmp_path: Path) -> None:
    path = _write(tmp_path, f"{HEADER}\n{ROW_1};fazla\n")

    with pytest.raises(DocumentReadError, match="has 5 columns, expected 4"):
        load_csv(path)


def test_one_column_header_means_a_wrong_delimiter(tmp_path: Path) -> None:
    path = _write(tmp_path, "Öğrenim Türü,Kız,Erkek\n1. Öğretim,368,258\n")

    with pytest.raises(DocumentReadError) as exc_info:
        load_csv(path)

    assert exc_info.value.reason == "header has only one column; the delimiter must be ';'"


def test_empty_column_name_is_rejected(tmp_path: Path) -> None:
    path = _write(tmp_path, "Personel;;Metin\nProfesör;6;Altı profesör var.\n")

    with pytest.raises(DocumentReadError) as exc_info:
        load_csv(path)

    assert exc_info.value.reason == "empty column name at position 2"


def test_duplicate_column_name_is_rejected(tmp_path: Path) -> None:
    path = _write(tmp_path, "Kodu;Ders;Kodu\nMAT 111;Matematik 1;MAT 111\n")

    with pytest.raises(DocumentReadError) as exc_info:
        load_csv(path)

    assert exc_info.value.reason == "duplicate column names: Kodu"


def test_header_without_data_rows_is_empty(tmp_path: Path) -> None:
    path = _write(tmp_path, f"{HEADER}\n;;;\n")

    with pytest.raises(EmptyDocumentError) as exc_info:
        load_csv(path)

    assert exc_info.value.reason == "no data rows after the header"


@pytest.mark.parametrize(
    "text", ["", "\n\n", ";;;\n;;;\n"], ids=["empty", "newlines", "separators"]
)
def test_file_without_a_header_is_empty(tmp_path: Path, text: str) -> None:
    path = _write(tmp_path, text)

    with pytest.raises(EmptyDocumentError) as exc_info:
        load_csv(path)

    assert exc_info.value.reason == "no header row"


@pytest.fixture
def tiny_field_limit() -> Iterator[None]:
    previous = csv.field_size_limit(5)
    yield
    csv.field_size_limit(previous)


@pytest.mark.usefixtures("tiny_field_limit")
def test_unparsable_csv_raises_read_error(tmp_path: Path) -> None:
    path = _write(tmp_path, f"{HEADER}\n{ROW_1}\n")

    with pytest.raises(DocumentReadError) as exc_info:
        load_csv(path)

    assert isinstance(exc_info.value.__cause__, csv.Error)


def test_undecodable_file_raises_decode_error(tmp_path: Path) -> None:
    path = tmp_path / "Bozuk.csv"
    path.write_bytes(b"Kodu;AKTS\nMAT 111;\x81\n")

    with pytest.raises(DocumentDecodeError):
        load_csv(path)


# --- cleaning (step 1a-3d)

ZERO_WIDTH_SPACE = chr(0x200B)
NO_BREAK_SPACE = chr(0x00A0)


def test_trailing_spaces_are_removed_and_counted(tmp_path: Path) -> None:
    # Komisyonlar.csv has trailing spaces in "Durum" and "Akademisyen".
    path = _write(
        tmp_path,
        "Komisyon;Durum ;Akademisyen\n"
        "Staj Komisyonu;Komisyon Başkanı ;Doç. Dr. Seher Polat \n"
        "Staj Komisyonu;Komisyon Üyesi;Dr. Öğr. Üyesi Nevra Akbilek\n",
    )

    table = load_csv(path)

    assert table.columns == ("Komisyon", "Durum", "Akademisyen")
    assert table.rows[0] == ("Staj Komisyonu", "Komisyon Başkanı", "Doç. Dr. Seher Polat")
    assert table.warnings == ("cleaned 3 cells",)


def test_invisible_characters_are_removed_from_cells(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        f"Kodu;Ders\nMAT{NO_BREAK_SPACE}111;Mate{ZERO_WIDTH_SPACE}matik  1\n",
    )

    table = load_csv(path)

    assert table.rows == (("MAT 111", "Matematik 1"),)
    assert table.warnings == ("cleaned 2 cells",)


def test_names_that_collide_after_cleaning_are_rejected(tmp_path: Path) -> None:
    path = _write(tmp_path, f"Kodu;Kodu ;Ders{ZERO_WIDTH_SPACE}\nMAT 111;MAT 111;Matematik 1\n")

    with pytest.raises(DocumentReadError) as exc_info:
        load_csv(path)

    assert exc_info.value.reason == "duplicate column names: Kodu"


def test_column_name_of_only_invisible_characters_is_empty(tmp_path: Path) -> None:
    path = _write(tmp_path, f"Personel;{ZERO_WIDTH_SPACE} ;Metin\nProfesör;6;Altı profesör.\n")

    with pytest.raises(DocumentReadError) as exc_info:
        load_csv(path)

    assert exc_info.value.reason == "empty column name at position 2"


def test_row_of_only_invisible_characters_is_dropped(tmp_path: Path) -> None:
    path = _write(tmp_path, f"{HEADER}\n{ROW_1}\n{ZERO_WIDTH_SPACE};{NO_BREAK_SPACE};;\n")

    table = load_csv(path)

    assert len(table.rows) == 1
    assert table.warnings == ("dropped 1 empty or separator-only rows",)


def test_warnings_list_cleaning_before_dropped_rows(tmp_path: Path) -> None:
    path = _write(tmp_path, f"{HEADER}\n{ROW_1} \n;;;\n", encoding="cp1254")

    assert load_csv(path).warnings == (
        "decoded as cp1254, not UTF-8",
        "cleaned 1 cells",
        "dropped 1 empty or separator-only rows",
    )


def test_csv_loader_errors_share_the_ingestion_base_class(tmp_path: Path) -> None:
    path = _write(tmp_path, "")

    with pytest.raises(IngestionError):
        load_csv(path)
