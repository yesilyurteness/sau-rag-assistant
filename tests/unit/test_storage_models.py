"""ORM model checks that need no database."""

import unicodedata

from app.storage.models import Chunk, Document

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


def test_chunks_constraints_have_fixed_names() -> None:
    names = {constraint.name for constraint in Chunk.__table__.constraints}

    assert names == {
        "pk_chunks",
        "fk_chunks_document_id_documents",
        "uq_chunks_document_id_position",
        "ck_chunks_text_not_empty",
        "ck_chunks_page",
        "ck_chunks_position",
    }


def test_chunk_foreign_key_cascades_on_delete() -> None:
    (foreign_key,) = Chunk.__table__.foreign_keys

    assert foreign_key.target_fullname == "documents.id"
    assert foreign_key.ondelete == "CASCADE"
