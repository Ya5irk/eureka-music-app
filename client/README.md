# Client — Eureka Music App

Python3 + PySide2 desktop app for Ubuntu. See [`../DESIGN.md`](../DESIGN.md)
§4 for the architecture, threading model, and non-functional strategy.

## Why Python 3.10

`PySide2==5.15.x` (required by the assignment) only ships PyPI wheels up to
**Python 3.10** — there are no `cp311`/`cp312` wheels. Ubuntu 22.04 ships
3.10 by default; on 20.04 or 24.04 you'll need to install 3.10 alongside
the system Python before creating the venv:

```bash
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install python3.10 python3.10-venv
```

## Setup

```bash
cd client
python3.10 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt   # or requirements.txt for a non-dev install
```

The server must be running first (see [`../server/README.md`](../server/README.md)):

```bash
cd ../server && docker compose up -d
```

## Configuration

Everything has a sane default; override via environment variables if needed:

| Variable | Default | Purpose |
|---|---|---|
| `EUREKA_API_URL` | `http://localhost:8000` | server base URL |
| `EUREKA_STATE_DIR` | `~/.local/share/eureka-music` | local SQLite DB + downloaded audio live here |
| `EUREKA_DB_PATH` | `<state dir>/library.sqlite3` | override the DB path directly |

## Run

```bash
python -m app.main
```

On first launch the Library tab is empty — use the Browse tab to search the
server's catalog and download tracks, or seed a local library directly (see
below) for a faster demo setup.

## Seed a local library directly (dev/demo)

Bypasses the server and populates the local SQLite + downloads folder
straight from an unzipped FMA Small folder — useful for iterating without
downloading every track through the UI:

```bash
python -m scripts.seed /path/to/fma --limit 100   # subset while developing
python -m scripts.seed /path/to/fma                # full 8,000-track run
```

Idempotent: re-running skips tracks already present by checksum.

## Tests

```bash
pytest
```

19+ tests cover the DAOs (SQLite persistence, playlist ordering, play-state
round-trips), `PlaylistService` (shuffle never mutates manual order —
`DESIGN.md` §4.2), `ApiClient` (against `httpx.MockTransport`, no live
server needed), `DownloadManager` (via `pytest-qt`'s `qtbot`, including the
checksum-dedupe path that skips the network entirely), `PlayerController`
(queue navigation, loop modes, shuffle, crash-safe resume), and the seed
script's CSV parsing. Tests run headless via `QT_QPA_PLATFORM=offscreen`,
set automatically in `tests/conftest.py`.

## Lint / types

```bash
ruff check .
mypy app scripts
```

## Verify the non-functional requirements

These need the full FMA-Small-scale local library to mean anything — seed
the full dataset first, then:

- **Startup < 10s**: `time python -m app.main` (measure to the window
  appearing, not full exit).
- **Never freezes**: interact with Browse/search/download/upload while a
  large download is in flight — all of it runs on `QThreadPool` workers
  (see `app/workers.py`), so the UI thread should stay responsive.
- **Survives SIGKILL**: start playback, `kill -9` the process mid-track,
  relaunch — it should resume at (roughly) the same track and position.
  `PlayerController.restore_last_state()` reads this from `play_state`,
  written throttled during playback via SQLite in WAL mode.
- **Stable memory**: watch RSS (`ps`/`top`) while scrolling the full
  8,000-track catalog and playing several tracks back to back — the list
  views page in ~100–200 rows at a time (`canFetchMore`/`fetchMore` in
  `app/ui/models.py`) rather than materializing the whole catalog.

## Layout

```
client/
  app/
    api_client.py         # sync HTTP client (used from worker threads only)
    config.py              # env-driven settings
    dao.py                 # LocalLibraryDao, PlaylistDao, PlayStateDao (sqlite3, WAL)
    database.py             # schema + connection helper
    local_models.py         # LocalTrack, Playlist, PlayState, LoopMode
    main.py                 # entry point
    workers.py               # QThreadPool worker wrapping a callable + Qt signals
    services/
      download_manager.py    # async download + checksum-dedupe + library insert
      upload_manager.py      # async upload
      playlist_service.py    # playlist CRUD + non-destructive shuffle view
      player_controller.py   # QMediaPlayer wrapper: queue, loop, shuffle, crash-safe state
    ui/
      main_window.py         # assembles Browse / Library / Playlist / Player bar
      models.py               # QAbstractListModel subclasses, lazy fetch-as-you-scroll
      upload_dialog.py
  scripts/seed.py           # seeds the local library from an unzipped FMA folder
  tests/
```
