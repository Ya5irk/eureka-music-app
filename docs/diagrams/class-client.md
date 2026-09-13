# Class — Client architecture (key classes)

```mermaid
classDiagram
    class MainWindow {
        -RemoteLibraryModel browseModel
        -LocalLibraryModel libraryModel
        -PlaylistTracksModel playlistModel
        -PlayerController player
        +onSearch(query)
        +onDownloadClicked(trackId)
        +onUploadClicked()
        +onStatsTabOpened()
    }

    class _TrackTableModel {
        <<QAbstractTableModel>>
        -str nowPlayingId
        +columnCount()
        +data(index, role)
        +setNowPlayingId(trackId)
    }

    class RemoteLibraryModel {
        -ApiClient api
        +fetchMore()
        +setSearch(query, genre)
    }

    class LocalLibraryModel {
        -LocalLibraryDao dao
        +fetchMore()
        +setQuery(query)
        +prependTrack(track)
    }

    class PlaylistTracksModel {
        -PlaylistService service
        +load(playlistId)
        +move(row, delta)
    }

    class ApiClient {
        -str baseUrl
        +listTracks(query, genre, cursor) RemoteTrackPage
        +getTrack(id) RemoteTrack
        +downloadTrack(id, destPath, onProgress)
        +uploadTrack(path, metadata, onProgress) RemoteTrack
        +similarTracks(id) list~RemoteTrack~
        +recommendNext(id, exclude) RemoteTrack
    }

    class DownloadManager {
        <<QThreadPool worker owner>>
        -ApiClient api
        -LocalLibraryDao dao
        +download(track)
        signal downloadProgress(trackId, pct)
        signal downloadComplete(track)
    }

    class UploadManager {
        <<QThreadPool worker owner>>
        -ApiClient api
        +upload(path, metadata)
        signal uploadComplete(track)
    }

    class PlaylistService {
        -PlaylistDao dao
        +createPlaylist(name)
        +addTrack(playlistId, trackId)
        +reorder(playlistId, orderedIds)
        +toggleShuffle(playlistId)
        +setLoopMode(playlistId, mode)
        +exportM3u(playlistId, path)
        +importM3u(path) list~LocalTrack~
    }

    class PlayerController {
        -QMediaPlayer mediaPlayer
        -QAudioProbe audioProbe
        -PlayStateDao stateDao
        -StatsDao statsDao
        +play(track)
        +stop()
        +seek(ms)
        +next()
        +previous()
        +currentTrack() LocalTrack
        signal positionChanged(ms)
        signal trackChanged(track)
        signal levelsChanged(bands)
    }

    class LocalLibraryDao {
        +insertTrack(track)
        +listPage(offset, limit, query)
        +findByChecksum(sha256)
        +findByPathOrFilename(path)
    }

    class PlaylistDao {
        +create(name)
        +listTracks(playlistId)
        +setOrder(playlistId, orderedIds)
    }

    class PlayStateDao {
        +save(state)
        +load() PlayState
    }

    class StatsDao {
        +logPlay(trackId)
        +totalPlays() int
        +totalListeningSeconds() int
        +topArtists(limit) list
        +topGenres(limit) list
        +recentPlays(limit) list
    }

    MainWindow --> RemoteLibraryModel
    MainWindow --> LocalLibraryModel
    MainWindow --> PlaylistTracksModel
    MainWindow --> PlayerController
    MainWindow --> DownloadManager
    MainWindow --> UploadManager
    RemoteLibraryModel --|> _TrackTableModel
    LocalLibraryModel --|> _TrackTableModel
    PlaylistTracksModel --|> _TrackTableModel
    RemoteLibraryModel --> ApiClient
    LocalLibraryModel --> LocalLibraryDao
    PlaylistTracksModel --> PlaylistService
    PlaylistService --> PlaylistDao
    PlayerController --> PlayStateDao
    PlayerController --> StatsDao
    DownloadManager --> ApiClient
    DownloadManager --> LocalLibraryDao
    UploadManager --> ApiClient
```

`RemoteLibraryModel`/`LocalLibraryModel`/`PlaylistTracksModel` share the
`_TrackTableModel` base (a `QAbstractTableModel`, not a list model — see
`app/ui/models.py`) so all three tables get the same Title/Artist/Album/
Year/Genres/Duration columns and the same now-playing indicator, while
each subclass only owns its row source and fetch strategy.
