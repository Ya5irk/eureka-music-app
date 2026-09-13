from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx


@dataclass(frozen=True)
class RemoteTrack:
    id: str
    title: str
    artist: str
    album: str | None
    release_year: int | None
    license: str | None
    tags: list[str]
    duration_seconds: int
    file_size_bytes: int
    checksum_sha256: str
    source: str
    genres: list[str]

    @classmethod
    def from_json(cls, data: dict) -> "RemoteTrack":
        return cls(
            id=data["id"],
            title=data["title"],
            artist=data["artist"],
            album=data.get("album"),
            release_year=data.get("release_year"),
            license=data.get("license"),
            tags=data.get("tags", []),
            duration_seconds=data["duration_seconds"],
            file_size_bytes=data["file_size_bytes"],
            checksum_sha256=data["checksum_sha256"],
            source=data["source"],
            genres=data.get("genres", []),
        )


@dataclass(frozen=True)
class RemoteTrackPage:
    items: list[RemoteTrack]
    next_cursor: str | None


@dataclass(frozen=True)
class SimilarTrack:
    """A track ranked by audio-content similarity to some other track - see
    the server's /tracks/{id}/similar and /tracks/{id}/recommend-next.
    """

    track: RemoteTrack
    similarity: float

    @classmethod
    def from_json(cls, data: dict) -> "SimilarTrack":
        return cls(track=RemoteTrack.from_json(data["track"]), similarity=data["similarity"])


ProgressCallback = Callable[[int, int], None]  # (bytes_done, bytes_total)


class ApiClient:
    """Thin synchronous HTTP client. Deliberately sync: every call is made
    from inside a QThreadPool worker (see app/workers.py), never from the UI
    thread, so there's no need for an asyncio event loop on the client side.
    """

    def __init__(
        self, base_url: str, timeout: float = 30.0, transport: httpx.BaseTransport | None = None
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._transport = transport  # injectable for tests (httpx.MockTransport)

    def _client(self) -> httpx.Client:
        return httpx.Client(timeout=self._timeout, transport=self._transport)

    def list_tracks(
        self, query: str | None = None, genre: str | None = None, cursor: str | None = None,
        limit: int = 100,
    ) -> RemoteTrackPage:
        params: dict[str, str | int] = {"limit": limit}
        if query:
            params["q"] = query
        if genre:
            params["genre"] = genre
        if cursor:
            params["cursor"] = cursor
        with self._client() as client:
            resp = client.get(f"{self._base_url}/tracks", params=params)
            resp.raise_for_status()
            body = resp.json()
            return RemoteTrackPage(
                items=[RemoteTrack.from_json(t) for t in body["items"]],
                next_cursor=body["next_cursor"],
            )

    def get_track(self, track_id: str) -> RemoteTrack:
        with self._client() as client:
            resp = client.get(f"{self._base_url}/tracks/{track_id}")
            resp.raise_for_status()
            return RemoteTrack.from_json(resp.json())

    def list_genres(self) -> list[str]:
        with self._client() as client:
            resp = client.get(f"{self._base_url}/genres")
            resp.raise_for_status()
            return [g["name"] for g in resp.json()]

    def get_similar_tracks(self, track_id: str, limit: int = 10) -> list[SimilarTrack]:
        with self._client() as client:
            resp = client.get(
                f"{self._base_url}/tracks/{track_id}/similar", params={"limit": limit}
            )
            if resp.status_code == 404:
                # No feature vector for this track yet (e.g. seeded/uploaded
                # before the similarity engine existed, or extraction failed
                # on a corrupt clip) - an empty result, not an error.
                return []
            resp.raise_for_status()
            return [SimilarTrack.from_json(item) for item in resp.json()]

    def get_recommend_next(
        self, track_id: str, exclude: list[str] | None = None
    ) -> SimilarTrack | None:
        params = {"exclude": ",".join(exclude)} if exclude else {}
        with self._client() as client:
            resp = client.get(
                f"{self._base_url}/tracks/{track_id}/recommend-next", params=params
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return SimilarTrack.from_json(resp.json())

    def download_track(
        self, track_id: str, dest_path: Path, on_progress: ProgressCallback | None = None
    ) -> None:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = dest_path.with_suffix(dest_path.suffix + ".part")
        with self._client() as client, client.stream(
            "GET", f"{self._base_url}/tracks/{track_id}/audio"
        ) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            done = 0
            with tmp_path.open("wb") as f:
                for chunk in resp.iter_bytes(chunk_size=256 * 1024):
                    f.write(chunk)
                    done += len(chunk)
                    if on_progress:
                        on_progress(done, total)
        # atomic: a killed download never leaves a partial file where a played track is expected
        tmp_path.replace(dest_path)

    def upload_track(
        self,
        file_path: Path,
        title: str,
        artist: str,
        album: str | None = None,
        genres: list[str] | None = None,
    ) -> RemoteTrack:
        data = {"title": title, "artist": artist}
        if album:
            data["album"] = album
        if genres:
            data["genres"] = ",".join(genres)
        with self._client() as client, file_path.open("rb") as f:
            resp = client.post(
                f"{self._base_url}/tracks",
                data=data,
                files={"file": (file_path.name, f, "audio/mpeg")},
            )
            resp.raise_for_status()
            return RemoteTrack.from_json(resp.json())
