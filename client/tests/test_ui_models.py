from pathlib import Path

from PySide2.QtCore import QModelIndex, Qt

from app.dao import LocalLibraryDao
from app.ui.models import LocalLibraryModel
from tests.conftest import make_track


def _model_with_tracks(library_dao: LocalLibraryDao, tmp_path: Path) -> LocalLibraryModel:
    for i in range(3):
        library_dao.insert_track(make_track(f"t{i}", title=f"Song {i}"))
    model = LocalLibraryModel(library_dao)
    # Populate synchronously, bypassing the async fetchMore/Worker round-trip -
    # this test is about set_now_playing_id()/data(), not the paging mechanism.
    model._items = [library_dao.get(f"t{i}") for i in range(3)]  # type: ignore[misc]
    return model


def _title_at(model: LocalLibraryModel, row: int) -> object:
    return model.data(model.index(row, 0), int(Qt.DisplayRole))  # type: ignore[call-overload]


def test_now_playing_track_gets_a_prefix(library_dao: LocalLibraryDao, tmp_path: Path) -> None:
    model = _model_with_tracks(library_dao, tmp_path)

    model.set_now_playing_id("t1")

    assert _title_at(model, 0) == "Song 0"
    assert _title_at(model, 1) == "▶ Song 1"
    assert _title_at(model, 2) == "Song 2"


def test_clearing_now_playing_id_removes_the_prefix(
    library_dao: LocalLibraryDao, tmp_path: Path
) -> None:
    model = _model_with_tracks(library_dao, tmp_path)
    model.set_now_playing_id("t1")

    model.set_now_playing_id(None)

    assert _title_at(model, 1) == "Song 1"


def test_setting_the_same_id_again_is_a_no_op(library_dao: LocalLibraryDao, tmp_path: Path) -> None:
    model = _model_with_tracks(library_dao, tmp_path)
    model.set_now_playing_id("t1")

    emitted = []
    model.dataChanged.connect(lambda *args: emitted.append(args))
    model.set_now_playing_id("t1")

    assert emitted == []


def test_empty_model_does_not_raise(library_dao: LocalLibraryDao) -> None:
    model = LocalLibraryModel(library_dao)
    model.set_now_playing_id("does-not-exist")  # must not raise on rowCount() == 0
    assert model.rowCount(QModelIndex()) == 0
