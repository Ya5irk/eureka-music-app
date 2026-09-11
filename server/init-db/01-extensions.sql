-- Enables trigram-based fuzzy/substring search used by the title/artist
-- GIN indexes in app/models.py. Runs once, on first container init, via
-- Postgres's docker-entrypoint-initdb.d mechanism.
CREATE EXTENSION IF NOT EXISTS pg_trgm;
