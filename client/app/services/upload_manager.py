from pathlib import Path

from PySide2.QtCore import QObject, QThreadPool, Signal

from app.api_client import ApiClient
from app.workers import Worker


class UploadManager(QObject):
    completed = Signal(object)  # RemoteTrack
    failed = Signal(str)

    def __init__(self, api: ApiClient, thread_pool: QThreadPool | None = None) -> None:
        super().__init__()
        self._api = api
        self._pool = thread_pool or QThreadPool.globalInstance()

    def upload(
        self,
        file_path: Path,
        title: str,
        artist: str,
        album: str | None = None,
        genres: list[str] | None = None,
    ) -> None:
        worker = Worker(self._api.upload_track, file_path, title, artist, album, genres)
        worker.signals.result.connect(self.completed.emit)
        worker.signals.error.connect(self.failed.emit)
        self._pool.start(worker)
