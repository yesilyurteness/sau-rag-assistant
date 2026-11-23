"""Enable the Postgres extensions the schema needs.

infra/postgres/init.sql already does this for the docker-compose database, but CI's Postgres
service container does not run init.sql, so the migration chain must not depend on it.
`vector` is for embeddings (step 3), `pg_trgm` for fuzzy name matching.

Revision ID: 0001
Revises:
Create Date: 2026-11-23
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EXTENSIONS = ("vector", "pg_trgm")


def upgrade() -> None:
    for extension in EXTENSIONS:
        op.execute(f"CREATE EXTENSION IF NOT EXISTS {extension}")


def downgrade() -> None:
    for extension in reversed(EXTENSIONS):
        op.execute(f"DROP EXTENSION IF EXISTS {extension}")
