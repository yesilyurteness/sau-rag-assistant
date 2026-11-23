"""One loader per source file type. Each returns an `app.ingestion.models.LoadedDocument`."""

from app.ingestion.loaders.pdf import load_pdf
from app.ingestion.loaders.txt import load_txt

__all__ = ["load_pdf", "load_txt"]
