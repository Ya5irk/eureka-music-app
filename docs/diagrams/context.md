# C4 — Context

```mermaid
C4Context
    title Eureka Music App — System Context

    Person(user, "Listener", "Ubuntu desktop user who wants to browse, download, and play music")

    System(client, "Desktop Client", "PySide2 / Python3, runs on Ubuntu")
    System(server, "Eureka Music Server", "FastAPI + Postgres, run via docker compose")

    System_Ext(fma, "FMA Small dataset", "Offline dataset, imported once via seed scripts — not a live dependency")

    Rel(user, client, "Browses, plays, organizes playlists, uploads tracks")
    Rel(client, server, "Lists / searches catalog, downloads, uploads", "HTTPS/HTTP REST")
    Rel(fma, server, "Seeded once via server/scripts/seed.py")
    Rel(fma, client, "Seeded once via client/scripts/seed.py (dev/demo only)")
```

Notes:

- The server is the sole source of truth for the catalog; no third-party
  music service (Spotify/YouTube/etc.) is a dependency at runtime.
- The FMA dataset is an offline, one-time import source, not a running
  system — it never appears in the repository itself.
