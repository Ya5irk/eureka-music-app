import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _uuid4_str() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(UTC)


track_genre = Table(
    "track_genre",
    Base.metadata,
    Column("track_id", String(36), ForeignKey("track.id", ondelete="CASCADE"), primary_key=True),
    Column("genre_id", Integer, ForeignKey("genre.id", ondelete="CASCADE"), primary_key=True),
)


class Track(Base):
    __tablename__ = "track"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid4_str)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    artist: Mapped[str] = mapped_column(String(500), nullable=False)
    album: Mapped[str | None] = mapped_column(String(500), nullable=True)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="seed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    genres: Mapped[list["Genre"]] = relationship(
        "Genre", secondary=track_genre, back_populates="tracks", lazy="selectin"
    )


class Genre(Base):
    __tablename__ = "genre"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)

    tracks: Mapped[list["Track"]] = relationship(
        "Track", secondary=track_genre, back_populates="genres"
    )


Index("ix_track_created_id", Track.created_at.desc(), Track.id.desc())
Index(
    "ix_track_title_trgm",
    Track.title,
    postgresql_using="gin",
    postgresql_ops={"title": "gin_trgm_ops"},
)
Index(
    "ix_track_artist_trgm",
    Track.artist,
    postgresql_using="gin",
    postgresql_ops={"artist": "gin_trgm_ops"},
)
