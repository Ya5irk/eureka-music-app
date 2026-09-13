# ERD — Server (Postgres)

```mermaid
erDiagram
    TRACK {
        uuid id PK
        text title
        text artist
        text album
        int  release_year "nullable, from album/date_released"
        text license "nullable, FMA per-track license string"
        text tags "comma-separated, from track/tags"
        int  duration_seconds
        text file_path
        bigint file_size_bytes
        text checksum_sha256
        text source "seed | upload"
        timestamptz created_at
    }
    GENRE {
        int id PK
        text name UK
    }
    TRACK_GENRE {
        uuid track_id FK
        int genre_id FK
    }
    TRACK_FEATURE {
        uuid track_id PK "FK to TRACK, one row per track"
        json vector "40-dim MFCC mean+std, see app/audio_features.py"
    }
    TRACK ||--o{ TRACK_GENRE : has
    GENRE ||--o{ TRACK_GENRE : tags
    TRACK ||--o| TRACK_FEATURE : has
```

See [DESIGN.md §3.2](../../DESIGN.md#32-data-model-server--postgres) for
indexing and rationale.
