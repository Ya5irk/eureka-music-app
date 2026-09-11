import httpx

from tests.test_tracks import _upload


async def test_genres_list_is_distinct_and_sorted(client: httpx.AsyncClient) -> None:
    await _upload(client, title="G1", artist="A", genres="Rock, Pop")
    await _upload(client, title="G2", artist="B", genres="Pop, Jazz")

    resp = await client.get("/genres")
    assert resp.status_code == 200
    names = [g["name"] for g in resp.json()]
    assert names == sorted(set(names))
    assert {"Rock", "Pop", "Jazz"}.issubset(set(names))
