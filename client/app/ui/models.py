from PySide2.QtCore import QAbstractTableModel, QModelIndex, Qt, QThreadPool, Signal

from app.api_client import ApiClient, RemoteTrack, RemoteTrackPage
from app.dao import LocalLibraryDao
from app.local_models import LocalTrack
from app.services.playlist_service import PlaylistService
from app.workers import Worker

# PySide2-stubs' Qt.ItemDataRole isn't declared as an IntEnum, so mypy can't
# see that these enum members are plain ints at runtime (they are).
TrackRole = int(Qt.UserRole) + 1  # type: ignore[call-overload]

_COLUMNS = ("Title", "Artist", "Album", "Year", "Genres", "Duration")


def _format_duration(total_seconds: int) -> str:
    total_seconds = max(total_seconds, 0)
    return f"{total_seconds // 60}:{total_seconds % 60:02d}"


def _track_tooltip(track: RemoteTrack | LocalTrack) -> str | None:
    lines = []
    if track.license:
        lines.append(f"License: {track.license}")
    if track.tags:
        lines.append(f"Tags: {', '.join(track.tags)}")
    return "\n".join(lines) or None


class _TrackTableModel(QAbstractTableModel):
    """Shared column layout (Title/Artist/Album/Year/Genres/Duration) for
    the three track tables (Browse/Library/Playlist) - a real table instead
    of a single "Title — Artist" text line per row. License and tags (also
    real FMA metadata, per tracks.csv) surface as a row tooltip rather than
    two more columns, to avoid the table getting cramped. Each subclass
    only manages its own row storage and fetching strategy via
    `_track_at_row`.
    """

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(_COLUMNS)

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = int(Qt.DisplayRole)  # type: ignore[call-overload]
    ) -> object:
        if orientation == Qt.Horizontal and role == Qt.DisplayRole and 0 <= section < len(_COLUMNS):
            return _COLUMNS[section]
        return None

    def __init__(self) -> None:
        super().__init__()
        self._now_playing_id: str | None = None

    def set_now_playing_id(self, track_id: str | None) -> None:
        """Marks which track (if any, in this model) is currently playing,
        shown as a "▶ " prefix on its title - deliberately *not* done via
        row selection, which is already how the user picks a row for
        Download/Add-to-Playlist/etc. Reusing selection for "now playing"
        made every plain click look like it started playback.
        """
        if track_id == self._now_playing_id:
            return
        self._now_playing_id = track_id
        if self.rowCount() > 0:
            top_left = self.index(0, 0)
            bottom_right = self.index(self.rowCount() - 1, 0)
            self.dataChanged.emit(top_left, bottom_right, [Qt.DisplayRole])

    def _track_at_row(self, row: int) -> RemoteTrack | LocalTrack:
        raise NotImplementedError

    def data(self, index: QModelIndex, role: int = int(Qt.DisplayRole)) -> object:  # type: ignore[call-overload]
        if not index.isValid():
            return None
        track = self._track_at_row(index.row())
        if role == TrackRole:
            return track
        if role == Qt.ToolTipRole:
            return _track_tooltip(track)
        if role == Qt.DisplayRole:
            column = index.column()
            if column == 0:
                return f"▶ {track.title}" if track.id == self._now_playing_id else track.title
            if column == 1:
                return track.artist
            if column == 2:
                return track.album or ""
            if column == 3:
                return str(track.release_year) if track.release_year else ""
            if column == 4:
                return ", ".join(track.genres)
            if column == 5:
                return _format_duration(track.duration_seconds)
        return None


class RemoteLibraryModel(_TrackTableModel):
    """Backs the Browse tab. Fetches pages from the server lazily via Qt's
    canFetchMore/fetchMore hooks (QTableView calls these automatically as
    the user scrolls near the end) so an 8,000-track catalog is never
    pulled into memory or rendered at once — see DESIGN.md section 4.5.
    """

    errorOccurred = Signal(str)

    def __init__(
        self, api: ApiClient, thread_pool: QThreadPool | None = None, page_size: int = 100
    ) -> None:
        super().__init__()
        self._api = api
        self._pool = thread_pool or QThreadPool.globalInstance()
        self._page_size = page_size
        self._items: list[RemoteTrack] = []
        self._next_cursor: str | None = None
        self._query: str | None = None
        self._genre: str | None = None
        self._loading = False
        self._exhausted = False

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._items)

    def _track_at_row(self, row: int) -> RemoteTrack:
        return self._items[row]

    def canFetchMore(self, parent: QModelIndex = QModelIndex()) -> bool:
        return not parent.isValid() and not self._loading and not self._exhausted

    def fetchMore(self, parent: QModelIndex = QModelIndex()) -> None:
        if self._loading or self._exhausted:
            return
        self._loading = True
        worker = Worker(
            self._api.list_tracks, self._query, self._genre, self._next_cursor, self._page_size
        )
        worker.signals.result.connect(self._on_page_loaded)
        worker.signals.error.connect(self._on_error)
        self._pool.start(worker)

    def _on_page_loaded(self, page: RemoteTrackPage) -> None:
        self._loading = False
        start = len(self._items)
        self.beginInsertRows(QModelIndex(), start, start + len(page.items) - 1)
        self._items.extend(page.items)
        self.endInsertRows()
        self._next_cursor = page.next_cursor
        self._exhausted = self._next_cursor is None

    def _on_error(self, message: str) -> None:
        self._loading = False
        self.errorOccurred.emit(message)

    def set_search(self, query: str | None, genre: str | None = None) -> None:
        self.beginResetModel()
        self._items = []
        self._next_cursor = None
        self._exhausted = False
        self._query = query
        self._genre = genre
        self.endResetModel()
        self.fetchMore()

    def track_at(self, row: int) -> RemoteTrack:
        return self._items[row]


class LocalLibraryModel(_TrackTableModel):
    """Backs the Library tab: the user's downloaded tracks. Same lazy
    fetch-as-you-scroll strategy as RemoteLibraryModel, reading from SQLite
    off the UI thread via a QThreadPool worker.
    """

    def __init__(
        self, dao: LocalLibraryDao, thread_pool: QThreadPool | None = None, page_size: int = 200
    ) -> None:
        super().__init__()
        self._dao = dao
        self._pool = thread_pool or QThreadPool.globalInstance()
        self._page_size = page_size
        self._items: list[LocalTrack] = []
        self._query: str | None = None
        self._loading = False
        self._exhausted = False

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._items)

    def _track_at_row(self, row: int) -> LocalTrack:
        return self._items[row]

    def canFetchMore(self, parent: QModelIndex = QModelIndex()) -> bool:
        return not parent.isValid() and not self._loading and not self._exhausted

    def fetchMore(self, parent: QModelIndex = QModelIndex()) -> None:
        if self._loading or self._exhausted:
            return
        self._loading = True
        offset = len(self._items)
        worker = Worker(self._dao.list_page, offset, self._page_size, self._query)
        worker.signals.result.connect(self._on_page_loaded)
        self._pool.start(worker)

    def _on_page_loaded(self, page: list[LocalTrack]) -> None:
        self._loading = False
        if not page:
            self._exhausted = True
            return
        start = len(self._items)
        self.beginInsertRows(QModelIndex(), start, start + len(page) - 1)
        self._items.extend(page)
        self.endInsertRows()
        if len(page) < self._page_size:
            self._exhausted = True

    def set_query(self, query: str | None) -> None:
        self.beginResetModel()
        self._items = []
        self._query = query
        self._exhausted = False
        self.endResetModel()
        self.fetchMore()

    def track_at(self, row: int) -> LocalTrack:
        return self._items[row]

    def prepend_track(self, track: LocalTrack) -> None:
        if any(t.id == track.id for t in self._items):
            return
        self.beginInsertRows(QModelIndex(), 0, 0)
        self._items.insert(0, track)
        self.endInsertRows()


class PlaylistTracksModel(_TrackTableModel):
    def __init__(self, service: PlaylistService) -> None:
        super().__init__()
        self._service = service
        self._playlist_id: int | None = None
        self._items: list[LocalTrack] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._items)

    def _track_at_row(self, row: int) -> LocalTrack:
        return self._items[row]

    def load(self, playlist_id: int | None) -> None:
        self.beginResetModel()
        self._playlist_id = playlist_id
        self._items = self._service.list_tracks(playlist_id) if playlist_id else []
        self.endResetModel()

    def track_ids(self) -> list[str]:
        return [t.id for t in self._items]

    def track_at(self, row: int) -> LocalTrack:
        return self._items[row]

    def move(self, row: int, delta: int) -> int:
        new_row = row + delta
        if not (0 <= new_row < len(self._items)):
            return row
        self._items[row], self._items[new_row] = self._items[new_row], self._items[row]
        top_left = self.index(min(row, new_row), 0)
        bottom_right = self.index(max(row, new_row), len(_COLUMNS) - 1)
        self.dataChanged.emit(top_left, bottom_right)
        if self._playlist_id is not None:
            self._service.reorder(self._playlist_id, self.track_ids())
        return new_row
