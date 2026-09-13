"""Seed the server's Postgres catalog + storage volume from an unzipped
FMA Small folder (fma_small/ + fma_metadata/ side by side).

Usage (inside the running `api` container, so it shares DATABASE_URL and
STORAGE_DIR with the server):

    docker compose exec api python -m scripts.seed /data/fma --limit 100
    docker compose exec api python -m scripts.seed /data/fma

Idempotent: re-running skips tracks whose audio checksum is already in the
catalog, so an interrupted run (this is a ~30GB dataset) can safely resume.

Note on tracks.csv: FMA's metadata CSV has two header rows (a top-level
group like "track"/"artist"/"album", then the field name) rather than one.
This parses it with the standard library `csv` module instead of pulling in
pandas just for that — reasonable for a one-off, non-performance-critical
import script. If your downloaded tracks.csv has a different column layout
than the one documented at https://github.com/mdeff/fma, run with
--dry-run first: it prints the detected columns before writing anything.

Uses every catalog-relevant field tracks.csv actually has, not just the
minimum: track/genres_all (all genre tags, not only genre_top) resolved to
names via genres.csv, track/tags, track/license, and album/date_released
(-> release year). All confirmed against the real downloaded dataset, not
guessed from the FMA repo's docs alone.

Also extracts a small audio-content feature vector per track (see
app/audio_features.py) for the "similar tracks"/"recommend next" bonus
features - this is the slow part of a full seed run (decoding + MFCC per
30s clip), not the file copy/checksum. A single track whose extraction
fails (corrupt/unreadable clip) is logged and skipped without aborting the
rest of the run; that track just won't show up in similarity results.
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import csv
import hashlib
import shutil
import sys
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audio_features import extract_feature_vector
from app.config import get_settings
from app.database import SessionLocal, init_db
from app.models import Genre, Track, TrackFeature
from app.storage import probe_duration_seconds

_CHUNK_SIZE = 1024 * 1024


@dataclass
class FmaRow:
    track_id: int
    title: str
    artist: str
    album: str
    genre_top: str
    genre_ids: list[int] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    license: str = ""
    release_year: int | None = None


def _fma_audio_path(fma_root: Path, track_id: int) -> Path:
    padded = f"{track_id:06d}"
    return fma_root / "fma_small" / padded[:3] / f"{padded}.mp3"


def _parse_int_list(raw: str) -> list[int]:
    """Parses FMA's Python-list-repr columns, e.g. "[17, 10, 76]" -> [17, 10, 76]."""
    try:
        return [int(x) for x in ast.literal_eval(raw)] if raw else []
    except (ValueError, SyntaxError):
        return []


def _parse_str_list(raw: str) -> list[str]:
    try:
        return [str(x) for x in ast.literal_eval(raw)] if raw else []
    except (ValueError, SyntaxError):
        return []


def _parse_release_year(raw: str) -> int | None:
    # Observed format: "2009-01-05 00:00:00"; empty when an album has no
    # recorded release date.
    stripped = raw.strip()
    if len(stripped) >= 4 and stripped[:4].isdigit():
        return int(stripped[:4])
    return None


def load_genre_names(fma_root: Path) -> dict[int, str]:
    """genres.csv: genre_id,#tracks,parent,title,top_level — tracks.csv only
    gives genre *ids* for genres_all, so this id -> title lookup is what
    makes those ids meaningful.
    """
    genres_csv = fma_root / "fma_metadata" / "genres.csv"
    if not genres_csv.is_file():
        return {}
    mapping: dict[int, str] = {}
    with genres_csv.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                mapping[int(row["genre_id"])] = row["title"].strip()
            except (KeyError, ValueError):
                continue
    return mapping


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
        genre_top_i = col("track", "genre_top")
        genres_all_i = col("track", "genres_all")
        tags_i = col("track", "tags")
        license_i = col("track", "license")
        date_released_i = col("album", "date_released")

        for raw in reader:
            if not raw or not raw[0].strip().isdigit():
                continue
            yield FmaRow(
                track_id=int(raw[0]),
                title=raw[title_i].strip() or f"Track {raw[0]}",
                artist=raw[artist_i].strip() or "Unknown Artist",
                album=raw[album_i].strip(),
                genre_top=raw[genre_top_i].strip(),
                genre_ids=_parse_int_list(raw[genres_all_i]),
                tags=_parse_str_list(raw[tags_i]),
                license=raw[license_i].strip(),
                release_year=_parse_release_year(raw[date_released_i]),
            )


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(_CHUNK_SIZE):
            hasher.update(chunk)
    return hasher.hexdigest()


async def _get_or_create_genres(
    db: AsyncSession, names: list[str], cache: dict[str, Genre]
) -> list[Genre]:
    genres = []
    for name in names:
        if not name:
            continue
        if name not in cache:
            genre = await db.scalar(select(Genre).where(Genre.name == name))
            if genre is None:
                genre = Genre(name=name)
                db.add(genre)
                await db.flush()
            cache[name] = genre
        genres.append(cache[name])
    return genres


async def seed(fma_root: Path, limit: int | None, dry_run: bool) -> None:
    settings = get_settings()
    csv_path = fma_root / "fma_metadata" / "tracks.csv"
    if not csv_path.is_file():
        raise SystemExit(f"expected metadata CSV at {csv_path}, not found")

    genre_names = load_genre_names(fma_root)
    rows = read_tracks_csv(csv_path)
    if limit is not None:
        rows = (row for i, row in enumerate(rows) if i < limit)

    if dry_run:
        preview = list(rows)[: limit or 10]
        for row in preview:
            names = [genre_names.get(gid, f"#{gid}") for gid in row.genre_ids]
            print(row, "-> genre names:", names)
        print(f"\n[dry-run] parsed {len(preview)} row(s), wrote nothing")
        return

    await init_db()

    inserted = skipped_missing = skipped_duplicate = skipped_feature_extraction = 0
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

            names = [genre_names[gid] for gid in row.genre_ids if gid in genre_names]
            if not names and row.genre_top:
                names = [row.genre_top]  # fall back to the single top genre
            genres = await _get_or_create_genres(db, names, genre_cache)

            track_id = str(uuid.uuid4())
            track = Track(
                id=track_id,
                title=row.title,
                artist=row.artist,
                album=row.album or None,
                release_year=row.release_year,
                license=row.license or None,
                tags=",".join(row.tags) or None,
                duration_seconds=probe_duration_seconds(dest),
                file_path=str(dest),
                file_size_bytes=dest.stat().st_size,
                checksum_sha256=checksum,
                source="seed",
                genres=genres,
            )
            db.add(track)

            try:
                vector = extract_feature_vector(dest)
                db.add(TrackFeature(track_id=track_id, vector=vector))
            except Exception as exc:  # noqa: BLE001 - a bad clip shouldn't abort the whole seed
                skipped_feature_extraction += 1
                print(f"...warning: feature extraction failed for track {row.track_id}: {exc}")

            inserted += 1

            if inserted % 200 == 0:
                await db.commit()
                print(f"...{inserted} tracks inserted")

        await db.commit()

    print(
        f"done: inserted={inserted} skipped_duplicate={skipped_duplicate} "
        f"skipped_missing_audio={skipped_missing} "
        f"skipped_feature_extraction={skipped_feature_extraction}"
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
