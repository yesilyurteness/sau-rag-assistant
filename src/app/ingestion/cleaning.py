"""Text cleanup shared by all loaders.

The goal is to fix the *form* of the text, never its content: no words are changed,
added or removed. Rules that depend on the source type (for example joining lines that
a PDF broke in the middle of a sentence) live in that type's loader, not here.
"""

import re
import unicodedata

# Characters that are invisible but break search and comparisons.
_INVISIBLE = {
    "﻿": "",  # byte order mark
    "​": "",  # zero-width space
    "‌": "",  # zero-width non-joiner
    "‍": "",  # zero-width joiner
    "⁠": "",  # word joiner
    "­": "",  # soft hyphen
}
_INVISIBLE_TABLE = str.maketrans(_INVISIBLE)

# Control characters other than newline (tab is turned into a space below).
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
# Any horizontal whitespace run (tabs, no-break spaces, other Unicode spaces).
_HORIZONTAL_SPACE = re.compile(r"[^\S\n]+")
_MANY_BLANK_LINES = re.compile(r"\n{3,}")


def clean_text(text: str) -> str:
    """Normalize a document's text.

    Steps, in order:
    1. Unicode NFC, so a dotted capital I written as "I + combining dot" becomes "İ" and
       compares equal to the same word typed normally.
    2. Windows and old Mac line endings become "\\n".
    3. Invisible characters (BOM, zero-width, soft hyphen) and control characters are removed.
    4. Runs of spaces and tabs become one space; spaces at line ends are removed.
    5. Three or more line breaks become one blank line; leading/trailing whitespace is removed.
    """
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.translate(_INVISIBLE_TABLE)
    text = text.replace("\t", " ")
    text = _CONTROL_CHARS.sub("", text)
    text = _HORIZONTAL_SPACE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = _MANY_BLANK_LINES.sub("\n\n", text)
    return text.strip()
