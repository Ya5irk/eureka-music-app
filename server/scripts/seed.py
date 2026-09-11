"""Seed the server's Postgres catalog + storage volume from an unzipped
FMA Small folder (fma_small/ + fma_metadata/tracks.csv side by side).

Usage (inside the running `api` container, so it shares DATABASE_URL and
STORAGE_DIR with the server):

    docker compose exec api python scripts/seed.py /data/fma --limit 100
    docker compose exec api python scripts/seed.py /data/fma

Idempotent: re-running skips tracks whose audio checksum is already in the
catalog, so an interrupted run (this is a ~30GB dataset) can safely resume.

Note on tracks.csv: FMA's metadata CSV has two header rows (a top-level
group like "track"/"artist"/"album", then the field name) rather than one.
This parses it with the standard library `csv` module instead of pulling in
pandas just for that — reasonable for a one-off, non-performance-critical
import script. If your downloaded tracks.csv has a different column layout
than the one documented at https://github.com/mdeff/fma, run with
--dry-run first: it prints the detected columns before writing anything.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import shutil
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import SessionLocal, init_db
from app.models import Genre, Track
from app.storage import probe_duration_seconds

_CHUNK_SIZE = 1024 * 1024


@dataclass
class FmaRow:
    track_id: int
    title: str
    artist: str
    album: str
    genre_top: str


def _fma_audio_path(fma_root: Path, track_id: int) -> Path:
    padded = f"{track_id:06d}"
    return fma_root / "fma_small" / padded[:3] / f"{padded}.mp3"


def read_tracks_csv(csv_path: Path) -> Iterator[FmaRow]:
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        top = next(reader)
        sub = next(reader)
        columns = {(t.strip(), s.strip()): i for i, (t, s) in enumerate(zip(top, sub, strict=True))}

        def col(group: str, name: str) -> int:
            idx = columns.get((group, name))
            if idx is None:
                available = ", ".join(f"{g}/{n}" for g, n in columns if g or n)
                raise SystemExit(
                    f"tracks.csv is missing expected column {group}/{name}. "
                    f"Columns found: {available}"
                )
            return idx

        title_i = col("track", "title")
        artist_i = col("artist", "name")
        album_i = col("album", "title")
        genre_i = col("track", "genre_top")

        for raw in reader:
            if not raw or not raw[0].strip().isdigit():
                continue
            yield FmaRow(
                track_id=int(raw[0]),
                title=raw[title_i].strip() or f"Track {raw[0]}",
                artist=raw[artist_i].strip() or "Unknown Artist",
                album=raw[album_i].strip(),
                genre_top=raw[genre_i].strip(),
            )


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(_CHUNK_SIZE):
            hasher.update(chunk)
    return hasher.hexdigest()


async def _get_or_create_genre(
    db: AsyncSession, name: str, cache: dict[str, Genre]
) -> Genre | None:
    if not name:
        return None
    if name in cache:
        return cache[name]
    genre = await db.scalar(select(Genre).where(Genre.name == name))
    if genre is None:
        genre = Genre(name=name)
        db.add(genre)
        await db.flush()
    cache[name] = genre
    return genre


async def seed(fma_root: Path, limit: int | None, dry_run: bool) -> None:
    settings = get_settings()
    csv_path = fma_root / "fma_metadata" / "tracks.csv"
    if not csv_path.is_file():
        raise SystemExit(f"expected metadata CSV at {csv_path}, not found")

    rows = read_tracks_csv(csv_path)
    if limit is not None:
        rows = (row for i, row in enumerate(rows) if i < limit)

    if dry_run:
        preview = list(rows)[: limit or 10]
        for row in preview:
            print(row)
        print(f"\n[dry-run] parsed {len(preview)} row(s), wrote nothing")
        return

    await init_db()

    inserted = skipped_missing = skipped_duplicate = 0
    genre_cache: dict[str, Genre] = {}

    async with SessionLocal() as db:
        for row in rows:
            audio_path = _fma_audio_path(fma_root, row.track_id)
            if not audio_path.is_file():
                skipped_missing += 1
                continue

            checksum = _sha256_file(audio_path)
            existing = await db.scalar(select(Track).where(Track.checksum_sha256 == checksum))
            if existing is not None:
                skipped_duplicate += 1
                continue

            dest = settings.storage_dir / f"{checksum}.mp3"
            if not dest.exists():
                settings.storage_dir.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(audio_path, dest)

            genre = await _get_or_create_genre(db, row.genre_top, genre_cache)
            track = Track(
                title=row.title,
                artist=row.artist,
                album=row.album or None,
                duration_seconds=probe_duration_seconds(dest),
                file_path=str(dest),
                file_size_bytes=dest.stat().st_size,
                checksum_sha256=checksum,
                source="seed",
                genres=[genre] if genre else [],
            )
            db.add(track)
            inserted += 1

            if inserted % 200 == 0:
                await db.commit()
                print(f"...{inserted} tracks inserted")

        await db.commit()

    print(
        f"done: inserted={inserted} skipped_duplicate={skipped_duplicate} "
        f"skipped_missing_audio={skipped_missing}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fma_root", type=Path, help="path to the unzipped FMA folder")
    parser.add_argument("--limit", type=int, default=None, help="only process the first N rows")
    parser.add_argument(
        "--dry-run", action="store_true", help="parse and print rows without writing anything"
    )
    args = parser.parse_args()

    if not args.fma_root.is_dir():
        sys.exit(f"not a directory: {args.fma_root}")

    asyncio.run(seed(args.fma_root, args.limit, args.dry_run))


if __name__ == "__main__":
    main()
