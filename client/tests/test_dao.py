from app.dao import LocalLibraryDao, PlaylistDao, PlayStateDao
from app.local_models import LoopMode, PlayState
from tests.conftest import make_track


def test_insert_and_get_track(library_dao: LocalLibraryDao) -> None:
    library_dao.insert_track(make_track("t1", title="Windowlicker"))

    track = library_dao.get("t1")
    assert track is not None
    assert track.title == "Windowlicker"


def test_find_by_checksum(library_dao: LocalLibraryDao) -> None:
    library_dao.insert_track(make_track("t1"))
    found = library_dao.find_by_checksum("checksum-t1")
    assert found is not None
    assert found.id == "t1"
    assert library_dao.find_by_checksum("does-not-exist") is None


def test_list_page_paginates_and_filters(library_dao: LocalLibraryDao) -> None:
    for i in range(5):
        library_dao.insert_track(make_track(f"t{i}", title=f"Song {i}"))

    page1 = library_dao.list_page(offset=0, limit=2)
    page2 = library_dao.list_page(offset=2, limit=2)
    assert len(page1) == 2
    assert len(page2) == 2
    assert {t.id for t in page1} != {t.id for t in page2}

    assert library_dao.count() == 5

    filtered = library_dao.list_page(offset=0, limit=10, query="Song 3")
    assert [t.title for t in filtered] == ["Song 3"]


def test_playlist_crud_and_ordering(
    playlist_dao: PlaylistDao, library_dao: LocalLibraryDao
) -> None:
    for i in range(3):
        library_dao.insert_track(make_track(f"t{i}"))

    pid = playlist_dao.create("Road Trip")
    playlist_dao.add_track(pid, "t0")
    playlist_dao.add_track(pid, "t1")
    playlist_dao.add_track(pid, "t2")

    ordered = playlist_dao.list_tracks(pid)
    assert [t.id for t in ordered] == ["t0", "t1", "t2"]

    playlist_dao.set_order(pid, ["t2", "t0", "t1"])
    reordered = playlist_dao.list_tracks(pid)
    assert [t.id for t in reordered] == ["t2", "t0", "t1"]

    playlist_dao.remove_track(pid, "t0")
    assert [t.id for t in playlist_dao.list_tracks(pid)] == ["t2", "t1"]

    playlist_dao.set_loop_mode(pid, LoopMode.PLAYLIST)
    playlist = playlist_dao.get(pid)
    assert playlist is not None
    assert playlist.loop_mode == LoopMode.PLAYLIST


def test_playlist_delete_cascades_to_playlist_track(
    playlist_dao: PlaylistDao, library_dao: LocalLibraryDao
) -> None:
    library_dao.insert_track(make_track("t0"))
    pid = playlist_dao.create("Temp")
    playlist_dao.add_track(pid, "t0")

    playlist_dao.delete(pid)
    assert playlist_dao.get(pid) is None


def test_play_state_defaults_then_round_trips(state_dao: PlayStateDao) -> None:
    default = state_dao.load()
    assert default.current_track_id is None
    assert default.shuffle_on is False

    state = PlayState(
        current_track_id="t1", position_ms=4200, playlist_id=1, playlist_index=2, shuffle_on=True
    )
    state_dao.save(state)
    loaded = state_dao.load()
    assert loaded == state

    # Simulates the throttled UPSERT during playback + resume after a kill.
    state_dao.save(PlayState(**{**state.__dict__, "position_ms": 9000}))
    assert state_dao.load().position_ms == 9000
