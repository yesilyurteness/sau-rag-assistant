"""One loader per source file type. Each returns an `app.ingestion.models.LoadedDocument`."""

from app.ingestion.loaders.txt import load_txt

__all__ = ["load_txt"]
