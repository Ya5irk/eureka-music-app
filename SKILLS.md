# SKILLS.md — how AI was used on this assignment

This file is a transparency log of the AI-assisted workflow used to build
Eureka Music App, per the assignment's request to show the design phase and
how AI was used, not just the output.

## Workflow

1. **Problem framing (human-led)**: read the assignment brief in full,
   identified the two deployables (server, client), the hard constraints
   (tech stack, dataset, non-functional targets), and what's explicitly out
   of scope, before opening an editor.
2. **Design phase (AI-assisted, human-reviewed)**: worked with Claude Code
   to turn the brief into `DESIGN.md` — architecture, API style + written
   justification, data models, threading model, non-functional strategy —
   and the diagrams in `docs/diagrams/` (C4 context/container, ERDs, flow,
   sequence, class). This step happened *before* any implementation code,
   and was reviewed/adjusted by hand before moving on, rather than accepted
   as-is.
3. **Scaffolding (AI-drafted)**: repo structure, boilerplate FastAPI routers,
   Pydantic schemas, PySide2 widget skeletons, docker-compose/Dockerfile,
   and seed script CLIs were drafted with AI assistance from the agreed
   design, then reviewed for correctness against `DESIGN.md`.
4. **Business logic & trade-offs (human-directed)**: decisions like
   cursor-vs-offset pagination, WAL-mode SQLite for crash safety, keeping
   shuffle non-destructive to manual ordering, and the single-`QMediaPlayer`
   instance for memory stability were made deliberately (see `DESIGN.md` §3
   and §4) and then implemented with AI assistance — not generated blind.
5. **Tests (AI-assisted)**: AI helped draft `pytest` cases for server CRUD
   and client services; coverage of edge cases (empty catalog, duplicate
   uploads via checksum, resume-after-kill) was reviewed and extended by
   hand where the first draft missed a case.
6. **Diagrams kept in sync**: whenever an implementation detail diverged
   from what a diagram showed, the diagram (and `DESIGN.md`) was updated in
   the same commit — diagrams are meant to describe the system as built, not
   just as originally imagined.

## What AI was *not* used for

- Deciding what the minimum feature set is — that's fixed by the brief.
- Picking the tech stack — fixed by the brief's required minimums.
- Inventing non-functional targets — fixed by the brief (10s startup, no
  freezing, SIGKILL-safe persistence, stable memory).
- Writing the final commit history narrative — commits are scoped and
  written to reflect the actual order of work, not batch-generated after
  the fact.

## Tooling

- **Claude Code** (agentic coding in the terminal/IDE) for design docs,
  diagrams, scaffolding, and iterative implementation with direct file
  edits and test runs in the loop.
