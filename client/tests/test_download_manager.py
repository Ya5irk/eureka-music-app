from pathlib import Path

import httpx

from app.api_client import ApiClient, RemoteTrack
from app.dao import LocalLibraryDao
from app.services.download_manager import DownloadManager


def _remote_track(track_id: str = "r1", checksum: str = "cs-1") -> RemoteTrack:
    return RemoteTrack(
        id=track_id,
        title="Some Song",
        artist="Someone",
        album=None,
        duration_seconds=200,
        file_size_bytes=8,
        checksum_sha256=checksum,
        source="seed",
        genres=[],
    )


def test_download_stores_track_and_emits_completed(
    qtbot, tmp_path: Path, library_dao: LocalLibraryDao
) -> None:
    content = b"audio-payload"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=content, headers={"content-length": str(len(content))})

    api = ApiClient("http://test", transport=httpx.MockTransport(handler))
    manager = DownloadManager(api, library_dao, downloads_dir=tmp_path)

    with qtbot.waitSignal(manager.completed, timeout=5000) as blocker:
        manager.download(_remote_track())

    local_track = blocker.args[0]
    assert local_track.id == "r1"
    assert Path(local_track.local_path).read_bytes() == content
    assert library_dao.get("r1") is not None


def test_download_dedupes_by_checksum_without_hitting_network(
    qtbot, tmp_path: Path, library_dao: LocalLibraryDao
) -> None:
    from tests.conftest import make_track

    existing = make_track("already-here", local_path=str(tmp_path / "already.mp3"))
    library_dao.insert_track(existing)

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("network should not be hit when checksum already exists locally")

    api = ApiClient("http://test", transport=httpx.MockTransport(handler))
    manager = DownloadManager(api, library_dao, downloads_dir=tmp_path)

    remote = _remote_track(track_id="new-remote-id", checksum=existing.checksum_sha256)
    with qtbot.waitSignal(manager.completed, timeout=1000) as blocker:
        manager.download(remote)

    assert blocker.args[0].id == "already-here"
