from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TrackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    artist: str
    album: str | None
    duration_seconds: int
    file_size_bytes: int
    checksum_sha256: str
    source: str
    created_at: datetime
    genres: list[str]

    @classmethod
    def from_orm_track(cls, track: object) -> "TrackOut":
        return cls.model_validate(
            {
                **{
                    field: getattr(track, field)
                    for field in (
                        "id",
                        "title",
                        "artist",
                        "album",
                        "duration_seconds",
                        "file_size_bytes",
                        "checksum_sha256",
                        "source",
                        "created_at",
                    )
                },
                "genres": sorted(g.name for g in track.genres),  # type: ignore[attr-defined]
            }
        )


class TrackPage(BaseModel):
    items: list[TrackOut]
    next_cursor: str | None


class GenreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
