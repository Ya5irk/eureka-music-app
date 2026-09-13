from pathlib import Path

import httpx

from app.api_client import ApiClient


def _client(handler) -> ApiClient:
    return ApiClient("http://test", transport=httpx.MockTransport(handler))


def test_list_tracks_parses_page() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/tracks"
        assert request.url.params["q"] == "daft"
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "1",
                        "title": "One More Time",
                        "artist": "Daft Punk",
                        "album": None,
                        "duration_seconds": 320,
                        "file_size_bytes": 1234,
                        "checksum_sha256": "abc",
                        "source": "seed",
                        "genres": ["Electronic"],
                    }
                ],
                "next_cursor": "xyz",
            },
        )

    page = _client(handler).list_tracks(query="daft")
    assert page.next_cursor == "xyz"
    assert page.items[0].title == "One More Time"
    assert page.items[0].genres == ["Electronic"]


def test_download_track_streams_to_dest_atomically(tmp_path: Path) -> None:
    content = b"fake-mp3-bytes" * 100

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=content, headers={"content-length": str(len(content))})

    dest = tmp_path / "out.mp3"
    progress_calls: list[tuple[int, int]] = []
    _client(handler).download_track(
        "t1", dest, on_progress=lambda done, total: progress_calls.append((done, total))
    )

    assert dest.read_bytes() == content
    assert not dest.with_suffix(".mp3.part").exists()
    assert progress_calls[-1][0] == len(content)


def test_upload_track_sends_multipart(tmp_path: Path) -> None:
    src = tmp_path / "song.mp3"
    src.write_bytes(b"audio-bytes")

    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        return httpx.Response(
            201,
            json={
                "id": "new-id",
                "title": "New Song",
                "artist": "Me",
                "album": None,
                "duration_seconds": 0,
                "file_size_bytes": len(b"audio-bytes"),
                "checksum_sha256": "def",
                "source": "upload",
                "genres": [],
            },
        )

    track = _client(handler).upload_track(src, title="New Song", artist="Me")

    assert seen == {"method": "POST", "path": "/tracks"}
    assert track.id == "new-id"
    assert track.source == "upload"


def _track_json(track_id: str, title: str) -> dict:
    return {
        "id": track_id,
        "title": title,
        "artist": "Someone",
        "album": None,
        "duration_seconds": 30,
        "file_size_bytes": 1,
        "checksum_sha256": "x",
        "source": "seed",
        "genres": [],
    }


def test_get_similar_tracks_parses_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/tracks/t1/similar"
        return httpx.Response(
            200,
            json=[{"track": _track_json("t2", "Close"), "similarity": 0.9}],
        )

    results = _client(handler).get_similar_tracks("t1")
    assert results[0].track.id == "t2"
    assert results[0].similarity == 0.9


def test_get_similar_tracks_404_returns_empty_list() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "no audio features"})

    assert _client(handler).get_similar_tracks("t1") == []


def test_get_recommend_next_sends_exclude_param() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["exclude"] == "a,b"
        return httpx.Response(200, json={"track": _track_json("t3", "Next"), "similarity": 0.5})

    result = _client(handler).get_recommend_next("t1", exclude=["a", "b"])
    assert result is not None
    assert result.track.id == "t3"


def test_get_recommend_next_404_returns_none() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "no eligible tracks"})

    assert _client(handler).get_recommend_next("t1") is None
