"""Fail when a text file in the repository holds an invisible or private-use character.

Such characters look like nothing (or like a normal space) in an editor, so they slip into
code and data unnoticed and break search, comparisons and tests. Write them as \\uXXXX escapes
instead. Ruff's PLE2515 only covers U+200B; this test covers the rest.
"""

import unicodedata
from collections.abc import Iterator
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

TEXT_SUFFIXES = frozenset(
    {".py", ".md", ".toml", ".json", ".jsonl", ".yml", ".yaml", ".csv", ".txt"}
    | {".sql", ".ini", ".cfg", ".example"}
)
SKIPPED_DIRS = frozenset(
    {".git", ".venv", "venv", "__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache"}
    | {"node_modules", "htmlcov", "build", "dist"}
)
# The local secrets file is never read (it is also not committed).
SKIPPED_FILES = frozenset({".env"})

NO_BREAK_SPACE = 0x00A0


def is_forbidden(char: str) -> bool:
    """BOM, zero-width characters, word joiner, soft hyphen and every other format (Cf)
    character, the no-break space, and the private-use area U+E000-U+F8FF (Co)."""
    return ord(char) == NO_BREAK_SPACE or unicodedata.category(char) in ("Cf", "Co")


def iter_text_files(root: Path) -> Iterator[Path]:
    """Files with a text suffix or without a suffix (Makefile, .gitignore), skipping tool
    and cache directories, the .env file and binary files (a NUL byte means binary)."""
    # Sort by the plain path text: Windows paths compare case-insensitively, Linux paths do not.
    for path in sorted(root.rglob("*"), key=lambda p: p.relative_to(root).as_posix()):
        relative = path.relative_to(root)
        if any(part in SKIPPED_DIRS for part in relative.parts[:-1]) or not path.is_file():
            continue
        if path.name in SKIPPED_FILES:
            continue
        if path.suffix and path.suffix not in TEXT_SUFFIXES:
            continue
        if b"\x00" in path.read_bytes():
            continue
        yield path


def find_forbidden_chars(root: Path) -> list[str]:
    """One "file:line:column: U+XXXX NAME" entry per forbidden character (1-based)."""
    findings: list[str] = []
    for path in iter_text_files(root):
        relative = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            findings.append(f"{relative}: not valid UTF-8")
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            for column, char in enumerate(line, start=1):
                if is_forbidden(char):
                    name = unicodedata.name(char, "PRIVATE USE")
                    findings.append(f"{relative}:{line_number}:{column}: U+{ord(char):04X} {name}")
    return findings


def test_repository_has_no_invisible_or_private_use_characters() -> None:
    findings = find_forbidden_chars(REPO_ROOT)

    assert not findings, "write these as \\uXXXX escapes:\n" + "\n".join(findings)


# --- the scanner itself


def test_scanner_reports_file_line_column_and_code(tmp_path: Path) -> None:
    (tmp_path / "data.py").write_text(
        f'A = "ok"\nB = "Staj{chr(0x200B)}"\nC = "{chr(0xF0B7)} madde"\n', encoding="utf-8"
    )
    (tmp_path / "notes.md").write_text(f"{chr(0xFEFF)}Başlık\nAKTS{chr(0x00A0)}5\n", "utf-8")
    (tmp_path / "Makefile").write_text(f"check:{chr(0x00AD)}\n", encoding="utf-8")

    assert find_forbidden_chars(tmp_path) == [
        "Makefile:1:7: U+00AD SOFT HYPHEN",
        "data.py:2:10: U+200B ZERO WIDTH SPACE",
        "data.py:3:6: U+F0B7 PRIVATE USE",
        "notes.md:1:1: U+FEFF ZERO WIDTH NO-BREAK SPACE",
        "notes.md:2:5: U+00A0 NO-BREAK SPACE",
    ]


def test_escaped_characters_are_not_reported(tmp_path: Path) -> None:
    backslash = chr(92)
    (tmp_path / "test_x.py").write_text(
        f'ZWSP = "{backslash}u200b"\nGLYPH = "{backslash}uf0a2"\n', encoding="utf-8"
    )

    assert find_forbidden_chars(tmp_path) == []


def test_turkish_letters_and_ordinary_bullets_are_allowed(tmp_path: Path) -> None:
    (tmp_path / "ok.txt").write_text("ı İ ş Ş ğ Ğ ü Ü ö Ö ç Ç • – …\n", encoding="utf-8")

    assert find_forbidden_chars(tmp_path) == []


def test_skipped_places_are_not_scanned(tmp_path: Path) -> None:
    bad = f"x{chr(0x200B)}\n"
    for directory in (".git", ".venv", "__pycache__", ".mypy_cache"):
        (tmp_path / directory).mkdir()
        (tmp_path / directory / "file.py").write_text(bad, encoding="utf-8")
    (tmp_path / ".env").write_text(bad, encoding="utf-8")
    (tmp_path / "image.png").write_text(bad, encoding="utf-8")  # suffix not in the list
    (tmp_path / "sample.pdf").write_bytes(b"%PDF\x00" + bad.encode())  # binary

    assert find_forbidden_chars(tmp_path) == []


def test_non_utf8_text_file_is_reported(tmp_path: Path) -> None:
    (tmp_path / "eski.txt").write_bytes("Öğrenci".encode("cp1254"))

    assert find_forbidden_chars(tmp_path) == ["eski.txt: not valid UTF-8"]
