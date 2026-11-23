"""One loader per source file type.

TXT and PDF loaders return an `app.ingestion.models.LoadedDocument`; the CSV loader returns an
`app.ingestion.models.LoadedTable`.
"""

from app.ingestion.loaders.csv import load_csv
from app.ingestion.loaders.pdf import load_pdf
from app.ingestion.loaders.txt import load_txt

__all__ = ["load_csv", "load_pdf", "load_txt"]
