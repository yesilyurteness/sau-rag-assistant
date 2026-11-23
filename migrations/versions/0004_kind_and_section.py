"""Add documents.kind and chunks.section.

`kind` picks the chunker (decided in step 1c-1 from the structure measurements). It is NOT
NULL without a default: no documents are ingested before step 1d, and on a table that
already had rows the migration should fail loudly instead of inventing a kind.
`(kind = 'table') = (file_type = 'csv')` keeps CSV files, and only CSV files, as tables.
`section` is the title of the section a chunk belongs to; NULL when the kind has none.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("kind", sa.Text(), nullable=False))
    op.create_check_constraint(
        op.f("ck_documents_kind"),
        "documents",
        "kind IN ('course_package', 'faq', 'decision_list', 'slides', 'narrative', 'table')",
    )
    op.create_check_constraint(
        op.f("ck_documents_kind_table_is_csv"),
        "documents",
        "(kind = 'table') = (file_type = 'csv')",
    )

    op.add_column("chunks", sa.Column("section", sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f("ck_chunks_section_not_empty"),
        "chunks",
        "section IS NULL OR length(section) > 0",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_chunks_section_not_empty"), "chunks", type_="check")
    op.drop_column("chunks", "section")
    op.drop_constraint(op.f("ck_documents_kind_table_is_csv"), "documents", type_="check")
    op.drop_constraint(op.f("ck_documents_kind"), "documents", type_="check")
    op.drop_column("documents", "kind")
