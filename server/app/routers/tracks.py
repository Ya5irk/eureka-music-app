from collections.abc import Iterator
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audio_features import cosine_similarity_matrix, extract_feature_vector
from app.config import Settings, get_settings
from app.database import get_db
from app.models import Genre, Track, TrackFeature
from app.pagination import InvalidCursor, decode_cursor, encode_cursor
from app.schemas import SimilarTrackOut, TrackOut, TrackPage
from app.storage import UploadTooLarge, probe_duration_seconds, stream_upload_to_disk

_GENRE_MATCH_BONUS = 0.05

router = APIRouter(tags=["tracks"])

_STREAM_CHUNK = 1024 * 1024
_ALLOWED_CONTENT_TYPES = {
    "audio/mpeg",
    "audio/mp3",
    "audio/mp4",
    "audio/x-m4a",
    "audio/wav",
    "audio/x-wav",
}


@router.get("/tracks", response_model=TrackPage)
async def list_tracks(
    q: str | None = None,
    genre: str | None = None,
    limit: int | None = Query(default=None, gt=0, le=200),
    cursor: str | None = None,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TrackPage:
    page_size = min(limit or settings.default_page_size, settings.max_page_size)

    stmt = select(Track)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Track.title.ilike(like), Track.artist.ilike(like)))
    if genre:
        stmt = stmt.join(Track.genres).where(Genre.name == genre)
    if cursor:
        try:
            c = decode_cursor(cursor)
        except InvalidCursor as exc:
            raise HTTPException(400, str(exc)) from exc
        stmt = stmt.where(
            or_(
                Track.created_at < c.created_at,
                and_(Track.created_at == c.created_at, Track.id < c.id),
            )
        )
    stmt = stmt.order_by(Track.created_at.desc(), Track.id.desc()).limit(page_size + 1)

    result = await db.execute(stmt)
    tracks = list(result.scalars().unique().all())

    has_more = len(tracks) > page_size
    tracks = tracks[:page_size]
    next_cursor = None
    if has_more and tracks:
        next_cursor = encode_cursor(tracks[-1].created_at, tracks[-1].id)

    items = [TrackOut.from_orm_track(t) for t in tracks]
    return TrackPage(items=items, next_cursor=next_cursor)


@router.get("/tracks/{track_id}", response_model=TrackOut)
async def get_track(track_id: str, db: AsyncSession = Depends(get_db)) -> TrackOut:
    track = await db.get(Track, track_id)
    if track is None:
        raise HTTPException(404, "track not found")
    return TrackOut.from_orm_track(track)


def _parse_range(range_header: str, file_size: int) -> tuple[int, int]:
    try:
        units, _, range_spec = range_header.partition("=")
        if units.strip() != "bytes":
            raise ValueError("only 'bytes' ranges are supported")
        start_str, _, end_str = range_spec.partition("-")
        start = int(start_str) if start_str else 0
        end = int(end_str) if end_str else file_size - 1
        end = min(end, file_size - 1)
        if start < 0 or start > end:
            raise ValueError("range start/end out of bounds")
        return start, end
    except ValueError as exc:
        raise HTTPException(416, f"invalid Range header: {range_header!r}") from exc


@router.get("/tracks/{track_id}/audio")
async def get_track_audio(
    track_id: str, request: Request, db: AsyncSession = Depends(get_db)
) -> Response:
    track = await db.get(Track, track_id)
    if track is None:
        raise HTTPException(404, "track not found")

    path = Path(track.file_path)
    if not path.is_file():
        raise HTTPException(410, "audio file missing from storage")

    file_size = path.stat().st_size
    media_type = "audio/mpeg"
    range_header = request.headers.get("range")

    if range_header is None:
        return FileResponse(path, media_type=media_type, headers={"Accept-Ranges": "bytes"})

    start, end = _parse_range(range_header, file_size)
    chunk_len = end - start + 1

    def iter_range() -> Iterator[bytes]:
        with path.open("rb") as f:
            f.seek(start)
            remaining = chunk_len
            while remaining > 0:
                data = f.read(min(_STREAM_CHUNK, remaining))
                if not data:
                    break
                remaining -= len(data)
                yield data

    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(chunk_len),
    }
    return StreamingResponse(iter_range(), status_code=206, media_type=media_type, headers=headers)


@router.get("/tracks/{track_id}/similar", response_model=list[SimilarTrackOut])
async def get_similar_tracks(
    track_id: str,
    limit: int = Query(default=10, gt=0, le=50),
    db: AsyncSession = Depends(get_db),
) -> list[SimilarTrackOut]:
    """"Finding similar songs from a random record" (brief's bonus list):
    ranks every other track by cosine similarity of its precomputed audio
    feature vector (see app/audio_features.py) against this one's.
    """
    query_feature = await db.get(TrackFeature, track_id)
    if query_feature is None:
        raise HTTPException(
            404, "no audio features for this track (seeded/uploaded before feature extraction?)"
        )

    result = await db.execute(select(TrackFeature).where(TrackFeature.track_id != track_id))
    others = result.scalars().all()
    if not others:
        return []

    similarities = cosine_similarity_matrix(query_feature.vector, [o.vector for o in others])
    ranked = sorted(zip(others, similarities, strict=True), key=lambda p: p[1], reverse=True)
    ranked = ranked[:limit]

    tracks_result = await db.execute(
        select(Track).where(Track.id.in_([f.track_id for f, _ in ranked]))
    )
    tracks_by_id = {t.id: t for t in tracks_result.scalars().unique().all()}

    return [
        SimilarTrackOut(
            track=TrackOut.from_orm_track(tracks_by_id[feature.track_id]),
            similarity=round(sim, 4),
        )
        for feature, sim in ranked
        if feature.track_id in tracks_by_id
    ]


@router.get("/tracks/{track_id}/recommend-next", response_model=SimilarTrackOut)
async def recommend_next(
    track_id: str,
    exclude: str | None = Query(default=None, description="comma-separated track ids to skip"),
    db: AsyncSession = Depends(get_db),
) -> SimilarTrackOut:
    """"Recommend next song" (brief's bonus list): nearest unplayed track to
    the one currently playing, in the same audio feature space as
    /similar, with a small bonus for sharing a genre with the source track
    (per DESIGN.md §7's original plan for this feature).
    """
    source_track = await db.get(Track, track_id)
    query_feature = await db.get(TrackFeature, track_id)
    if source_track is None or query_feature is None:
        raise HTTPException(
            404, "no audio features for this track (seeded/uploaded before feature extraction?)"
        )

    excluded_ids = {track_id, *(x.strip() for x in (exclude or "").split(",") if x.strip())}
    result = await db.execute(
        select(TrackFeature).where(TrackFeature.track_id.notin_(excluded_ids))
    )
    others = result.scalars().all()
    if not others:
        raise HTTPException(404, "no eligible tracks left to recommend")

    similarities = cosine_similarity_matrix(query_feature.vector, [o.vector for o in others])
    tracks_result = await db.execute(
        select(Track).where(Track.id.in_([f.track_id for f in others]))
    )
    tracks_by_id = {t.id: t for t in tracks_result.scalars().unique().all()}
    source_genres = {g.name for g in source_track.genres}

    scored: list[tuple[Track, float]] = []
    for feature, sim in zip(others, similarities, strict=True):
        track = tracks_by_id.get(feature.track_id)
        if track is None:
            continue
        bonus = _GENRE_MATCH_BONUS if source_genres & {g.name for g in track.genres} else 0.0
        scored.append((track, sim + bonus))

    if not scored:
        raise HTTPException(404, "no eligible tracks left to recommend")

    best_track, best_score = max(scored, key=lambda p: p[1])
    return SimilarTrackOut(
        track=TrackOut.from_orm_track(best_track), similarity=round(best_score, 4)
    )


async def _get_or_create_genres(db: AsyncSession, names: list[str]) -> list[Genre]:
    if not names:
        return []
    result = await db.execute(select(Genre).where(Genre.name.in_(names)))
    existing = {g.name: g for g in result.scalars().all()}
    genres = []
    for name in names:
        genre = existing.get(name)
        if genre is None:
            genre = Genre(name=name)
            db.add(genre)
            existing[name] = genre
        genres.append(genre)
    return genres


@router.post("/tracks", response_model=TrackOut, status_code=201)
async def upload_track(
    file: UploadFile,
    title: str = Form(...),
    artist: str = Form(...),
    album: str | None = Form(None),
    genres: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TrackOut:
    if file.content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(415, f"unsupported content type: {file.content_type}")

    try:
        path, size, checksum = await stream_upload_to_disk(
            file, settings.storage_dir, settings.max_upload_bytes
        )
    except UploadTooLarge as exc:
        raise HTTPException(413, str(exc)) from exc

    existing = await db.scalar(select(Track).where(Track.checksum_sha256 == checksum))
    if existing is not None:
        return TrackOut.from_orm_track(existing)

    genre_names = [g.strip() for g in (genres or "").split(",") if g.strip()]
    genre_objs = await _get_or_create_genres(db, genre_names)

    track = Track(
        title=title,
        artist=artist,
        album=album,
        duration_seconds=probe_duration_seconds(path),
        file_path=str(path),
        file_size_bytes=size,
        checksum_sha256=checksum,
        source="upload",
        genres=genre_objs,
    )
    db.add(track)
    await db.flush()  # assigns track.id, needed for the TrackFeature FK below

    try:
        # MFCC extraction is CPU-bound; run off the event loop so one upload
        # doesn't stall every other request being served concurrently.
        vector = await run_in_threadpool(extract_feature_vector, path)
        db.add(TrackFeature(track_id=track.id, vector=vector))
    except Exception:  # noqa: BLE001 - an uploaded file we can't analyze still gets stored
        pass

    await db.commit()
    await db.refresh(track, attribute_names=["genres"])
    return TrackOut.from_orm_track(track)
