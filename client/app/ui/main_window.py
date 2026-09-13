from pathlib import Path

from PySide2.QtCore import QAbstractTableModel, Qt, QThreadPool
from PySide2.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QStatusBar,
    QStyle,
    QTableView,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.api_client import ApiClient
from app.dao import LocalLibraryDao
from app.local_models import LoopMode
from app.services.download_manager import DownloadManager
from app.services.player_controller import PlayerController
from app.services.playlist_service import PlaylistService
from app.services.upload_manager import UploadManager
from app.ui.models import LocalLibraryModel, PlaylistTracksModel, RemoteLibraryModel
from app.ui.similar_tracks_dialog import SimilarTracksDialog
from app.ui.upload_dialog import UploadDialog
from app.workers import Worker


def _format_ms(ms: int) -> str:
    total_seconds = max(ms, 0) // 1000
    return f"{total_seconds // 60}:{total_seconds % 60:02d}"


def _make_track_table(model: QAbstractTableModel, accessible_name: str) -> QTableView:
    """A real multi-column table (Title/Artist/Album/Year/Genres/Duration)
    rather than a single "Title — Artist" text line, shared setup for the
    three track views (Browse/Library/Playlist). License and tags (also
    real dataset fields) show as a tooltip on hover instead of two more
    columns — see _track_tooltip in ui/models.py.
    """
    view = QTableView()
    view.setModel(model)
    view.setAccessibleName(accessible_name)
    view.setSelectionBehavior(QAbstractItemView.SelectRows)
    view.setSelectionMode(QAbstractItemView.SingleSelection)
    view.setEditTriggers(QAbstractItemView.NoEditTriggers)
    view.verticalHeader().setVisible(False)
    header = view.horizontalHeader()
    # Title carries the most information and gets whatever space is left;
    # Artist/Album/Genres get sensible, user-resizable starting widths
    # instead of being forced equal to Title regardless of content;
    # Year/Duration only ever need to fit a handful of characters.
    header.setSectionResizeMode(0, QHeaderView.Stretch)
    header.setSectionResizeMode(1, QHeaderView.Interactive)
    header.setSectionResizeMode(2, QHeaderView.Interactive)
    header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
    header.setSectionResizeMode(4, QHeaderView.Interactive)
    header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
    view.setColumnWidth(1, 140)
    view.setColumnWidth(2, 140)
    view.setColumnWidth(4, 150)
    return view


class MainWindow(QMainWindow):
    def __init__(
        self,
        api: ApiClient,
        library_dao: LocalLibraryDao,
        playlist_service: PlaylistService,
        download_manager: DownloadManager,
        upload_manager: UploadManager,
        player: PlayerController,
    ) -> None:
        super().__init__()
        self.setWindowTitle("Eureka Music")

        self._api = api
        self._library_dao = library_dao
        self._playlist_service = playlist_service
        self._download_manager = download_manager
        self._upload_manager = upload_manager
        self._player = player
        self._pool = QThreadPool.globalInstance()
        self._pending_recommend_track_id: str | None = None

        self._remote_model = RemoteLibraryModel(api)
        self._local_model = LocalLibraryModel(library_dao)
        self._playlist_tracks_model = PlaylistTracksModel(playlist_service)

        self._build_ui()
        self._wire_signals()

        self._local_model.set_query(None)
        self._refresh_playlists()

    # -- construction ---------------------------------------------------

    def _build_ui(self) -> None:
        tabs = QTabWidget()
        tabs.addTab(self._build_browse_tab(), "Browse")
        tabs.addTab(self._build_library_tab(), "Library")
        tabs.addTab(self._build_playlist_tab(), "Playlists")

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(tabs, stretch=1)
        layout.addWidget(self._build_player_bar(), stretch=0)
        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())

    def _build_browse_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        caption = QLabel("Search the server's catalog, then download a track to play it.")
        caption.setObjectName("emptyStateLabel")
        layout.addWidget(caption)

        search_row = QHBoxLayout()
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Search title or artist…")
        self._search_edit.setAccessibleName("Search the catalog")
        self._search_edit.returnPressed.connect(self._on_search)
        search_button = QPushButton("Search")
        search_button.setDefault(True)
        search_button.clicked.connect(self._on_search)
        search_row.addWidget(self._search_edit)
        search_row.addWidget(search_button)
        layout.addLayout(search_row)

        self._remote_view = _make_track_table(self._remote_model, "Catalog search results")
        layout.addWidget(self._remote_view)

        self._download_progress = QProgressBar()
        self._download_progress.setRange(0, 100)
        self._download_progress.hide()
        layout.addWidget(self._download_progress)

        actions_row = QHBoxLayout()
        download_button = QPushButton("Download")
        download_button.setToolTip("Download the selected track so it can be played locally")
        download_button.clicked.connect(self._on_download_selected)
        upload_button = QPushButton("Upload…")
        upload_button.setToolTip("Upload a local audio file to the server's catalog")
        upload_button.clicked.connect(self._on_upload_clicked)
        similar_button = QPushButton("Similar Tracks…")
        similar_button.setToolTip(
            "Find tracks that sound like the selected one, by audio content"
        )
        similar_button.clicked.connect(self._on_similar_tracks_clicked)
        actions_row.addWidget(download_button)
        actions_row.addWidget(upload_button)
        actions_row.addWidget(similar_button)
        layout.addLayout(actions_row)

        return widget

    def _build_library_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        caption = QLabel("Your downloaded tracks. Double-click one to play it.")
        caption.setObjectName("emptyStateLabel")
        layout.addWidget(caption)

        self._local_view = _make_track_table(self._local_model, "Downloaded tracks")
        self._local_view.doubleClicked.connect(self._on_local_track_double_clicked)
        layout.addWidget(self._local_view)

        add_button = QPushButton("Add to Selected Playlist")
        add_button.setToolTip("Add the selected track to the playlist chosen in the Playlists tab")
        add_button.clicked.connect(self._on_add_to_playlist)
        layout.addWidget(add_button)

        return widget

    def _build_playlist_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        header = QHBoxLayout()
        self._playlist_combo = QComboBox()
        self._playlist_combo.setAccessibleName("Selected playlist")
        self._playlist_combo.currentIndexChanged.connect(self._on_playlist_selected)
        new_button = QPushButton("New…")
        new_button.setToolTip("Create a new playlist")
        new_button.clicked.connect(self._on_new_playlist)
        header.addWidget(self._playlist_combo)
        header.addWidget(new_button)
        layout.addLayout(header)

        self._playlist_empty_label = QLabel("No playlists yet — click “New…” to create one.")
        self._playlist_empty_label.setObjectName("emptyStateLabel")
        self._playlist_empty_label.setAlignment(Qt.AlignCenter)
        self._playlist_empty_label.setWordWrap(True)
        layout.addWidget(self._playlist_empty_label)

        self._playlist_view = _make_track_table(
            self._playlist_tracks_model, "Tracks in this playlist"
        )
        self._playlist_view.doubleClicked.connect(self._on_playlist_track_double_clicked)
        layout.addWidget(self._playlist_view)

        controls = QHBoxLayout()
        up_button = QPushButton("Up")
        up_button.setToolTip("Move the selected track earlier in the playlist")
        up_button.clicked.connect(lambda: self._on_move_track(-1))
        down_button = QPushButton("Down")
        down_button.setToolTip("Move the selected track later in the playlist")
        down_button.clicked.connect(lambda: self._on_move_track(1))
        remove_button = QPushButton("Remove")
        remove_button.setToolTip("Remove the selected track from this playlist")
        remove_button.clicked.connect(self._on_remove_from_playlist)
        controls.addWidget(up_button)
        controls.addWidget(down_button)
        controls.addWidget(remove_button)
        layout.addLayout(controls)

        options = QHBoxLayout()
        self._shuffle_button = QPushButton("Shuffle")
        self._shuffle_button.setCheckable(True)
        self._shuffle_button.setToolTip("Play this playlist in random order")
        self._shuffle_button.clicked.connect(self._on_toggle_shuffle)
        self._loop_combo = QComboBox()
        self._loop_combo.setAccessibleName("Loop mode")
        self._loop_combo.addItems(["No loop", "Loop track", "Loop playlist"])
        self._loop_combo.currentIndexChanged.connect(self._on_loop_mode_changed)
        options.addWidget(self._shuffle_button)
        options.addWidget(self._loop_combo)
        layout.addLayout(options)

        play_button = QPushButton("Play Playlist")
        play_button.clicked.connect(self._on_play_playlist)
        layout.addWidget(play_button)

        return widget

    def _build_player_bar(self) -> QWidget:
        bar = QWidget()
        layout = QVBoxLayout(bar)

        self._now_playing_label = QLabel("Nothing playing")
        self._now_playing_label.setObjectName("nowPlayingLabel")
        layout.addWidget(self._now_playing_label)

        seek_row = QHBoxLayout()
        self._position_label = QLabel("0:00")
        self._position_slider = QSlider(Qt.Horizontal)
        self._position_slider.setRange(0, 0)
        self._position_slider.setAccessibleName("Playback position")
        self._position_slider.setToolTip("Drag to seek to a specific time")
        self._position_slider.sliderPressed.connect(self._on_seek_pressed)
        self._position_slider.sliderReleased.connect(self._on_seek_released)
        self._duration_label = QLabel("0:00")
        seek_row.addWidget(self._position_label)
        seek_row.addWidget(self._position_slider)
        seek_row.addWidget(self._duration_label)
        layout.addLayout(seek_row)

        # Qt's own bundled standard icons, not custom artwork - reliable
        # everywhere (unlike the Unicode glyphs an earlier pass used, which
        # rendered blank on a system lacking those font glyphs).
        style = self.style()
        transport_row = QHBoxLayout()
        prev_button = QPushButton()
        prev_button.setIcon(style.standardIcon(QStyle.SP_MediaSkipBackward))
        prev_button.setToolTip("Previous track")
        prev_button.setAccessibleName("Previous track")
        prev_button.clicked.connect(self._player.previous)
        self._play_pause_button = QPushButton()
        self._play_icon = style.standardIcon(QStyle.SP_MediaPlay)
        self._pause_icon = style.standardIcon(QStyle.SP_MediaPause)
        self._play_pause_button.setIcon(self._play_icon)
        self._play_pause_button.setToolTip("Play or pause the current track")
        self._play_pause_button.setAccessibleName("Play or pause")
        self._play_pause_button.clicked.connect(self._on_play_pause)
        stop_button = QPushButton()
        stop_button.setIcon(style.standardIcon(QStyle.SP_MediaStop))
        stop_button.setToolTip("Stop playback")
        stop_button.setAccessibleName("Stop")
        stop_button.clicked.connect(self._player.stop)
        next_button = QPushButton()
        next_button.setIcon(style.standardIcon(QStyle.SP_MediaSkipForward))
        next_button.setToolTip("Next track")
        next_button.setAccessibleName("Next track")
        next_button.clicked.connect(self._player.next)
        recommend_button = QPushButton("Recommend Next")
        recommend_button.setToolTip(
            "Find and queue a track that sounds like what's currently playing"
        )
        recommend_button.clicked.connect(self._on_recommend_next_clicked)
        for button in (prev_button, self._play_pause_button, stop_button, next_button):
            transport_row.addWidget(button)
        transport_row.addWidget(recommend_button)
        layout.addLayout(transport_row)

        return bar

    # -- signal wiring ----------------------------------------------------

    def _wire_signals(self) -> None:
        self._download_manager.progress.connect(self._on_download_progress)
        self._download_manager.completed.connect(self._on_download_completed)
        self._download_manager.failed.connect(self._on_download_failed)
        self._upload_manager.completed.connect(self._on_upload_completed)
        self._upload_manager.failed.connect(self._on_upload_failed)
        self._remote_model.errorOccurred.connect(self._on_search_error)

        self._player.trackChanged.connect(self._on_track_changed)
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)

        self._seeking = False

    # -- browse / download / upload ---------------------------------------

    def _on_search(self) -> None:
        self._remote_model.set_search(self._search_edit.text().strip() or None)

    def _on_download_selected(self) -> None:
        index = self._remote_view.currentIndex()
        if not index.isValid():
            return
        track = self._remote_model.track_at(index.row())
        self.statusBar().showMessage(f"Downloading {track.title}…")
        self._download_progress.setValue(0)
        self._download_progress.show()
        self._download_manager.download(track)

    def _on_download_progress(self, track_id: str, done: int, total: int) -> None:
        if total > 0:
            self._download_progress.setValue(int(done * 100 / total))

    def _on_download_completed(self, track: object) -> None:
        self._local_model.prepend_track(track)  # type: ignore[arg-type]
        self._download_progress.hide()
        self.statusBar().showMessage(f"Downloaded {track.title}", 3000)  # type: ignore[attr-defined]
        if track.id == self._pending_recommend_track_id:  # type: ignore[attr-defined]
            self._pending_recommend_track_id = None
            self._player.set_queue([track.id], playlist_id=None)  # type: ignore[attr-defined]

    def _on_download_failed(self, track_id: str, error: str) -> None:
        self._download_progress.hide()
        self.statusBar().showMessage(f"Download failed for {track_id}: {error}", 5000)

    def _on_search_error(self, message: str) -> None:
        self.statusBar().showMessage(f"Search failed: {message}", 5000)

    def _on_upload_clicked(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose a track to upload", "", "Audio (*.mp3)")
        if not path:
            return
        dialog = UploadDialog(self)
        if dialog.exec_() != UploadDialog.Accepted:
            return
        title, artist, album, genres = dialog.values()
        self.statusBar().showMessage(f"Uploading {title}…")
        self._upload_manager.upload(Path(path), title, artist, album or None, genres or None)

    def _on_upload_completed(self, track: object) -> None:
        self.statusBar().showMessage(f"Uploaded {track.title}", 3000)  # type: ignore[attr-defined]
        self._remote_model.set_search(self._search_edit.text().strip() or None)

    def _on_upload_failed(self, error: str) -> None:
        QMessageBox.warning(self, "Upload failed", error)

    def _on_similar_tracks_clicked(self) -> None:
        index = self._remote_view.currentIndex()
        if not index.isValid():
            return
        track = self._remote_model.track_at(index.row())
        self.statusBar().showMessage(f"Finding tracks similar to {track.title}…")
        worker = Worker(self._api.get_similar_tracks, track.id)
        worker.signals.result.connect(
            lambda results: self._on_similar_tracks_result(track.title, results)
        )
        worker.signals.error.connect(
            lambda err: self.statusBar().showMessage(f"Similarity search failed: {err}", 5000)
        )
        self._pool.start(worker)

    def _on_similar_tracks_result(self, source_title: str, results: object) -> None:
        self.statusBar().clearMessage()
        dialog = SimilarTracksDialog(source_title, results, self)  # type: ignore[arg-type]
        if dialog.exec_() == SimilarTracksDialog.Accepted:
            track = dialog.selected_track()
            if track is not None:
                self.statusBar().showMessage(f"Downloading {track.title}…")
                self._download_progress.setValue(0)
                self._download_progress.show()
                self._download_manager.download(track)

    # -- library / playlists -----------------------------------------------

    def _on_local_track_double_clicked(self, index: object) -> None:
        row = index.row()  # type: ignore[attr-defined]
        track = self._local_model.track_at(row)
        self._player.set_queue([track.id], playlist_id=None)

    def _refresh_playlists(self) -> None:
        current_id = self._current_playlist_id()
        self._playlist_combo.blockSignals(True)
        self._playlist_combo.clear()
        for playlist in self._playlist_service.list_playlists():
            self._playlist_combo.addItem(playlist.name, playlist.id)
        self._playlist_combo.blockSignals(False)
        if current_id is not None:
            idx = self._playlist_combo.findData(current_id)
            if idx >= 0:
                self._playlist_combo.setCurrentIndex(idx)
        has_playlists = self._playlist_combo.count() > 0
        self._playlist_empty_label.setVisible(not has_playlists)
        self._playlist_combo.setVisible(has_playlists)
        self._on_playlist_selected()

    def _current_playlist_id(self) -> int | None:
        return self._playlist_combo.currentData()

    def _on_new_playlist(self) -> None:
        name, ok = QInputDialog.getText(self, "New Playlist", "Name:", QLineEdit.Normal, "")
        if ok and name.strip():
            self._playlist_service.create_playlist(name.strip())
            self._refresh_playlists()

    def _on_playlist_selected(self) -> None:
        self._playlist_tracks_model.load(self._current_playlist_id())

    def _on_add_to_playlist(self) -> None:
        playlist_id = self._current_playlist_id()
        index = self._local_view.currentIndex()
        if playlist_id is None or not index.isValid():
            return
        track = self._local_model.track_at(index.row())
        self._playlist_service.add_track(playlist_id, track.id)
        self._playlist_tracks_model.load(playlist_id)

    def _on_remove_from_playlist(self) -> None:
        playlist_id = self._current_playlist_id()
        index = self._playlist_view.currentIndex()
        if playlist_id is None or not index.isValid():
            return
        track = self._playlist_tracks_model.track_at(index.row())
        self._playlist_service.remove_track(playlist_id, track.id)
        self._playlist_tracks_model.load(playlist_id)

    def _on_move_track(self, delta: int) -> None:
        index = self._playlist_view.currentIndex()
        if not index.isValid():
            return
        new_row = self._playlist_tracks_model.move(index.row(), delta)
        self._playlist_view.setCurrentIndex(self._playlist_tracks_model.index(new_row, 0))

    def _on_toggle_shuffle(self) -> None:
        self._player.toggle_shuffle()

    def _on_loop_mode_changed(self, index: int) -> None:
        self._player.set_loop_mode(LoopMode(index))
        playlist_id = self._current_playlist_id()
        if playlist_id is not None:
            self._playlist_service.set_loop_mode(playlist_id, LoopMode(index))

    def _on_play_playlist(self) -> None:
        playlist_id = self._current_playlist_id()
        track_ids = self._playlist_tracks_model.track_ids()
        if playlist_id is None or not track_ids:
            return
        self._player.set_queue(track_ids, start_index=0, playlist_id=playlist_id)

    def _on_playlist_track_double_clicked(self, index: object) -> None:
        playlist_id = self._current_playlist_id()
        if playlist_id is None:
            return
        row = index.row()  # type: ignore[attr-defined]
        self._player.set_queue(
            self._playlist_tracks_model.track_ids(), start_index=row, playlist_id=playlist_id
        )

    # -- player bar ----------------------------------------------------------

    def _on_play_pause(self) -> None:
        if self._player.is_playing():
            self._player.pause()
            self._play_pause_button.setIcon(self._play_icon)
        else:
            self._player.play()
            self._play_pause_button.setIcon(self._pause_icon)

    def _on_track_changed(self, track: object) -> None:
        self._now_playing_label.setText(f"{track.title} — {track.artist}")  # type: ignore[attr-defined]
        self._play_pause_button.setIcon(self._pause_icon)

    def _on_position_changed(self, ms: int) -> None:
        if not self._seeking:
            self._position_slider.setValue(ms)
        self._position_label.setText(_format_ms(ms))

    def _on_duration_changed(self, ms: int) -> None:
        self._position_slider.setRange(0, ms)
        self._duration_label.setText(_format_ms(ms))

    def _on_seek_pressed(self) -> None:
        self._seeking = True

    def _on_seek_released(self) -> None:
        self._seeking = False
        self._player.seek(self._position_slider.value())

    def _on_recommend_next_clicked(self) -> None:
        current = self._player.current_track()
        if current is None:
            self.statusBar().showMessage("Nothing is playing to base a recommendation on", 4000)
            return
        exclude = self._player.recently_played_ids()
        self.statusBar().showMessage("Finding a recommended track…")
        worker = Worker(self._api.get_recommend_next, current.id, exclude)
        worker.signals.result.connect(self._on_recommend_next_result)
        worker.signals.error.connect(
            lambda err: self.statusBar().showMessage(f"Recommendation failed: {err}", 5000)
        )
        self._pool.start(worker)

    def _on_recommend_next_result(self, result: object) -> None:
        if result is None:
            self.statusBar().showMessage("No recommendation available yet for this track", 4000)
            return
        track = result.track  # type: ignore[attr-defined]
        if self._library_dao.get(track.id) is not None:
            self.statusBar().showMessage(f"Playing recommended track: {track.title}", 4000)
            self._player.set_queue([track.id], playlist_id=None)
            return
        self.statusBar().showMessage(f"Downloading recommended track: {track.title}…")
        self._pending_recommend_track_id = track.id
        self._download_progress.setValue(0)
        self._download_progress.show()
        self._download_manager.download(track)
