"""Exercises scripts/seed.py against a small synthetic FMA-shaped fixture,
same approach as server/tests/test_seed_script.py — see that file's
docstring for why (no access to the real ~30GB dataset here), and for
where the exact tracks.csv column layout below was confirmed against the
real downloaded dataset.
"""

import os
from pathlib import Path

from app.dao import LocalLibraryDao
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
    assert rows[0].genre_ids == [21]
    assert rows[0].release_year == 2009
    assert rows[1].genre_ids == [21, 10]
    assert rows[1].tags == ["classic"]


def test_seed_inserts_tracks_and_is_idempotent(
    tmp_path: Path, db_path: Path, library_dao: LocalLibraryDao
) -> None:
    fma_root = tmp_path / "fma"
    _write_fixture(fma_root)
    os.environ["EUREKA_DB_PATH"] = str(db_path)
    os.environ["EUREKA_STATE_DIR"] = str(tmp_path)

    seed(fma_root, limit=None, dry_run=False)
    tracks = {t.title: t for t in library_dao.list_page(0, 10)}
    assert set(tracks) == {"Food", "This World"}

    food = tracks["Food"]
    assert food.release_year == 2009
    assert food.license == "Attribution-NonCommercial-ShareAlike 3.0 International"
    assert food.genres == ["Hip-Hop"]

    this_world = tracks["This World"]
    assert set(this_world.genres) == {"Hip-Hop", "Pop"}
    assert this_world.tags == ["classic"]

    seed(fma_root, limit=None, dry_run=False)  # re-run must not duplicate
    assert library_dao.count() == 2
