import os
import tempfile
from collections.abc import AsyncIterator

_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp_db.close()
_tmp_storage = tempfile.mkdtemp()

# Must happen before any `app.*` import: app.database builds its engine from
# app.config.get_settings() at import time, and get_settings() is lru_cached
# on first call — so the whole app naturally runs against a throwaway SQLite
# file + temp storage dir for the test session, with no dependency overrides
# needed. Postgres-only behavior (pg_trgm) isn't exercised here; that's
# verified via `docker compose` per server/README.md.
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["STORAGE_DIR"] = _tmp_storage

import httpx  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.database import engine, init_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _init_db() -> None:
    # httpx.ASGITransport doesn't drive the ASGI lifespan protocol, so the
    # app's own startup hook (which creates tables) never runs under it —
    # call it explicitly once per test session instead.
    await init_db()


@pytest_asyncio.fixture(autouse=True)
async def _clean_db() -> None:
    # Every test shares one SQLite file for the session (see above), so
    # without this, upload side effects from one test would leak into the
    # next — e.g. an empty-catalog assertion failing because an earlier
    # test already uploaded tracks.
    async with engine.begin() as conn:
        for table in ("track_genre", "track_feature", "track", "genre"):
            await conn.execute(text(f"DELETE FROM {table}"))


@pytest_asyncio.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def mp3_bytes(tag: bytes = b"\xff\xfb\x90\x00") -> bytes:
    """Not a decodable MP3 (mutagen will fail to probe duration, which is
    handled gracefully) but enough for upload/storage/checksum round-trips.
    """
    return tag + os.urandom(256)


def wav_bytes(frequency_hz: float = 440.0, seconds: float = 1.0, sample_rate: int = 22050) -> bytes:
    """A genuinely decodable WAV (a sine tone) - unlike mp3_bytes() above,
    this is real audio, needed to exercise app.audio_features.extract_
    feature_vector and the /similar, /recommend-next endpoints, which need
    an actual waveform to compute MFCCs from.
    """
    import io

    import numpy as np
    import soundfile as sf

    t = np.linspace(0, seconds, int(sample_rate * seconds), endpoint=False)
    tone = 0.5 * np.sin(2 * np.pi * frequency_hz * t)
    buf = io.BytesIO()
    sf.write(buf, tone, sample_rate, format="WAV")
    return buf.getvalue()
