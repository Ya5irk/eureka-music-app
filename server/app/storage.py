import hashlib
import os
import uuid
from pathlib import Path

from fastapi import UploadFile
from mutagen import MutagenError
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4

_CHUNK_SIZE = 1024 * 1024


class UploadTooLarge(ValueError):
    pass


async def stream_upload_to_disk(
    upload: UploadFile, storage_dir: Path, max_bytes: int
) -> tuple[Path, int, str]:
    """Stream an incoming upload to a temp file, checksum it, then atomically
    rename it to its content-addressed final path so a crash mid-write never
    leaves a corrupt file where a served track is expected.
    """
    storage_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = storage_dir / f".tmp-{uuid.uuid4().hex}"
    hasher = hashlib.sha256()
    total = 0
    try:
        with tmp_path.open("wb") as f:
            while chunk := await upload.read(_CHUNK_SIZE):
                total += len(chunk)
                if total > max_bytes:
                    raise UploadTooLarge(f"upload exceeds {max_bytes} bytes")
                hasher.update(chunk)
                f.write(chunk)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise

    checksum = hasher.hexdigest()
    suffix = Path(upload.filename or "track.mp3").suffix or ".mp3"
    final_path = storage_dir / f"{checksum}{suffix}"
    if final_path.exists():
        tmp_path.unlink(missing_ok=True)
    else:
        os.replace(tmp_path, final_path)
    return final_path, total, checksum


def probe_duration_seconds(path: Path) -> int:
    for probe in (MP3, MP4):
        try:
            audio = probe(path)
            if audio.info and audio.info.length:
                return round(audio.info.length)
        except MutagenError:
            continue
    return 0
