import random

from app.dao import PlaylistDao
from app.local_models import LocalTrack, LoopMode, Playlist


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
