"""T041: Cursor encode/decode utilities for paginated reading."""

from __future__ import annotations

import base64
import json


def encode_cursor(chunk_index: int) -> str:
    """Encode a chunk_index into an opaque base64 cursor string."""
    payload = json.dumps({"chunk_index": chunk_index})
    return base64.b64encode(payload.encode()).decode()


def decode_cursor(cursor: str) -> int:
    """Decode a cursor string back to a chunk_index.

    Raises ValueError with 'INVALID_CURSOR' on malformed input.
    """
    try:
        payload = json.loads(base64.b64decode(cursor.encode()).decode())
        return int(payload["chunk_index"])
    except Exception as exc:
        raise ValueError(f"INVALID_CURSOR: {exc}") from exc
