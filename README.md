# Eureka Music App

A music catalog server + Ubuntu desktop client, built for the Eureka
Robotics full-time software engineer take-home assignment.

- **Server**: FastAPI + Postgres, packaged for `docker compose`. Stores the
  song catalog and audio files, and is the single source of truth.
- **Client**: Python3 + PySide2 desktop app for Ubuntu. Browses/downloads
  from the server, plays music locally, manages playlists, uploads tracks.

## Start here

- [`DESIGN.md`](DESIGN.md) — architecture, API/data-model decisions and why,
  non-functional strategy. Read this before the code.
- [`docs/diagrams/`](docs/diagrams/) — C4 context/container, ERDs, flow, and
  sequence diagrams referenced from `DESIGN.md`.
- [`AGENTS.md`](AGENTS.md) — conventions for anyone (human or AI) working in
  this repo.
- [`SKILLS.md`](SKILLS.md) — how AI was used while building this project.

## Run it

- [`server/README.md`](server/README.md) — build/run the server via Docker,
  seed the catalog from FMA Small, verify it's working.
- [`client/README.md`](client/README.md) — set up the client venv, seed a
  local library, run the app, verify it's working.

## Status

Design phase complete (architecture, diagrams, AI-collaboration docs).
Server and client both have working implementations of the required
minimum feature set, with passing test suites — see the commit history for
how the work was decomposed. Verified end-to-end on a real Ubuntu 22.04
machine: live `docker compose` stack, full 8,000-track FMA Small seed,
client GUI exercised against it (browse/search, download, playback incl.
crash-safe resume, playlists, upload).

All five bonus features in `DESIGN.md` §7 are implemented, covered by
unit/integration tests, and verified live end-to-end on the same Ubuntu
machine: the audio-content similarity engine + recommend-next (server),
the real-time audio visualizer, the listening-stats dashboard, and M3U
playlist export/import (client). The similarity engine's full-catalog
audio-feature seed (a heavier pass than the metadata-only one above) has
completed against the full 8,000-track catalog.

## Data

FMA Small isn't in this repo (per the assignment instructions) — pass its
unzipped path to the seed scripts described in the server/client READMEs.
