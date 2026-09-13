from PySide2.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

from app.api_client import RemoteTrack, SimilarTrack

_TrackRole = 256  # first role above Qt's reserved built-in roles


class SimilarTracksDialog(QDialog):
    """Lists tracks ranked by audio-content similarity to some source track
    (see ApiClient.get_similar_tracks) - the brief's "finding similar songs
    from a random record" bonus feature. Selecting one and accepting the
    dialog downloads it via the caller's DownloadManager.
    """

    def __init__(
        self, source_title: str, results: list[SimilarTrack], parent: object = None
    ) -> None:
        super().__init__(parent)  # type: ignore[arg-type]
        self.setWindowTitle("Similar Tracks")
        self.resize(420, 320)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Tracks that sound like “{source_title}”:"))

        self._list = QListWidget()
        self._list.setAccessibleName("Similar tracks")
        for result in results:
            match_pct = max(0, min(100, round(result.similarity * 100)))
            label = f"{result.track.title} — {result.track.artist} ({match_pct}% match)"
            item = QListWidgetItem(label)
            item.setData(_TrackRole, result.track)
            self._list.addItem(item)
        if not results:
            self._list.addItem("No similar tracks found yet.")
            self._list.setEnabled(False)
        layout.addWidget(self._list)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Download")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_track(self) -> RemoteTrack | None:
        item = self._list.currentItem()
        if item is None:
            return None
        track = item.data(_TrackRole)
        return track if isinstance(track, RemoteTrack) else None
