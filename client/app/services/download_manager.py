from pathlib import Path

from PySide2.QtCore import QObject, QThreadPool, Signal

from app.api_client import ApiClient, RemoteTrack
from app.dao import LocalLibraryDao
from app.local_models import LocalTrack
from app.workers import Worker


class DownloadManager(QObject):
    progress = Signal(str, int, int)  # track_id, bytes_done, bytes_total
    completed = Signal(object)  # LocalTrack
    failed = Signal(str, str)  # track_id, error

    def __init__(
        self,
        api: ApiClient,
        library_dao: LocalLibraryDao,
        downloads_dir: Path,
        thread_pool: QThreadPool | None = None,
    ) -> None:
        super().__init__()
        self._api = api
        self._library = library_dao
        self._downloads_dir = downloads_dir
        self._pool = thread_pool or QThreadPool.globalInstance()

    def download(self, remote: RemoteTrack) -> None:
        existing = self._library.find_by_checksum(remote.checksum_sha256)
        if existing is not None:
            self.completed.emit(existing)
            return

        worker = Worker(self._download_and_store, remote)
        worker.signals.result.connect(self.completed.emit)
        worker.signals.error.connect(lambda msg: self.failed.emit(remote.id, msg))
        self._pool.start(worker)

    def _download_and_store(self, remote: RemoteTrack) -> LocalTrack:
        dest = self._downloads_dir / f"{remote.checksum_sha256}.mp3"

        def on_progress(done: int, total: int) -> None:
            self.progress.emit(remote.id, done, total)

        self._api.download_track(remote.id, dest, on_progress)

        track = LocalTrack(
            id=remote.id,
            title=remote.title,
            artist=remote.artist,
            album=remote.album,
            duration_seconds=remote.duration_seconds,
            local_path=str(dest),
            checksum_sha256=remote.checksum_sha256,
            downloaded_at="",
            release_year=remote.release_year,
            license=remote.license,
            tags=remote.tags,
            genres=remote.genres,
        )
        self._library.insert_track(track)
        stored = self._library.get(remote.id)
        assert stored is not None
        return stored
