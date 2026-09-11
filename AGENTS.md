# AGENTS.md

Instructions for any AI coding agent (Claude Code, Cursor, Codex, etc.)
working in this repository. Human contributors follow the same rules.

## Before writing code

Read [`DESIGN.md`](DESIGN.md) first. It records the architecture and the
trade-offs already decided (API style, data models, threading model,
non-functional strategy). Don't re-derive these from scratch or silently
diverge from them — if a decision in `DESIGN.md` turns out to be wrong once
you're implementing it, say so and update `DESIGN.md` in the same change,
don't just quietly do something else.

## Repository layout

```
DESIGN.md, AGENTS.md, SKILLS.md   # design & process docs (repo root)
docs/diagrams/                    # one diagram per file, GitHub-rendered mermaid
server/                           # FastAPI + Postgres, Dockerized
client/                           # PySide2 desktop app, run from a venv
```

Each of `server/` and `client/` is self-contained with its own README,
dependency file, and tests — treat them as two separate deployables that
only communicate over the REST API, never by importing each other's code or
touching each other's database directly.

## Running things

- Server: see [`server/README.md`](server/README.md) (`docker compose up`,
  seed script, running tests).
- Client: see [`client/README.md`](client/README.md) (venv setup, seed
  script, running the app, running tests).

## Conventions

- **Python**: type hints on all public functions/methods; `ruff` for
  lint+format, `mypy` for type checking. Run both before committing.
- **Comments**: only for non-obvious *why* (a constraint, a workaround, an
  invariant that isn't clear from the code). Don't restate what the code
  does — names and types should already say that.
- **No speculative abstraction**: implement what the current milestone in
  `DESIGN.md` needs, not a generalized framework for hypothetical future
  features.
- **Commits**: small, logical, buildable at each step. Prefix with the area,
  e.g. `server: add track upload endpoint`, `client: add download worker`,
  `docs: add sequence diagram for upload`. Do not squash the history —
  reviewers want to see how the work was decomposed.
- **Tests live next to what they test**: `server/tests/`, `client/tests/`.
  A new endpoint or service method ships with at least one test.

## Guardrails (do not do these)

- Do not commit the FMA dataset, any `.mp3`/audio file, or anything under
  `fma_small/` / `fma_metadata/` — `.gitignore` already excludes these;
  don't work around it.
- Do not commit `.env` files or real secrets. Use `.env.example` with
  placeholder values.
- Do not add authentication/OAuth flows, cloud deployment configs, or
  cross-platform (Windows/macOS) build paths — explicitly out of scope per
  the assignment brief.
- Do not let the client block its UI thread on network or disk IO — route
  through `QThreadPool` workers and Qt signals, per `DESIGN.md` §4.1. A PR
  that adds a synchronous network/file call on the UI thread is a bug, not
  a style nit.
- Do not materialize the full catalog (8,000 rows) into memory in the
  client at once — the list views are paginated by design; keep it that
  way.
- Do not bypass the server as the source of truth — the client's SQLite
  store is a local cache/library, never an alternate catalog.

## When in doubt

Prefer the simplest change that satisfies `DESIGN.md` and the assignment's
minimum feature list. Bonus features (visualizer, similarity, recommendations
— see `DESIGN.md` §7) only after the minimum scope works end-to-end and the
non-functional requirements are demonstrated at full FMA-Small scale.
