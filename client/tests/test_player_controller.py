from pathlib import Path

from PySide2.QtMultimedia import QMediaPlayer

from app.local_models import LoopMode
from app.services.player_controller import PlayerController
from tests.conftest import Daos, make_track


def _make_controller(daos: Daos, tmp_path: Path) -> PlayerController:
    for i in range(3):
        f = tmp_path / f"t{i}.mp3"
        f.write_bytes(b"not-real-audio")
        daos.library.insert_track(make_track(f"t{i}", title=f"Song {i}", local_path=str(f)))
    return PlayerController(daos.library, daos.playlist, daos.state)


def test_set_queue_persists_state_and_emits_track_changed(
    qtbot, daos: Daos, tmp_path: Path
) -> None:
    controller = _make_controller(daos, tmp_path)

    with qtbot.waitSignal(controller.trackChanged, timeout=2000) as blocker:
        controller.set_queue(["t0", "t1", "t2"])

    assert blocker.args[0].id == "t0"
    state = daos.state.load()
    assert state.current_track_id == "t0"
    assert state.position_ms == 0


def test_next_and_previous_navigate_queue(qtbot, daos: Daos, tmp_path: Path) -> None:
    controller = _make_controller(daos, tmp_path)
    controller.set_queue(["t0", "t1", "t2"])

    controller.next()
    assert daos.state.load().current_track_id == "t1"

    controller.next()
    assert daos.state.load().current_track_id == "t2"

    controller.next()  # past the end, no loop -> stays put (stop() doesn't change current track)
    assert daos.state.load().current_track_id == "t2"

    controller.previous()
    assert daos.state.load().current_track_id == "t1"


def test_playlist_loop_wraps_to_start(qtbot, daos: Daos, tmp_path: Path) -> None:
    controller = _make_controller(daos, tmp_path)
    controller.set_queue(["t0", "t1", "t2"])
    controller.set_loop_mode(LoopMode.PLAYLIST)

    controller.next()
    controller.next()
    controller.next()  # wraps

    assert daos.state.load().current_track_id == "t0"


def test_track_loop_replays_same_track_on_end_of_media(qtbot, daos: Daos, tmp_path: Path) -> None:
    controller = _make_controller(daos, tmp_path)
    controller.set_queue(["t0", "t1", "t2"])
    controller.set_loop_mode(LoopMode.TRACK)

    with qtbot.waitSignal(controller.trackChanged, timeout=2000) as blocker:
        controller._on_media_status_changed(QMediaPlayer.EndOfMedia)

    assert blocker.args[0].id == "t0"
    assert daos.state.load().current_track_id == "t0"


def test_toggle_shuffle_does_not_mutate_playlist_order(qtbot, daos: Daos, tmp_path: Path) -> None:
    controller = _make_controller(daos, tmp_path)
    pid = daos.playlist.create("Mix")
    for tid in ("t0", "t1", "t2"):
        daos.playlist.add_track(pid, tid)

    controller.set_queue(["t0", "t1", "t2"], playlist_id=pid)
    controller.toggle_shuffle()

    assert [t.id for t in daos.playlist.list_tracks(pid)] == ["t0", "t1", "t2"]


def test_restore_last_state_rebuilds_queue(qtbot, daos: Daos, tmp_path: Path) -> None:
    controller = _make_controller(daos, tmp_path)
    pid = daos.playlist.create("Mix")
    for tid in ("t0", "t1", "t2"):
        daos.playlist.add_track(pid, tid)
    controller.set_queue(["t0", "t1", "t2"], start_index=1, playlist_id=pid)
    controller.seek(5000)

    fresh = PlayerController(daos.library, daos.playlist, daos.state)
    with qtbot.waitSignal(fresh.trackChanged, timeout=2000) as blocker:
        fresh.restore_last_state()

    assert blocker.args[0].id == "t1"
