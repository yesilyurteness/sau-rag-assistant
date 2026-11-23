"""Regenerate the synthetic PDFs used by the PDF loader tests.

Run from the repository root, passing a TTF font that has the Turkish letters (for example
DejaVu Sans). The font file itself is not kept in the repository:

    uv run --no-project --with reportlab python tests/fixtures/ingestion/make_pdf_fixtures.py \
        --font /path/to/DejaVuSans.ttf

The text is invented. reportlab's default Helvetica cannot draw ı, ş, ğ or İ, hence the font
argument. `invariant=1` leaves out the creation date and random IDs, so the same input always
gives byte-identical files.
"""

import argparse
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

OUT_DIR = Path(__file__).parent
FONT_NAME = "TurkishSans"

# One list of lines per page; an empty list is a page without any text.
SAMPLE_PAGES: list[list[str]] = [
    [
        "Örnek Staj Yönergesi",
        "Madde 1 - Öğrenciler iki staj yapar; her staj 20 iş günüdür.",
        "Şirket Cumartesi çalışıyorsa ve öğrenci bunu belgelerse",
        "Cumartesi günü iş günü sayılır.",
    ],
    [],
    [
        "Madde 2 - İŞ GÜVENLİĞİ eğitimi ılık bir sonbahar gününde yapılır.",
        "Ğ ğ Ü ü Ş ş İ ı Ö ö Ç ç",
    ],
]


def _write(path: Path, pages: list[list[str]], encrypt: str | None = None) -> None:
    pdf = canvas.Canvas(str(path), pagesize=A4, invariant=1, encrypt=encrypt)
    for lines in pages:
        pdf.setFont(FONT_NAME, 11)
        y = 800
        for line in lines:
            pdf.drawString(60, y, line)
            y -= 16
        pdf.showPage()
    pdf.save()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--font", type=Path, required=True, help="TTF font with Turkish letters")
    args = parser.parse_args()

    pdfmetrics.registerFont(TTFont(FONT_NAME, str(args.font)))
    _write(OUT_DIR / "ornek_yonerge.pdf", SAMPLE_PAGES)
    _write(OUT_DIR / "bos.pdf", [[], []])
    _write(OUT_DIR / "sifreli.pdf", SAMPLE_PAGES[:1], encrypt="parola")


if __name__ == "__main__":
    main()
