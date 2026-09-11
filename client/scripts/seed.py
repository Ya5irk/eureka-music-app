"""Seed the client's local library (SQLite + downloads dir) directly from an
unzipped FMA Small folder, bypassing the server entirely. Useful for local
dev/demo without round-tripping every track through a download.

Usage:

    python -m scripts.seed /path/to/fma --limit 50
    python -m scripts.seed /path/to/fma

Idempotent: re-running skips tracks whose checksum is already in the local
library. See server/scripts/seed.py for notes on tracks.csv's two-header-row
format; this script duplicates that small amount of parsing rather than
importing across the server/client boundary (see AGENTS.md — the two are
independent deployables that only talk over the REST API).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import shutil
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from mutagen import MutagenError
from mutagen.mp3 import MP3

from app.config import load_settings
from app.dao import LocalLibraryDao
from app.database import init_db
from app.local_models import LocalTrack

_CHUNK_SIZE = 1024 * 1024


@dataclass
class FmaRow:
    track_id: int
    title: str
    artist: str


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

        for raw in reader:
            if not raw or not raw[0].strip().isdigit():
                continue
            yield FmaRow(
                track_id=int(raw[0]),
                title=raw[title_i].strip() or f"Track {raw[0]}",
                artist=raw[artist_i].strip() or "Unknown Artist",
            )


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(_CHUNK_SIZE):
            hasher.update(chunk)
    return hasher.hexdigest()


def _probe_duration_seconds(path: Path) -> int:
    try:
        audio = MP3(path)
        if audio.info and audio.info.length:
            return round(audio.info.length)
    except MutagenError:
        pass
    return 0


def seed(fma_root: Path, limit: int | None, dry_run: bool) -> None:
    settings = load_settings()
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

    init_db(settings.db_path)
    dao = LocalLibraryDao(settings.db_path)

    inserted = skipped_missing = skipped_duplicate = 0

    for row in rows:
        audio_path = _fma_audio_path(fma_root, row.track_id)
        if not audio_path.is_file():
            skipped_missing += 1
            continue

        checksum = _sha256_file(audio_path)
        if dao.find_by_checksum(checksum) is not None:
            skipped_duplicate += 1
            continue

        dest = settings.downloads_dir / f"{checksum}.mp3"
        if not dest.exists():
            settings.downloads_dir.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(audio_path, dest)

        dao.insert_track(
            LocalTrack(
                id=f"seed-{row.track_id}",
                title=row.title,
                artist=row.artist,
                album=None,
                duration_seconds=_probe_duration_seconds(dest),
                local_path=str(dest),
                checksum_sha256=checksum,
                downloaded_at="",
            )
        )
        inserted += 1
        if inserted % 200 == 0:
            print(f"...{inserted} tracks inserted")

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

    seed(args.fma_root, args.limit, args.dry_run)


if __name__ == "__main__":
    main()
