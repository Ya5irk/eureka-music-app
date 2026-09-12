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
