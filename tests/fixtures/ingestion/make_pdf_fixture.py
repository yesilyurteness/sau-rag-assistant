"""Regenerate the synthetic FAQ PDF used by the loader and pipeline tests.

Run from the repository root:
    uv run --with reportlab python tests/fixtures/ingestion/make_pdf_fixture.py
The text is invented; it only mimics the layout of the real FAQ (bullet question, answer, and an
answer that continues on the next page).
"""

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
OUT = Path(__file__).with_name("sss_ornek.pdf")

PAGES = [
    [
        "Örnek Sık Sorulan Sorular",
        "",
        "•Örnek stajımı hangi dönemde yapabilirim?",
        "Örnek stajı yaz döneminde, fakültenin ilan ettiği tarihler arasında",
        "yapabilirsiniz. Başvuruyu başlangıçtan en az on gün önce tamamlayın.",
        "",
        "•Şirket Cumartesi çalışıyorsa ne olur?",
        "Şirketin Cumartesi çalıştığını belgelerseniz Cumartesi günü iş günü",
    ],
    [
        "sayılır. Belgeyi komisyon üyesine teslim edin.",
    ],
]


def main() -> None:
    pdfmetrics.registerFont(TTFont("DejaVu", FONT))
    pdf = canvas.Canvas(str(OUT), pagesize=A4)
    for lines in PAGES:
        pdf.setFont("DejaVu", 11)
        y = 800
        for line in lines:
            pdf.drawString(60, y, line)
            y -= 16
        pdf.showPage()
    pdf.save()


if __name__ == "__main__":
    main()
