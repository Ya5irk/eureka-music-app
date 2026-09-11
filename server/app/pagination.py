import base64
import binascii
from dataclasses import dataclass
from datetime import datetime


class InvalidCursor(ValueError):
    pass


@dataclass(frozen=True)
class Cursor:
    created_at: datetime
    id: str


def encode_cursor(created_at: datetime, id_: str) -> str:
    raw = f"{created_at.isoformat()}|{id_}".encode()
    return base64.urlsafe_b64encode(raw).decode()


def decode_cursor(cursor: str) -> Cursor:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        created_at_str, id_ = raw.split("|", 1)
        return Cursor(created_at=datetime.fromisoformat(created_at_str), id=id_)
    except (ValueError, binascii.Error) as exc:
        raise InvalidCursor(f"malformed cursor: {cursor!r}") from exc
