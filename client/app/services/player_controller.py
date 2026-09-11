import random

from PySide2.QtCore import QObject, QUrl, Signal
from PySide2.QtMultimedia import QMediaContent, QMediaPlayer

from app.dao import LocalLibraryDao, PlaylistDao, PlayStateDao
from app.local_models import LocalTrack, LoopMode, PlayState

_POSITION_SAVE_EVERY_N_TICKS = 4  # QMediaPlayer notifies ~4x/sec -> persist ~1x/sec


class PlayerController(QObject):
    trackChanged = Signal(object)  # LocalTrack | None
    positionChanged = Signal(int)  # ms
    durationChanged = Signal(int)  # ms
    queueChanged = Signal(list)  # list[str] track ids, current playback order

    def __init__(
        self,
        library_dao: LocalLibraryDao,
        playlist_dao: PlaylistDao,
        state_dao: PlayStateDao,
    ) -> None:
        super().__init__()
        self._library = library_dao
        self._playlist_dao = playlist_dao
        self._state_dao = state_dao

        self._player = QMediaPlayer()
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.mediaStatusChanged.connect(self._on_media_status_changed)
        self._player.durationChanged.connect(self.durationChanged.emit)

        self._queue: list[str] = []
        self._index: int = 0
        self._playlist_id: int | None = None
        self._loop_mode = LoopMode.NONE
        self._shuffle_on = False
        self._tick_count = 0

    # -- queue / transport -------------------------------------------------

    def set_queue(
        self, track_ids: list[str], start_index: int = 0, playlist_id: int | None = None
    ) -> None:
        self._queue = list(track_ids)
        self._playlist_id = playlist_id
        self.queueChanged.emit(self._queue)
        self._play_index(start_index)

    def play(self) -> None:
        self._player.play()

    def pause(self) -> None:
        self._player.pause()

    def stop(self) -> None:
        self._player.stop()

    def seek(self, position_ms: int) -> None:
        self._player.setPosition(position_ms)
        self._persist(position_ms)

    def next(self) -> None:
        if not self._queue:
            return
        if self._index + 1 < len(self._queue):
            self._play_index(self._index + 1)
        elif self._loop_mode == LoopMode.PLAYLIST:
            self._play_index(0)
        else:
            self.stop()

    def previous(self) -> None:
        if self._queue and self._index - 1 >= 0:
            self._play_index(self._index - 1)

    def set_loop_mode(self, mode: LoopMode) -> None:
        self._loop_mode = mode

    def is_playing(self) -> bool:
        return bool(self._player.state() == QMediaPlayer.PlayingState)

    def toggle_shuffle(self) -> bool:
        """Reorders only the in-memory playback queue. Never calls
        PlaylistDao.set_order, so the playlist's manually-set order in
        SQLite is untouched by shuffling — see DESIGN.md section 4.2.
        """
        self._shuffle_on = not self._shuffle_on
        if self._shuffle_on and self._queue:
            current = self._queue[self._index]
            rest = [t for t in self._queue if t != current]
            random.shuffle(rest)
            self._queue = [current, *rest]
            self._index = 0
            self.queueChanged.emit(self._queue)
        return self._shuffle_on

    # -- crash-safe resume ---------------------------------------------------

    def restore_last_state(self) -> None:
        state = self._state_dao.load()
        if state.current_track_id is None:
            return

        if state.playlist_id is not None:
            track_ids = [t.id for t in self._playlist_dao.list_tracks(state.playlist_id)]
        else:
            track_ids = [state.current_track_id]

        self._shuffle_on = state.shuffle_on
        start_index = min(state.playlist_index, max(len(track_ids) - 1, 0))
        self.set_queue(track_ids, start_index=start_index, playlist_id=state.playlist_id)
        self._player.pause()  # restore paused, not auto-playing on launch
        self._player.setPosition(state.position_ms)

    # -- internals -----------------------------------------------------------

    def _play_index(self, index: int) -> None:
        if not (0 <= index < len(self._queue)):
            return
        self._index = index
        track = self._library.get(self._queue[index])
        if track is None:
            return
        self._player.setMedia(QMediaContent(QUrl.fromLocalFile(track.local_path)))
        self._player.play()
        self.trackChanged.emit(track)
        self._persist(position_ms=0)

    def _current_track(self) -> LocalTrack | None:
        if not self._queue:
            return None
        return self._library.get(self._queue[self._index])

    def _on_position_changed(self, position_ms: int) -> None:
        self.positionChanged.emit(position_ms)
        self._tick_count += 1
        if self._tick_count % _POSITION_SAVE_EVERY_N_TICKS == 0:
            self._persist(position_ms)

    def _on_media_status_changed(self, status: QMediaPlayer.MediaStatus) -> None:
        if status != QMediaPlayer.EndOfMedia:
            return
        if self._loop_mode == LoopMode.TRACK:
            self._play_index(self._index)
        else:
            self.next()

    def _persist(self, position_ms: int) -> None:
        current_id = self._queue[self._index] if self._queue else None
        self._state_dao.save(
            PlayState(
                current_track_id=current_id,
                position_ms=position_ms,
                playlist_id=self._playlist_id,
                playlist_index=self._index,
                shuffle_on=self._shuffle_on,
            )
        )
