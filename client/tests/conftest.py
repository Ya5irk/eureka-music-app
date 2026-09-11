import os
from dataclasses import dataclass
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from app.dao import LocalLibraryDao, PlaylistDao, PlayStateDao  # noqa: E402
from app.database import init_db  # noqa: E402
from app.local_models import LocalTrack  # noqa: E402


@dataclass
class Daos:
    library: LocalLibraryDao
    playlist: PlaylistDao
    state: PlayStateDao


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "library.sqlite3"
    init_db(path)
    return path


@pytest.fixture
def library_dao(db_path: Path) -> LocalLibraryDao:
    return LocalLibraryDao(db_path)


@pytest.fixture
def playlist_dao(db_path: Path) -> PlaylistDao:
    return PlaylistDao(db_path)


@pytest.fixture
def state_dao(db_path: Path) -> PlayStateDao:
    return PlayStateDao(db_path)


@pytest.fixture
def daos(library_dao: LocalLibraryDao, playlist_dao: PlaylistDao, state_dao: PlayStateDao) -> Daos:
    return Daos(library=library_dao, playlist=playlist_dao, state=state_dao)


def make_track(
    id_: str, title: str = "T", artist: str = "A", local_path: str = "x.mp3"
) -> LocalTrack:
    return LocalTrack(
        id=id_,
        title=title,
        artist=artist,
        album=None,
        duration_seconds=180,
        local_path=local_path,
        checksum_sha256=f"checksum-{id_}",
        downloaded_at="",
    )


def mp3_bytes(tag: bytes = b"\xff\xfb\x90\x00") -> bytes:
    """Not decodable audio (duration probing will fail gracefully) but
    enough for checksum/storage round-trips in tests.
    """
    return tag + os.urandom(256)
