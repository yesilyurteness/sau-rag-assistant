"""ORM model checks that need no database."""

import unicodedata

from app.storage.models import Document

NFC_NAME = "İstatistik Olasılık 1.txt"
NFD_NAME = unicodedata.normalize("NFD", NFC_NAME)  # "I" + combining dot above


def test_source_name_is_stored_in_nfc() -> None:
    assert NFD_NAME != NFC_NAME  # the test data really is decomposed

    document = Document(source_name=NFD_NAME)

    assert document.source_name == NFC_NAME


def test_documents_constraints_have_fixed_names() -> None:
    names = {constraint.name for constraint in Document.__table__.constraints}

    assert names == {
        "pk_documents",
        "uq_documents_source_name",
        "ck_documents_file_type",
        "ck_documents_status",
        "ck_documents_academic_year",
        "ck_documents_content_hash",
        "ck_documents_source_name_nfc",
    }
