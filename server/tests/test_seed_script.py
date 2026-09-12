"""Exercises scripts/seed.py against a small synthetic FMA-shaped fixture
(2 tracks) rather than the real ~30GB dataset, which isn't available in
this environment. Validates the CSV parsing (two header rows, list-repr
columns for genres_all/tags) and the id -> fma_small/XXX/XXXXXX.mp3 path
convention — all confirmed against the real downloaded dataset first (see
scripts/seed.py's docstring); run the script itself against the real
dataset before recording the submission video.
"""

from pathlib import Path

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Track
from scripts.seed import read_tracks_csv, seed
from tests.conftest import mp3_bytes


def _write_fixture(fma_root: Path) -> None:
    metadata_dir = fma_root / "fma_metadata"
    metadata_dir.mkdir(parents=True)
    (metadata_dir / "tracks.csv").write_text(
        "\n".join(
            [
                ",album,album,artist,track,track,track,track,track",
                ",date_released,title,name,title,genre_top,genres_all,tags,license",
                (
                    "2,2009-01-05 00:00:00,AWOL - A Way Of Life,AWOL,Food,Hip-Hop,[21],[],"
                    "Attribution-NonCommercial-ShareAlike 3.0 International"
                ),
                (
                    "5,,AWOL - A Way Of Life,AWOL,This World,Hip-Hop,"
                    "\"[21, 10]\",['classic'],Public Domain"
                ),
            ]
        ),
        encoding="utf-8",
    )
    (metadata_dir / "genres.csv").write_text(
        "\n".join(
            [
                "genre_id,#tracks,parent,title,top_level",
                "21,1000,0,Hip-Hop,21",
                "10,500,0,Pop,10",
            ]
        ),
        encoding="utf-8",
    )

    for track_id in (2, 5):
        padded = f"{track_id:06d}"
        audio_dir = fma_root / "fma_small" / padded[:3]
        audio_dir.mkdir(parents=True, exist_ok=True)
        (audio_dir / f"{padded}.mp3").write_bytes(mp3_bytes())


def test_read_tracks_csv_parses_two_header_rows(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    rows = list(read_tracks_csv(tmp_path / "fma_metadata" / "tracks.csv"))

    assert [r.track_id for r in rows] == [2, 5]
    assert rows[0].title == "Food"
    assert rows[0].artist == "AWOL"
    assert rows[0].genre_top == "Hip-Hop"
    assert rows[0].genre_ids == [21]
    assert rows[0].release_year == 2009
    assert rows[0].license == "Attribution-NonCommercial-ShareAlike 3.0 International"
    assert rows[1].genre_ids == [21, 10]
    assert rows[1].tags == ["classic"]
    assert rows[1].release_year is None  # empty date_released


async def test_seed_inserts_tracks_and_is_idempotent(tmp_path: Path) -> None:
    _write_fixture(tmp_path)

    await seed(tmp_path, limit=None, dry_run=False)
    async with SessionLocal() as db:
        tracks = {t.title: t for t in (await db.execute(select(Track))).scalars().all()}
    assert set(tracks) == {"Food", "This World"}
    assert all(t.source == "seed" for t in tracks.values())

    food = tracks["Food"]
    assert {g.name for g in food.genres} == {"Hip-Hop"}
    assert food.release_year == 2009
    assert food.license == "Attribution-NonCommercial-ShareAlike 3.0 International"
    assert food.tags is None

    this_world = tracks["This World"]
    assert {g.name for g in this_world.genres} == {"Hip-Hop", "Pop"}
    assert this_world.tags == "classic"
    assert this_world.release_year is None

    # Re-running must not create duplicates (checksum-based dedupe).
    await seed(tmp_path, limit=None, dry_run=False)
    async with SessionLocal() as db:
        tracks_after = list((await db.execute(select(Track))).scalars().all())
    assert len(tracks_after) == len(tracks)


async def test_seed_respects_limit(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    await seed(tmp_path, limit=1, dry_run=False)

    async with SessionLocal() as db:
        tracks = list((await db.execute(select(Track))).scalars().all())
    assert len(tracks) == 1
