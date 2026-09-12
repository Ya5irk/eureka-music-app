from dataclasses import dataclass, field
from enum import IntEnum


class LoopMode(IntEnum):
    NONE = 0
    TRACK = 1
    PLAYLIST = 2


@dataclass(frozen=True)
class LocalTrack:
    id: str
    title: str
    artist: str
    album: str | None
    duration_seconds: int
    local_path: str
    checksum_sha256: str
    downloaded_at: str
    release_year: int | None = None
    license: str | None = None
    tags: list[str] = field(default_factory=list)
    genres: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Playlist:
    id: int
    name: str
    loop_mode: LoopMode


@dataclass(frozen=True)
class PlayState:
    current_track_id: str | None
    position_ms: int
    playlist_id: int | None
    playlist_index: int
    shuffle_on: bool
