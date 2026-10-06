"""File TTL cache for Poster API responses."""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable, TypeVar

log = logging.getLogger(__name__)

CACHE_DIR = Path("cache/poster")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_TTL = int(os.getenv("POSTER_CACHE_TTL", "900"))  # 15 min

T = TypeVar("T")


def get_cached(key: str, loader: Callable[[], T], ttl: int = DEFAULT_TTL) -> T:
    """Return cached data or call loader() and store the result."""
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in key)
    path = CACHE_DIR / f"{safe}.json"
    now = time.time()
    if path.exists():
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
            fetched = float(blob.get("fetched_at") or 0)
            if now - fetched < ttl and "data" in blob:
                return blob["data"]
        except (json.JSONDecodeError, OSError, TypeError) as exc:
            log.debug("poster cache read %s: %s", key, exc)

    data = loader()
    skip_empty = key in ("products", "categories", "spots") or key.startswith("menu_web_")
    if skip_empty and isinstance(data, list) and len(data) == 0:
        return data
    if skip_empty and isinstance(data, dict) and not (data.get("items") or []):
        return data
    try:
        path.write_text(
            json.dumps({"fetched_at": now, "data": data}, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError as exc:
        log.warning("poster cache write %s: %s", key, exc)
    return data


def invalidate(key: str) -> None:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in key)
    path = CACHE_DIR / f"{safe}.json"
    path.unlink(missing_ok=True)
