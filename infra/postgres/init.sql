-- Runs once, when the postgres volume is first created.
-- Schema itself is managed by Alembic migrations (Stage 1); this only enables extensions.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- trigram similarity, useful for names and fuzzy matching
