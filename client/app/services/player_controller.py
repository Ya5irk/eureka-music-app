import random

from PySide2.QtCore import QObject, QUrl, Signal
from PySide2.QtMultimedia import (
    QAudioBuffer,
    QAudioFormat,
    QAudioProbe,
    QMediaContent,
    QMediaPlayer,
)

from app.audio_levels import pcm_bytes_to_levels
from app.dao import LocalLibraryDao, PlaylistDao, PlayStateDao, StatsDao
from app.local_models import LocalTrack, LoopMode, PlayState

_POSITION_SAVE_EVERY_N_TICKS = 4  # QMediaPlayer notifies ~4x/sec -> persist ~1x/sec


class PlayerController(QObject):
    trackChanged = Signal(object)  # LocalTrack | None
    positionChanged = Signal(int)  # ms
    durationChanged = Signal(int)  # ms
    queueChanged = Signal(list)  # list[str] track ids, current playback order
    audioLevelsChanged = Signal(list)  # list[float] in [0, 1] - see app/audio_levels.py

    def __init__(
        self,
        library_dao: LocalLibraryDao,
        playlist_dao: PlaylistDao,
        state_dao: PlayStateDao,
        stats_dao: StatsDao | None = None,
    ) -> None:
        super().__init__()
        self._library = library_dao
        self._playlist_dao = playlist_dao
        self._state_dao = state_dao
        self._stats_dao = stats_dao

        self._player = QMediaPlayer()
        self._player.setVolume(100)
        self._player.setMuted(False)
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.mediaStatusChanged.connect(self._on_media_status_changed)
        self._player.durationChanged.connect(self.durationChanged.emit)

        # Visualizer data source ("music visualizer" bonus feature). Whether
        # this backend actually delivers probed buffers is a real open
        # question (this project has already hit GStreamer-backend quirks
        # elsewhere - duration()/pause() - that no amount of doc-reading
        # predicted); MainWindow times out and shows a fallback message if
        # audioLevelsChanged never fires after playback starts.
        self._probe = QAudioProbe()
        self._probe.audioBufferProbed.connect(self._on_audio_buffer)
        self._probe.setSource(self._player)

        self._queue: list[str] = []
        self._index: int = 0
        self._playlist_id: int | None = None
        self._loop_mode = LoopMode.NONE
        self._shuffle_on = False
        self._tick_count = 0
        self._pending_seek_ms: int | None = None

    # -- queue / transport -------------------------------------------------

    def set_queue(
        self,
        track_ids: list[str],
        start_index: int = 0,
        playlist_id: int | None = None,
        start_playing: bool = True,
    ) -> None:
        self._queue = list(track_ids)
        self._playlist_id = playlist_id
        self.queueChanged.emit(self._queue)
        self._play_index(start_index, start_playing=start_playing)

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
        Toggling back off restores the real manual order (re-read from the
        DAO) rather than leaving the queue stuck in its shuffled order.
        """
        self._shuffle_on = not self._shuffle_on
        if not self._queue:
            return self._shuffle_on

        current = self._queue[self._index]
        if self._shuffle_on:
            rest = [t for t in self._queue if t != current]
            random.shuffle(rest)
            self._queue = [current, *rest]
            self._index = 0
        elif self._playlist_id is not None:
            self._queue = [t.id for t in self._playlist_dao.list_tracks(self._playlist_id)]
            self._index = self._queue.index(current) if current in self._queue else 0
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
        # The actual seek happens in _on_position_changed once the pipeline
        # proves it's really running - see _play_index's docstring for why
        # that's the only reliable signal on this backend. start_playing is
        # irrelevant here: whenever _pending_seek_ms is set, _play_index
        # always mutes+plays regardless, so the value doesn't matter, but
        # False documents the intent (end up paused, not auto-playing).
        self._pending_seek_ms = state.position_ms
        self.set_queue(
            track_ids, start_index=start_index, playlist_id=state.playlist_id, start_playing=False
        )
        self._persist(state.position_ms)  # _play_index above just persisted position 0

    # -- internals -----------------------------------------------------------

    def _play_index(self, index: int, start_playing: bool = True) -> None:
        if not (0 <= index < len(self._queue)):
            return
        self._index = index
        track = self._library.get(self._queue[index])
        if track is None:
            return
        # Loading new media into a player that's still actively playing (no
        # prior stop()) can stall GStreamer's pipeline teardown/rebuild
        # indefinitely on some backends - always stop first.
        self._player.stop()
        if self._pending_seek_ms is not None:
            # Confirmed live, empirically, on real Ubuntu: this backend
            # never reports a valid duration() for these files, and
            # pause() alone (without ever calling play()) never advances
            # position at all - the pipeline simply never starts. play()
            # is the only thing that actually gets it running, so we mute
            # first and let _on_position_changed apply the real seek and
            # pause once the first genuine position tick proves the
            # pipeline is live - never any audible sound in between.
            self._player.setMuted(True)
            self._player.setMedia(QMediaContent(QUrl.fromLocalFile(track.local_path)))
            self._player.play()
        else:
            self._player.setMedia(QMediaContent(QUrl.fromLocalFile(track.local_path)))
            if start_playing:
                self._player.play()
            else:
                self._player.pause()
            # Only the genuine "start playing this track now" path (never
            # the crash-resume branch above, which is restoring state, not
            # a new listen) counts toward the stats dashboard.
            if self._stats_dao is not None:
                self._stats_dao.log_play(track.id)
        self.trackChanged.emit(track)
        self._persist(position_ms=0)

    def current_track(self) -> LocalTrack | None:
        if not self._queue:
            return None
        return self._library.get(self._queue[self._index])

    def recently_played_ids(self, limit: int = 20) -> list[str]:
        """The queue's last `limit` played track ids up to and including the
        current one, in play order - used to avoid re-recommending a track
        just played (see MainWindow's "Recommend Next" action).
        """
        return self._queue[max(0, self._index - limit + 1) : self._index + 1]

    def _on_position_changed(self, position_ms: int) -> None:
        if self._pending_seek_ms is not None:
            # The first tick at all proves the muted play() in _play_index
            # actually got the pipeline running - safe to seek now, then
            # settle into the paused state restore_last_state wants,
            # without this transient tick being mistaken for real playback.
            target = self._pending_seek_ms
            self._pending_seek_ms = None
            self._player.setPosition(target)
            self._player.pause()
            self._player.setMuted(False)
            return

        self.positionChanged.emit(position_ms)
        self._tick_count += 1
        if self._tick_count % _POSITION_SAVE_EVERY_N_TICKS == 0:
            self._persist(position_ms)

    def _on_audio_buffer(self, buffer: QAudioBuffer) -> None:
        if not buffer.isValid():
            return
        fmt = buffer.format()
        ptr = buffer.constData()
        try:
            # PySide2-stubs types constData() as a plain int (it's really a
            # shiboken2 VoidPtr at runtime, which does have .setsize()).
            ptr.setsize(buffer.byteCount())  # type: ignore[attr-defined]
            raw = bytes(ptr)
        except (AttributeError, TypeError, ValueError):
            return  # unexpected buffer shape on this backend - skip this frame

        levels = pcm_bytes_to_levels(
            raw,
            sample_size_bits=fmt.sampleSize(),
            channel_count=fmt.channelCount(),
            is_float=fmt.sampleType() == QAudioFormat.Float,
            is_signed=fmt.sampleType() == QAudioFormat.SignedInt,
        )
        self.audioLevelsChanged.emit(levels)

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
