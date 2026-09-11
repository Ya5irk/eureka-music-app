"""Exercises scripts/seed.py against a small synthetic FMA-shaped fixture,
same approach as server/tests/test_seed_script.py — see that file's
docstring for why (no access to the real ~30GB dataset here).
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
                ",track,artist",
                ",title,name",
                "2,Food,AWOL",
                "5,This World,AWOL",
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


def test_seed_inserts_tracks_and_is_idempotent(
    tmp_path: Path, db_path: Path, library_dao: LocalLibraryDao
) -> None:
    fma_root = tmp_path / "fma"
    _write_fixture(fma_root)
    os.environ["EUREKA_DB_PATH"] = str(db_path)
    os.environ["EUREKA_STATE_DIR"] = str(tmp_path)

    seed(fma_root, limit=None, dry_run=False)
    titles = {t.title for t in library_dao.list_page(0, 10)}
    assert titles == {"Food", "This World"}

    seed(fma_root, limit=None, dry_run=False)  # re-run must not duplicate
    assert library_dao.count() == 2
