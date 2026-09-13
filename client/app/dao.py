import sqlite3
from pathlib import Path

from app.database import connect
from app.local_models import LocalTrack, LoopMode, Playlist, PlayState


def _split_csv_field(value: str | None) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()] if value else []


def _row_to_track(row: sqlite3.Row) -> LocalTrack:
    return LocalTrack(
        id=row["id"],
        title=row["title"],
        artist=row["artist"],
        album=row["album"],
        duration_seconds=row["duration_seconds"],
        local_path=row["local_path"],
        checksum_sha256=row["checksum_sha256"],
        downloaded_at=row["downloaded_at"],
        release_year=row["release_year"],
        license=row["license"],
        tags=_split_csv_field(row["tags"]),
        genres=_split_csv_field(row["genres"]),
    )


class LocalLibraryDao:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def insert_track(self, track: LocalTrack) -> None:
        with connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO local_track
                    (id, title, artist, album, duration_seconds, local_path, checksum_sha256,
                     release_year, license, tags, genres)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    track.id,
                    track.title,
                    track.artist,
                    track.album,
                    track.duration_seconds,
                    track.local_path,
                    track.checksum_sha256,
                    track.release_year,
                    track.license,
                    ",".join(track.tags) or None,
                    ",".join(track.genres) or None,
                ),
            )
            conn.commit()

    def find_by_checksum(self, checksum: str) -> LocalTrack | None:
        with connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT * FROM local_track WHERE checksum_sha256 = ?", (checksum,)
            ).fetchone()
            return _row_to_track(row) if row else None

    def get(self, track_id: str) -> LocalTrack | None:
        with connect(self._db_path) as conn:
            row = conn.execute("SELECT * FROM local_track WHERE id = ?", (track_id,)).fetchone()
            return _row_to_track(row) if row else None

    def list_page(
        self, offset: int, limit: int, query: str | None = None
    ) -> list[LocalTrack]:
        sql = "SELECT * FROM local_track"
        params: list[object] = []
        if query:
            sql += " WHERE title LIKE ? OR artist LIKE ?"
            like = f"%{query}%"
            params += [like, like]
        sql += " ORDER BY downloaded_at DESC, id DESC LIMIT ? OFFSET ?"
        params += [limit, offset]
        with connect(self._db_path) as conn:
            rows = conn.execute(sql, params).fetchall()
            return [_row_to_track(r) for r in rows]

    def count(self) -> int:
        with connect(self._db_path) as conn:
            (n,) = conn.execute("SELECT COUNT(*) FROM local_track").fetchone()
            return int(n)

    def find_by_path_or_filename(self, path: str) -> LocalTrack | None:
        """Used by M3U playlist import: an exact `local_path` match works
        when the .m3u was exported from this same install, but the same
        library re-downloaded on another machine (or after a reinstall)
        will have a different downloads directory - falling back to a
        filename match (local_path is always "<checksum>.mp3", so the
        filename alone is already a strong, checksum-derived match) makes
        import actually portable rather than only ever working on the
        exact machine that exported it.
        """
        with connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT * FROM local_track WHERE local_path = ?", (path,)
            ).fetchone()
            if row is None:
                filename = Path(path).name
                row = conn.execute(
                    "SELECT * FROM local_track WHERE local_path LIKE ?", (f"%{filename}",)
                ).fetchone()
            return _row_to_track(row) if row else None


class PlaylistDao:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def create(self, name: str) -> int:
        with connect(self._db_path) as conn:
            cur = conn.execute("INSERT INTO playlist (name) VALUES (?)", (name,))
            conn.commit()
            assert cur.lastrowid is not None
            return cur.lastrowid

    def delete(self, playlist_id: int) -> None:
        with connect(self._db_path) as conn:
            conn.execute("DELETE FROM playlist WHERE id = ?", (playlist_id,))
            conn.commit()

    def list_playlists(self) -> list[Playlist]:
        with connect(self._db_path) as conn:
            rows = conn.execute("SELECT * FROM playlist ORDER BY name").fetchall()
            return [
                Playlist(id=r["id"], name=r["name"], loop_mode=LoopMode(r["loop_mode"]))
                for r in rows
            ]

    def get(self, playlist_id: int) -> Playlist | None:
        with connect(self._db_path) as conn:
            row = conn.execute("SELECT * FROM playlist WHERE id = ?", (playlist_id,)).fetchone()
            if row is None:
                return None
            return Playlist(id=row["id"], name=row["name"], loop_mode=LoopMode(row["loop_mode"]))

    def add_track(self, playlist_id: int, track_id: str) -> None:
        with connect(self._db_path) as conn:
            (next_pos,) = conn.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 FROM playlist_track WHERE playlist_id = ?",
                (playlist_id,),
            ).fetchone()
            conn.execute(
                "INSERT OR IGNORE INTO playlist_track (playlist_id, track_id, position) "
                "VALUES (?, ?, ?)",
                (playlist_id, track_id, next_pos),
            )
            conn.commit()

    def remove_track(self, playlist_id: int, track_id: str) -> None:
        with connect(self._db_path) as conn:
            conn.execute(
                "DELETE FROM playlist_track WHERE playlist_id = ? AND track_id = ?",
                (playlist_id, track_id),
            )
            conn.commit()

    def list_tracks(self, playlist_id: int) -> list[LocalTrack]:
        with connect(self._db_path) as conn:
            rows = conn.execute(
                """
                SELECT lt.* FROM local_track lt
                JOIN playlist_track pt ON pt.track_id = lt.id
                WHERE pt.playlist_id = ?
                ORDER BY pt.position ASC
                """,
                (playlist_id,),
            ).fetchall()
            return [_row_to_track(r) for r in rows]

    def set_order(self, playlist_id: int, ordered_track_ids: list[str]) -> None:
        """Rewrite `position` to match `ordered_track_ids`. This is the only
        thing that mutates manual order — toggling shuffle never calls this,
        so a user's manual arrangement always survives a shuffle toggle.
        """
        with connect(self._db_path) as conn:
            conn.executemany(
                "UPDATE playlist_track SET position = ? WHERE playlist_id = ? AND track_id = ?",
                [(i, playlist_id, tid) for i, tid in enumerate(ordered_track_ids)],
            )
            conn.commit()

    def set_loop_mode(self, playlist_id: int, mode: LoopMode) -> None:
        with connect(self._db_path) as conn:
            conn.execute(
                "UPDATE playlist SET loop_mode = ? WHERE id = ?", (int(mode), playlist_id)
            )
            conn.commit()


class StatsDao:
    """Backs the listening-stats dashboard bonus feature: a log of "track
    started playing" events, aggregated into simple top-artist/top-genre/
    recently-played views. Deliberately just counts play *starts*, not
    listen-through percentage or skip detection - a reasonable, honestly-
    documented simplification rather than something more elaborate.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def log_play(self, track_id: str) -> None:
        with connect(self._db_path) as conn:
            conn.execute("INSERT INTO play_event (track_id) VALUES (?)", (track_id,))
            conn.commit()

    def total_plays(self) -> int:
        with connect(self._db_path) as conn:
            (n,) = conn.execute("SELECT COUNT(*) FROM play_event").fetchone()
            return int(n)

    def total_listening_seconds(self) -> int:
        with connect(self._db_path) as conn:
            (total,) = conn.execute(
                """
                SELECT COALESCE(SUM(lt.duration_seconds), 0)
                FROM play_event pe JOIN local_track lt ON lt.id = pe.track_id
                """
            ).fetchone()
            return int(total)

    def top_artists(self, limit: int = 5) -> list[tuple[str, int]]:
        with connect(self._db_path) as conn:
            rows = conn.execute(
                """
                SELECT lt.artist AS artist, COUNT(*) AS play_count
                FROM play_event pe JOIN local_track lt ON lt.id = pe.track_id
                GROUP BY lt.artist ORDER BY play_count DESC, artist ASC LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [(row["artist"], row["play_count"]) for row in rows]

    def top_genres(self, limit: int = 5) -> list[tuple[str, int]]:
        # genres is stored comma-separated per track (see _row_to_track), so
        # this can't be a plain GROUP BY - tally in Python instead.
        with connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT lt.genres AS genres "
                "FROM play_event pe JOIN local_track lt ON lt.id = pe.track_id"
            ).fetchall()
        counts: dict[str, int] = {}
        for row in rows:
            for genre in _split_csv_field(row["genres"]):
                counts[genre] = counts.get(genre, 0) + 1
        return sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:limit]

    def recent_plays(self, limit: int = 20) -> list[tuple[LocalTrack, str]]:
        with connect(self._db_path) as conn:
            rows = conn.execute(
                """
                SELECT lt.*, pe.played_at AS played_at
                FROM play_event pe JOIN local_track lt ON lt.id = pe.track_id
                ORDER BY pe.id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [(_row_to_track(row), row["played_at"]) for row in rows]


class PlayStateDao:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def save(self, state: PlayState) -> None:
        with connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO play_state
                    (id, current_track_id, position_ms, playlist_id, playlist_index, shuffle_on)
                VALUES (1, ?, ?, ?, ?, ?)
                ON CONFLICT (id) DO UPDATE SET
                    current_track_id = excluded.current_track_id,
                    position_ms = excluded.position_ms,
                    playlist_id = excluded.playlist_id,
                    playlist_index = excluded.playlist_index,
                    shuffle_on = excluded.shuffle_on
                """,
                (
                    state.current_track_id,
                    state.position_ms,
                    state.playlist_id,
                    state.playlist_index,
                    int(state.shuffle_on),
                ),
            )
            conn.commit()

    def load(self) -> PlayState:
        with connect(self._db_path) as conn:
            row = conn.execute("SELECT * FROM play_state WHERE id = 1").fetchone()
            if row is None:
                return PlayState(
                    current_track_id=None,
                    position_ms=0,
                    playlist_id=None,
                    playlist_index=0,
                    shuffle_on=False,
                )
            return PlayState(
                current_track_id=row["current_track_id"],
                position_ms=row["position_ms"],
                playlist_id=row["playlist_id"],
                playlist_index=row["playlist_index"],
                shuffle_on=bool(row["shuffle_on"]),
            )
