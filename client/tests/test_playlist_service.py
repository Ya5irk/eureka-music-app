from pathlib import Path

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


def test_export_m3u_writes_extended_m3u(
    playlist_dao: PlaylistDao, library_dao: LocalLibraryDao, tmp_path: Path
) -> None:
    library_dao.insert_track(
        make_track("t0", title="Song A", artist="Artist A", local_path=str(tmp_path / "a.mp3"))
    )
    library_dao.insert_track(
        make_track("t1", title="Song B", artist="Artist B", local_path=str(tmp_path / "b.mp3"))
    )
    pid = playlist_dao.create("Export Me")
    playlist_dao.add_track(pid, "t0")
    playlist_dao.add_track(pid, "t1")

    service = PlaylistService(playlist_dao)
    dest = tmp_path / "out.m3u"
    count = service.export_m3u(pid, dest)

    assert count == 2
    content = dest.read_text(encoding="utf-8")
    assert content.startswith("#EXTM3U")
    assert "#EXTINF:180,Artist A - Song A" in content
    assert str(tmp_path / "a.mp3") in content
    assert str(tmp_path / "b.mp3") in content


def test_import_m3u_matches_tracks_by_exact_path(
    playlist_dao: PlaylistDao, library_dao: LocalLibraryDao, tmp_path: Path
) -> None:
    a_path = tmp_path / "downloads" / "aaa.mp3"
    library_dao.insert_track(make_track("t0", title="Song A", local_path=str(a_path)))

    m3u = tmp_path / "playlist.m3u"
    m3u.write_text(f"#EXTM3U\n#EXTINF:180,A\n{a_path}\n", encoding="utf-8")

    service = PlaylistService(playlist_dao)
    result = service.import_m3u(m3u, "Imported", library_dao)

    assert result.imported == 1
    assert result.skipped == 0
    assert [t.id for t in service.list_tracks(result.playlist_id)] == ["t0"]


def test_import_m3u_falls_back_to_filename_match(
    playlist_dao: PlaylistDao, library_dao: LocalLibraryDao, tmp_path: Path
) -> None:
    # Simulates importing an .m3u exported from a *different* machine/
    # install, where the downloads directory prefix differs but the
    # filename (checksum-derived) is the same.
    library_dao.insert_track(
        make_track("t0", local_path=str(tmp_path / "this_machine" / "aaa.mp3"))
    )
    m3u = tmp_path / "playlist.m3u"
    m3u.write_text("/some/other/machine/downloads/aaa.mp3\n", encoding="utf-8")

    service = PlaylistService(playlist_dao)
    result = service.import_m3u(m3u, "Imported", library_dao)

    assert result.imported == 1
    assert result.skipped == 0


def test_import_m3u_skips_entries_not_in_local_library(
    playlist_dao: PlaylistDao, library_dao: LocalLibraryDao, tmp_path: Path
) -> None:
    m3u = tmp_path / "playlist.m3u"
    m3u.write_text("/nowhere/never-downloaded.mp3\n", encoding="utf-8")

    service = PlaylistService(playlist_dao)
    result = service.import_m3u(m3u, "Imported", library_dao)

    assert result.imported == 0
    assert result.skipped == 1
    assert service.list_tracks(result.playlist_id) == []
