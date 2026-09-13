import httpx

from tests.conftest import mp3_bytes, wav_bytes


async def _upload_wav(
    client: httpx.AsyncClient, *, title: str, artist: str, frequency_hz: float, seconds: float = 1.0
) -> dict:
    resp = await client.post(
        "/tracks",
        data={"title": title, "artist": artist},
        files={
            "file": (
                "track.wav",
                wav_bytes(frequency_hz=frequency_hz, seconds=seconds),
                "audio/wav",
            )
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_similar_404_when_track_has_no_features(client: httpx.AsyncClient) -> None:
    # mp3_bytes() isn't real audio, so feature extraction silently fails on
    # upload (see upload_track's broad except) - /similar should say so
    # explicitly rather than returning a misleading empty/garbage result.
    resp = await client.post(
        "/tracks",
        data={"title": "Undecodable", "artist": "X"},
        files={"file": ("track.mp3", mp3_bytes(), "audio/mpeg")},
    )
    track_id = resp.json()["id"]

    similar = await client.get(f"/tracks/{track_id}/similar")
    assert similar.status_code == 404

    recommended = await client.get(f"/tracks/{track_id}/recommend-next")
    assert recommended.status_code == 404


async def test_similar_ranks_closer_tone_first(client: httpx.AsyncClient) -> None:
    source = await _upload_wav(client, title="Source", artist="A", frequency_hz=440.0)
    close = await _upload_wav(client, title="Close", artist="B", frequency_hz=440.0, seconds=1.2)
    far = await _upload_wav(client, title="Far", artist="C", frequency_hz=4000.0)

    resp = await client.get(f"/tracks/{source['id']}/similar")
    assert resp.status_code == 200
    results = resp.json()

    ids_in_order = [r["track"]["id"] for r in results]
    assert close["id"] in ids_in_order
    assert far["id"] in ids_in_order
    assert ids_in_order.index(close["id"]) < ids_in_order.index(far["id"])

    scores = {r["track"]["id"]: r["similarity"] for r in results}
    assert scores[close["id"]] > scores[far["id"]]


async def test_similar_excludes_the_source_track_itself(client: httpx.AsyncClient) -> None:
    source = await _upload_wav(client, title="Source2", artist="A", frequency_hz=220.0)
    await _upload_wav(client, title="Other", artist="B", frequency_hz=220.0)

    resp = await client.get(f"/tracks/{source['id']}/similar")
    ids_in_order = [r["track"]["id"] for r in resp.json()]
    assert source["id"] not in ids_in_order


async def test_recommend_next_respects_exclude(client: httpx.AsyncClient) -> None:
    source = await _upload_wav(client, title="Source3", artist="A", frequency_hz=880.0)
    close = await _upload_wav(client, title="Close3", artist="B", frequency_hz=880.0, seconds=1.3)
    far = await _upload_wav(client, title="Far3", artist="C", frequency_hz=3000.0)

    best = await client.get(f"/tracks/{source['id']}/recommend-next")
    assert best.status_code == 200
    assert best.json()["track"]["id"] == close["id"]

    excluding_close = await client.get(
        f"/tracks/{source['id']}/recommend-next", params={"exclude": close["id"]}
    )
    assert excluding_close.status_code == 200
    assert excluding_close.json()["track"]["id"] == far["id"]


async def test_recommend_next_404_when_everything_excluded(client: httpx.AsyncClient) -> None:
    source = await _upload_wav(client, title="Source4", artist="A", frequency_hz=550.0)
    other = await _upload_wav(client, title="Other4", artist="B", frequency_hz=550.0)

    resp = await client.get(
        f"/tracks/{source['id']}/recommend-next", params={"exclude": other["id"]}
    )
    assert resp.status_code == 404
