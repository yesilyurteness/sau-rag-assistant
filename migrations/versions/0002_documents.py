"""Create the documents table: one row per source file.

Written by hand to stay readable; tests/integration/test_schema_matches_models.py runs
Alembic's autogenerate comparison against app.storage.models to prove they agree.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("source_name", sa.Text(), nullable=False),
        sa.Column("file_type", sa.Text(), nullable=False),
        sa.Column("academic_year", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documents")),
        sa.UniqueConstraint("source_name", name=op.f("uq_documents_source_name")),
        sa.CheckConstraint(
            "file_type IN ('txt', 'pdf', 'csv')", name=op.f("ck_documents_file_type")
        ),
        sa.CheckConstraint("status IN ('current', 'superseded')", name=op.f("ck_documents_status")),
        # "2025-2026": format first, then second year = first + 1 (CASE fixes the order).
        sa.CheckConstraint(
            "CASE WHEN academic_year ~ '^[0-9]{4}-[0-9]{4}$' "
            "THEN substr(academic_year, 6, 4)::int = substr(academic_year, 1, 4)::int + 1 "
            "ELSE false END",
            name=op.f("ck_documents_academic_year"),
        ),
        sa.CheckConstraint(
            "content_hash ~ '^[0-9a-f]{64}$'", name=op.f("ck_documents_content_hash")
        ),
        sa.CheckConstraint(
            "source_name = normalize(source_name, NFC)", name=op.f("ck_documents_source_name_nfc")
        ),
    )


def downgrade() -> None:
    op.drop_table("documents")
