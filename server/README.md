# Server — Eureka Music App

FastAPI + Postgres. See [`../DESIGN.md`](../DESIGN.md) §3 for the API design
rationale and data model.

**Note on migrations**: tables are created via SQLAlchemy `metadata.create_all`
on startup rather than Alembic migrations. Given the assignment's explicit
non-goals (no production-grade concerns expected), a migrations tool would
be more ceremony than the schema currently needs; a real multi-environment
deployment would want Alembic instead.

## Run via Docker Compose

```bash
cd server
cp .env.example .env   # defaults are fine for local use
docker compose up --build
```

This starts Postgres (with the `pg_trgm` extension enabled on first init —
see `init-db/01-extensions.sql`) and the API on `http://localhost:8000`.
Interactive API docs: `http://localhost:8000/docs`.

Data persists across restarts in named volumes (`pgdata`, `audio_storage`);
`docker compose down -v` if you want a clean slate.

## Seed the catalog from FMA Small

```bash
docker compose exec api python -m scripts.seed /data/fma --limit 100   # subset while developing
docker compose exec api python -m scripts.seed /data/fma                # full 8,000-track run
```

(Must be run as a module — `python scripts/seed.py` directly fails with
`ModuleNotFoundError: No module named 'app'`, since the script's own
directory, not `/app`, ends up first on `sys.path` that way.)

`/data/fma` above assumes you've mounted your unzipped FMA folder into the
`api` container — add a volume for it in `docker-compose.yml`, e.g.:

```yaml
    volumes:
      - audio_storage:/data/audio
      - /path/on/host/to/fma:/data/fma:ro
```

Idempotent: re-running skips tracks whose audio checksum is already
catalogued, so an interrupted run (this is a large dataset) can resume.
`--dry-run` parses and prints rows without writing anything — useful to
sanity-check `tracks.csv` parsing against your actual download first.

Seeding also extracts a small audio-content feature vector per track (see
`app/audio_features.py` and DESIGN.md §7) for the similarity/recommend-next
bonus features below — this is the slow part of a full run, not the file
copy/checksum step. On modest hardware (e.g. a 2-vCPU VM), budget real time
for a full 8,000-track run; it's still safely resumable if interrupted.

## Verify

```bash
curl http://localhost:8000/health
curl http://localhost:8000/tracks | jq
```

### Bonus features (DESIGN.md §7)

```bash
# audio-content similarity ranking for a given track id
curl http://localhost:8000/tracks/<id>/similar | jq

# nearest unplayed track, excluding ids you pass in
curl "http://localhost:8000/tracks/<id>/recommend-next?exclude=<id1>,<id2>" | jq
```

Both return 404 if the track has no feature vector yet (seeded/uploaded
before extraction ran, or its clip failed to decode) - not an error, just
nothing to rank against.

## Tests

Run against a real Postgres (matches production; exercises the `pg_trgm`
indexes that a SQLite fallback can't):

```bash
docker compose exec api pytest
```

Or locally against SQLite for a fast dev loop (doesn't exercise
Postgres-only behavior — see `tests/conftest.py`):

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

## Lint / types

```bash
ruff check .
mypy app scripts
```

## Layout

```
server/
  app/
    main.py           # FastAPI app + lifespan (creates tables on startup)
    config.py          # env-driven settings
    database.py         # async SQLAlchemy engine/session
    models.py            # Track, Genre, track_genre, TrackFeature (+ trigram indexes)
    schemas.py            # Pydantic response models
    pagination.py          # cursor encode/decode
    storage.py              # checksum + atomic-rename upload streaming, duration probing
    audio_features.py        # MFCC extraction + cosine similarity (bonus: similar/recommend-next)
    routers/
      tracks.py              # list/search, get, download (Range support), upload, similar, recommend-next
      genres.py
      health.py
  scripts/seed.py     # seeds the catalog + audio features from an unzipped FMA folder
  init-db/01-extensions.sql  # enables pg_trgm on first Postgres init
  tests/
  Dockerfile
  docker-compose.yml
```
