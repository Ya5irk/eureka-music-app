# Flow — End-to-end user journey

```mermaid
flowchart TD
    Start([Launch client]) --> Cached{Local library\ncached?}
    Cached -- yes --> ShowLib[Show cached library\nimmediately]
    Cached -- no --> EmptyLib[Show empty state]
    ShowLib --> RefreshAsync[Async: refresh from server]
    EmptyLib --> RefreshAsync

    RefreshAsync --> Browse[User browses / searches catalog]
    Browse --> Download[Download track]
    Download --> LocalReady[Track in local library + SQLite]
    LocalReady --> AddPlaylist{Add to playlist?}
    AddPlaylist -- yes --> Playlist[Add to playlist\n(manual order / shuffle / loop)]
    AddPlaylist -- no --> Play
    Playlist --> Play[Play / stop / continue / seek]
    Play --> StateSaved[(play_state written\nthrottled, WAL)]

    Browse --> Upload[Upload local file]
    Upload --> ServerStores[Server stores file + metadata\nbecomes visible to all clients]

    StateSaved -.crash / SIGKILL / reboot.-> Relaunch[Relaunch client]
    Relaunch --> Restore[Restore last track,\nposition, playlist, shuffle]
    Restore --> Play
```
