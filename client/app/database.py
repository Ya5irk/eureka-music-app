import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS local_track (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    album TEXT,
    duration_seconds INTEGER NOT NULL DEFAULT 0,
    local_path TEXT NOT NULL,
    checksum_sha256 TEXT NOT NULL,
    downloaded_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS playlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    loop_mode INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS playlist_track (
    playlist_id INTEGER NOT NULL REFERENCES playlist(id) ON DELETE CASCADE,
    track_id TEXT NOT NULL REFERENCES local_track(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    PRIMARY KEY (playlist_id, track_id)
);

CREATE TABLE IF NOT EXISTS play_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    current_track_id TEXT,
    position_ms INTEGER NOT NULL DEFAULT 0,
    playlist_id INTEGER,
    playlist_index INTEGER NOT NULL DEFAULT 0,
    shuffle_on INTEGER NOT NULL DEFAULT 0
);
"""


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
        conn.commit()


@contextmanager
def connect(db_path: Path) -> Iterator[sqlite3.Connection]:
    """A short-lived, WAL-mode connection. Opened fresh per call rather than
    shared across threads: sqlite3 connections aren't safe to share between
    threads, and this app's DAOs are invoked from QThreadPool workers, so a
    cheap per-call connection is simpler and safer than a pooling scheme.
    """
    conn = sqlite3.connect(db_path, timeout=5.0)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        yield conn
    finally:
        conn.close()
