"""Exercises scripts/seed.py against a small synthetic FMA-shaped fixture
(2 tracks) rather than the real ~30GB dataset, which isn't available in
this environment. Validates the CSV parsing (two header rows) and the
id -> fma_small/XXX/XXXXXX.mp3 path convention; run the script itself
against the real dataset before recording the submission video.
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
                ",track,track,artist,album",
                ",title,genre_top,name,title",
                "2,Food,Hip-Hop,AWOL,AWOL - A Way Of Life",
                "5,This World,Hip-Hop,AWOL,AWOL - A Way Of Life",
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


async def test_seed_inserts_tracks_and_is_idempotent(tmp_path: Path) -> None:
    _write_fixture(tmp_path)

    await seed(tmp_path, limit=None, dry_run=False)
    async with SessionLocal() as db:
        tracks = list((await db.execute(select(Track))).scalars().all())
    assert {t.title for t in tracks} == {"Food", "This World"}
    assert all(t.source == "seed" for t in tracks)
    assert all(t.genres and t.genres[0].name == "Hip-Hop" for t in tracks)

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
