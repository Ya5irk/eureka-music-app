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

This repository currently reflects the **design phase**: architecture,
diagrams, and repo scaffolding are in place; server and client
implementation follow in subsequent commits (see commit history).

## Data

This repo does not contain the [FMA Small](https://github.com/mdeff/fma)
dataset. Download `fma_small.zip` and `fma_metadata.zip` separately, unzip
them, and pass the path to the seed scripts described in the server/client
READMEs.
