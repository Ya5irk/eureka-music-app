from PySide2.QtCore import Qt
from PySide2.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListView,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QSplitter,
    QStatusBar,
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
from app.ui.upload_dialog import UploadDialog


def _format_ms(ms: int) -> str:
    total_seconds = max(ms, 0) // 1000
    return f"{total_seconds // 60}:{total_seconds % 60:02d}"


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
        self._playlist_service = playlist_service
        self._download_manager = download_manager
        self._upload_manager = upload_manager
        self._player = player

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

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(tabs)
        splitter.addWidget(self._build_playlist_panel())
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(splitter, stretch=1)
        layout.addWidget(self._build_player_bar(), stretch=0)
        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())

    def _build_browse_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        search_row = QHBoxLayout()
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Search title or artist…")
        self._search_edit.returnPressed.connect(self._on_search)
        search_button = QPushButton("Search")
        search_button.clicked.connect(self._on_search)
        search_row.addWidget(self._search_edit)
        search_row.addWidget(search_button)
        layout.addLayout(search_row)

        self._remote_view = QListView()
        self._remote_view.setModel(self._remote_model)
        layout.addWidget(self._remote_view)

        actions_row = QHBoxLayout()
        download_button = QPushButton("Download")
        download_button.clicked.connect(self._on_download_selected)
        upload_button = QPushButton("Upload…")
        upload_button.clicked.connect(self._on_upload_clicked)
        actions_row.addWidget(download_button)
        actions_row.addWidget(upload_button)
        layout.addLayout(actions_row)

        return widget

    def _build_library_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self._local_view = QListView()
        self._local_view.setModel(self._local_model)
        self._local_view.doubleClicked.connect(self._on_local_track_double_clicked)
        layout.addWidget(self._local_view)

        add_button = QPushButton("Add to Selected Playlist")
        add_button.clicked.connect(self._on_add_to_playlist)
        layout.addWidget(add_button)

        return widget

    def _build_playlist_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        header = QHBoxLayout()
        self._playlist_combo = QComboBox()
        self._playlist_combo.currentIndexChanged.connect(self._on_playlist_selected)
        new_button = QPushButton("New…")
        new_button.clicked.connect(self._on_new_playlist)
        header.addWidget(self._playlist_combo)
        header.addWidget(new_button)
        layout.addLayout(header)

        self._playlist_view = QListView()
        self._playlist_view.setModel(self._playlist_tracks_model)
        self._playlist_view.doubleClicked.connect(self._on_playlist_track_double_clicked)
        layout.addWidget(self._playlist_view)

        controls = QHBoxLayout()
        up_button = QPushButton("Up")
        up_button.clicked.connect(lambda: self._on_move_track(-1))
        down_button = QPushButton("Down")
        down_button.clicked.connect(lambda: self._on_move_track(1))
        remove_button = QPushButton("Remove")
        remove_button.clicked.connect(self._on_remove_from_playlist)
        controls.addWidget(up_button)
        controls.addWidget(down_button)
        controls.addWidget(remove_button)
        layout.addLayout(controls)

        options = QHBoxLayout()
        self._shuffle_button = QPushButton("Shuffle")
        self._shuffle_button.setCheckable(True)
        self._shuffle_button.clicked.connect(self._on_toggle_shuffle)
        self._loop_combo = QComboBox()
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
        layout.addWidget(self._now_playing_label)

        seek_row = QHBoxLayout()
        self._position_label = QLabel("0:00")
        self._position_slider = QSlider(Qt.Horizontal)
        self._position_slider.setRange(0, 0)
        self._position_slider.sliderPressed.connect(self._on_seek_pressed)
        self._position_slider.sliderReleased.connect(self._on_seek_released)
        self._duration_label = QLabel("0:00")
        seek_row.addWidget(self._position_label)
        seek_row.addWidget(self._position_slider)
        seek_row.addWidget(self._duration_label)
        layout.addLayout(seek_row)

        transport_row = QHBoxLayout()
        prev_button = QPushButton("Prev")
        prev_button.clicked.connect(self._player.previous)
        self._play_pause_button = QPushButton("Play")
        self._play_pause_button.clicked.connect(self._on_play_pause)
        stop_button = QPushButton("Stop")
        stop_button.clicked.connect(self._player.stop)
        next_button = QPushButton("Next")
        next_button.clicked.connect(self._player.next)
        for button in (prev_button, self._play_pause_button, stop_button, next_button):
            transport_row.addWidget(button)
        layout.addLayout(transport_row)

        return bar

    # -- signal wiring ----------------------------------------------------

    def _wire_signals(self) -> None:
        self._download_manager.completed.connect(self._on_download_completed)
        self._download_manager.failed.connect(self._on_download_failed)
        self._upload_manager.completed.connect(self._on_upload_completed)
        self._upload_manager.failed.connect(self._on_upload_failed)

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
        self._download_manager.download(track)

    def _on_download_completed(self, track: object) -> None:
        self._local_model.prepend_track(track)  # type: ignore[arg-type]
        self.statusBar().showMessage(f"Downloaded {track.title}", 3000)  # type: ignore[attr-defined]

    def _on_download_failed(self, track_id: str, error: str) -> None:
        self.statusBar().showMessage(f"Download failed for {track_id}: {error}", 5000)

    def _on_upload_clicked(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose a track to upload", "", "Audio (*.mp3)")
        if not path:
            return
        dialog = UploadDialog(self)
        if dialog.exec_() != UploadDialog.Accepted:
            return
        title, artist, album, genres = dialog.values()
        self.statusBar().showMessage(f"Uploading {title}…")
        self._upload_manager.upload(path, title, artist, album or None, genres or None)

    def _on_upload_completed(self, track: object) -> None:
        self.statusBar().showMessage(f"Uploaded {track.title}", 3000)  # type: ignore[attr-defined]
        self._remote_model.set_search(self._search_edit.text().strip() or None)

    def _on_upload_failed(self, error: str) -> None:
        QMessageBox.warning(self, "Upload failed", error)

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
        self._playlist_view.setCurrentIndex(self._playlist_tracks_model.index(new_row))

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
            self._play_pause_button.setText("Play")
        else:
            self._player.play()
            self._play_pause_button.setText("Pause")

    def _on_track_changed(self, track: object) -> None:
        self._now_playing_label.setText(f"{track.title} — {track.artist}")  # type: ignore[attr-defined]
        self._play_pause_button.setText("Pause")

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
