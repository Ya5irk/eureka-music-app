from app.dao import LocalLibraryDao, StatsDao
from tests.conftest import make_track


def _seed_tracks(library_dao: LocalLibraryDao) -> None:
    library_dao.insert_track(
        make_track("t1", title="Song A", artist="Aphex Twin", duration_seconds=120, genres=["IDM"])
    )
    library_dao.insert_track(
        make_track(
            "t2",
            title="Song B",
            artist="Aphex Twin",
            duration_seconds=200,
            genres=["IDM", "Electronic"],
        )
    )
    library_dao.insert_track(
        make_track(
            "t3", title="Song C", artist="Daft Punk", duration_seconds=300, genres=["Electronic"]
        )
    )


def test_total_plays_and_listening_seconds(
    library_dao: LocalLibraryDao, stats_dao: StatsDao
) -> None:
    _seed_tracks(library_dao)
    assert stats_dao.total_plays() == 0
    assert stats_dao.total_listening_seconds() == 0

    stats_dao.log_play("t1")
    stats_dao.log_play("t2")

    assert stats_dao.total_plays() == 2
    assert stats_dao.total_listening_seconds() == 320  # 120 + 200


def test_top_artists_ranks_by_play_count(library_dao: LocalLibraryDao, stats_dao: StatsDao) -> None:
    _seed_tracks(library_dao)
    stats_dao.log_play("t1")
    stats_dao.log_play("t1")
    stats_dao.log_play("t3")

    top = stats_dao.top_artists()
    assert top[0] == ("Aphex Twin", 2)
    assert top[1] == ("Daft Punk", 1)


def test_top_genres_counts_each_genre_a_track_carries(
    library_dao: LocalLibraryDao, stats_dao: StatsDao
) -> None:
    _seed_tracks(library_dao)
    stats_dao.log_play("t1")  # IDM
    stats_dao.log_play("t2")  # IDM, Electronic
    stats_dao.log_play("t3")  # Electronic

    counts = dict(stats_dao.top_genres())
    assert counts["IDM"] == 2
    assert counts["Electronic"] == 2


def test_recent_plays_orders_most_recent_first(
    library_dao: LocalLibraryDao, stats_dao: StatsDao
) -> None:
    _seed_tracks(library_dao)
    stats_dao.log_play("t1")
    stats_dao.log_play("t3")
    stats_dao.log_play("t2")

    recent = stats_dao.recent_plays(limit=2)
    assert [track.id for track, _ in recent] == ["t2", "t3"]


def test_recent_plays_respects_limit(library_dao: LocalLibraryDao, stats_dao: StatsDao) -> None:
    _seed_tracks(library_dao)
    for track_id in ("t1", "t2", "t3", "t1", "t2"):
        stats_dao.log_play(track_id)

    assert len(stats_dao.recent_plays(limit=3)) == 3
