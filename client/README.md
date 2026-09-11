# Client — Eureka Music App

Python3 + PySide2 desktop app for Ubuntu. See [`../DESIGN.md`](../DESIGN.md)
§4 for the architecture, threading model, and non-functional strategy.

> Implementation in progress — this README will be filled in with concrete
> venv / seed / run / verify instructions as the client is built. See the
> repo's commit history for current progress.

## Planned layout

```
client/
  app/            # PySide2 application (ui/, services/, db/)
  scripts/seed.py # seeds the local library from an unzipped FMA Small folder
  tests/
  requirements.txt
```
