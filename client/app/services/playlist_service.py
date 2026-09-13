import random
from dataclasses import dataclass
from pathlib import Path

from app.dao import LocalLibraryDao, PlaylistDao
from app.local_models import LocalTrack, LoopMode, Playlist


@dataclass(frozen=True)
class M3uImportResult:
    playlist_id: int
    imported: int
    skipped: int


class PlaylistService:
    def __init__(self, dao: PlaylistDao) -> None:
        self._dao = dao

    def create_playlist(self, name: str) -> int:
        return self._dao.create(name)

    def delete_playlist(self, playlist_id: int) -> None:
        self._dao.delete(playlist_id)

    def list_playlists(self) -> list[Playlist]:
        return self._dao.list_playlists()

    def get(self, playlist_id: int) -> Playlist | None:
        return self._dao.get(playlist_id)

    def add_track(self, playlist_id: int, track_id: str) -> None:
        self._dao.add_track(playlist_id, track_id)

    def remove_track(self, playlist_id: int, track_id: str) -> None:
        self._dao.remove_track(playlist_id, track_id)

    def list_tracks(self, playlist_id: int) -> list[LocalTrack]:
        return self._dao.list_tracks(playlist_id)

    def reorder(self, playlist_id: int, ordered_track_ids: list[str]) -> None:
        """Manual reordering. The only operation that writes `position` —
        see `shuffled_order` below for why shuffle never calls this.
        """
        self._dao.set_order(playlist_id, ordered_track_ids)

    def set_loop_mode(self, playlist_id: int, mode: LoopMode) -> None:
        self._dao.set_loop_mode(playlist_id, mode)

    def shuffled_order(self, playlist_id: int, seed: int | None = None) -> list[str]:
        """Returns a shuffled *view* of the playlist's track ids without
        touching stored order — manual ordering is never destroyed by
        toggling shuffle on and off (see DESIGN.md section 4.2).
        """
        track_ids = [t.id for t in self._dao.list_tracks(playlist_id)]
        random.Random(seed).shuffle(track_ids)
        return track_ids

    def export_m3u(self, playlist_id: int, dest_path: Path) -> int:
        """Writes an Extended M3U — real interoperability with other
        players (VLC, etc.), not just a round-trip format for this app.
        Returns the number of tracks written.
        """
        tracks = self._dao.list_tracks(playlist_id)
        lines = ["#EXTM3U"]
        for track in tracks:
            lines.append(f"#EXTINF:{track.duration_seconds},{track.artist} - {track.title}")
            lines.append(track.local_path)
        dest_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return len(tracks)

    def import_m3u(
        self, path: Path, playlist_name: str, library_dao: LocalLibraryDao
    ) -> M3uImportResult:
        """Creates a new playlist from an .m3u file's entries, matched
        against the *local* library (see LocalLibraryDao.find_by_path_or_
        filename). A line that isn't a track already downloaded here is
        skipped, not fetched — this app only ever plays tracks that came
        through its own download/seed/upload path from the FMA-sourced
        catalog, so import can't silently pull in arbitrary files.
        """
        lines = path.read_text(encoding="utf-8").splitlines()
        entry_paths = [line.strip() for line in lines if line.strip() and not line.startswith("#")]

        playlist_id = self._dao.create(playlist_name)
        imported = skipped = 0
        for entry in entry_paths:
            track = library_dao.find_by_path_or_filename(entry)
            if track is None:
                skipped += 1
                continue
            self._dao.add_track(playlist_id, track.id)
            imported += 1
        return M3uImportResult(playlist_id=playlist_id, imported=imported, skipped=skipped)
