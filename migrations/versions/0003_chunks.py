"""Create the chunks table: the searchable pieces of TXT and PDF documents.

Deleting a document deletes its chunks in the database (ON DELETE CASCADE). The unique key
(document_id, position) also serves lookups by document_id, so there is no separate index.
academic_year and status are not copied here; they are read from documents with a join.
Written by hand; `alembic check` in the integration tests proves it matches the models.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chunks",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("document_id", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chunks")),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_chunks_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("document_id", "position", name=op.f("uq_chunks_document_id_position")),
        sa.CheckConstraint("length(text) > 0", name=op.f("ck_chunks_text_not_empty")),
        sa.CheckConstraint("page IS NULL OR page >= 1", name=op.f("ck_chunks_page")),
        sa.CheckConstraint("position >= 0", name=op.f("ck_chunks_position")),
    )


def downgrade() -> None:
    op.drop_table("chunks")
