"""Short get_client cache for /api/me (avoid blocking the event loop)."""
from __future__ import annotations

import time
from typing import Any

from services import poster

_TTL_SEC = 12.0
_cache: dict[int, tuple[float, dict]] = {}


def get_client_cached(
    client_id: int | str,
    *,
    timeout: float | None = 4.0,
) -> dict[str, Any]:
    """Cached Poster client. Default short timeout so Mini App /api/me cannot stall."""
    cid = int(client_id)
    now = time.monotonic()
    hit = _cache.get(cid)
    if hit and now - hit[0] < _TTL_SEC:
        return hit[1]
    data = poster.get_client(cid, timeout=timeout) or {}
    _cache[cid] = (now, data)
    return data


def invalidate_client(client_id: int | str) -> None:
    _cache.pop(int(client_id), None)
