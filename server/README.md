# Server — Eureka Music App

FastAPI + Postgres. See [`../DESIGN.md`](../DESIGN.md) §3 for the API design
rationale and data model.

> Implementation in progress — this README will be filled in with concrete
> `docker compose` / seed / verify instructions as the server is built. See
> the repo's commit history for current progress.

## Planned layout

```
server/
  app/            # FastAPI application (routers, models, schemas, db)
  scripts/seed.py # seeds the catalog from an unzipped FMA Small folder
  tests/
  Dockerfile
  docker-compose.yml
  requirements.txt / pyproject.toml
  .env.example
```
