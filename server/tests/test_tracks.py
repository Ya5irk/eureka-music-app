import httpx

from tests.conftest import mp3_bytes


async def _upload(
    client: httpx.AsyncClient,
    *,
    title: str,
    artist: str,
    content: bytes | None = None,
    genres: str = "",
) -> dict:
    resp = await client.post(
        "/tracks",
        data={"title": title, "artist": artist, "genres": genres},
        files={"file": ("track.mp3", content or mp3_bytes(), "audio/mpeg")},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_list_empty(client: httpx.AsyncClient) -> None:
    resp = await client.get("/tracks")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["next_cursor"] is None


async def test_upload_then_get(client: httpx.AsyncClient) -> None:
    track = await _upload(
        client, title="Windowlicker", artist="Aphex Twin", genres="Electronic, IDM"
    )

    assert track["title"] == "Windowlicker"
    assert track["artist"] == "Aphex Twin"
    assert track["source"] == "upload"
    assert sorted(track["genres"]) == ["Electronic", "IDM"]

    resp = await client.get(f"/tracks/{track['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == track["id"]


async def test_get_nonexistent_track_is_404(client: httpx.AsyncClient) -> None:
    resp = await client.get("/tracks/does-not-exist")
    assert resp.status_code == 404


async def test_duplicate_upload_is_deduped_by_checksum(client: httpx.AsyncClient) -> None:
    content = mp3_bytes()
    first = await _upload(client, title="A", artist="X", content=content)
    second = await _upload(client, title="A again", artist="X", content=content)

    assert first["id"] == second["id"]

    listing = await client.get("/tracks", params={"q": "A"})
    matching = [t for t in listing.json()["items"] if t["id"] == first["id"]]
    assert len(matching) == 1


async def test_search_by_title(client: httpx.AsyncClient) -> None:
    await _upload(client, title="Ready Or Not", artist="Fugees")

    resp = await client.get("/tracks", params={"q": "ready or"})
    titles = [t["title"] for t in resp.json()["items"]]
    assert "Ready Or Not" in titles

    resp = await client.get("/tracks", params={"q": "definitely-not-in-catalog"})
    assert resp.json()["items"] == []


async def test_download_full_and_ranged(client: httpx.AsyncClient) -> None:
    content = mp3_bytes()
    track = await _upload(client, title="Range Test", artist="Y", content=content)

    full = await client.get(f"/tracks/{track['id']}/audio")
    assert full.status_code == 200
    assert full.content == content

    ranged = await client.get(
        f"/tracks/{track['id']}/audio", headers={"Range": "bytes=0-9"}
    )
    assert ranged.status_code == 206
    assert ranged.content == content[:10]
    assert ranged.headers["content-range"] == f"bytes 0-9/{len(content)}"


async def test_pagination_cursor(client: httpx.AsyncClient) -> None:
    for i in range(3):
        await _upload(client, title=f"Page Track {i}", artist="Pager")

    first_page = await client.get("/tracks", params={"q": "Page Track", "limit": 2})
    body = first_page.json()
    assert len(body["items"]) == 2
    assert body["next_cursor"] is not None

    second_page = await client.get(
        "/tracks", params={"q": "Page Track", "limit": 2, "cursor": body["next_cursor"]}
    )
    body2 = second_page.json()
    assert len(body2["items"]) == 1
    assert body2["next_cursor"] is None

    seen_ids = {t["id"] for t in body["items"]} | {t["id"] for t in body2["items"]}
    assert len(seen_ids) == 3
