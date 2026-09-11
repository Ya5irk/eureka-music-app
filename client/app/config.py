import os
from dataclasses import dataclass
from pathlib import Path


def _default_state_dir() -> Path:
    return Path(os.environ.get("EUREKA_STATE_DIR", Path.home() / ".local/share/eureka-music"))


@dataclass(frozen=True)
class Settings:
    api_base_url: str
    db_path: Path
    downloads_dir: Path
    page_size: int = 100


def load_settings() -> Settings:
    state_dir = _default_state_dir()
    downloads_dir = state_dir / "downloads"
    downloads_dir.mkdir(parents=True, exist_ok=True)
    return Settings(
        api_base_url=os.environ.get("EUREKA_API_URL", "http://localhost:8000"),
        db_path=Path(os.environ.get("EUREKA_DB_PATH", state_dir / "library.sqlite3")),
        downloads_dir=downloads_dir,
    )
