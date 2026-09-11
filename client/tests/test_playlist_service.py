from app.dao import LocalLibraryDao, PlaylistDao
from app.services.playlist_service import PlaylistService
from tests.conftest import make_track


def test_shuffle_does_not_mutate_manual_order(
    playlist_dao: PlaylistDao, library_dao: LocalLibraryDao
) -> None:
    for i in range(5):
        library_dao.insert_track(make_track(f"t{i}"))
    pid = playlist_dao.create("Mix")
    for i in range(5):
        playlist_dao.add_track(pid, f"t{i}")

    service = PlaylistService(playlist_dao)
    manual_order_before = [t.id for t in service.list_tracks(pid)]

    shuffled = service.shuffled_order(pid, seed=1)
    assert set(shuffled) == set(manual_order_before)

    manual_order_after = [t.id for t in service.list_tracks(pid)]
    assert manual_order_after == manual_order_before, (
        "toggling/reading a shuffled view must never touch stored playlist_track.position"
    )


def test_reorder_persists_new_manual_order(
    playlist_dao: PlaylistDao, library_dao: LocalLibraryDao
) -> None:
    for i in range(3):
        library_dao.insert_track(make_track(f"t{i}"))
    pid = playlist_dao.create("Mix")
    for i in range(3):
        playlist_dao.add_track(pid, f"t{i}")

    service = PlaylistService(playlist_dao)
    service.reorder(pid, ["t2", "t1", "t0"])

    assert [t.id for t in service.list_tracks(pid)] == ["t2", "t1", "t0"]
