"""Local cache for Poster menu images."""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

from services.poster import media_url

log = logging.getLogger(__name__)

MEDIA_DIR = Path("cache/poster_media")
MEDIA_DIR.mkdir(parents=True, exist_ok=True)
MEDIA_TTL = int(os.getenv("POSTER_MEDIA_CACHE_TTL", str(7 * 86400)))

TIMEOUT = 25


def _meta_path(kind: str, item_id: int) -> Path:
    return MEDIA_DIR / f"{kind}_{item_id}.json"


def _guess_ext(url: str, content_type: str | None) -> str:
    path = urlparse(url).path.lower()
    for ext in (".jpeg", ".jpg", ".png", ".webp", ".gif"):
        if path.endswith(ext):
            return ".jpg" if ext == ".jpeg" else ext
    ct = (content_type or "").lower()
    if "png" in ct:
        return ".png"
    if "webp" in ct:
        return ".webp"
    if "gif" in ct:
        return ".gif"
    return ".jpg"


def _data_path(kind: str, item_id: int, ext: str) -> Path:
    return MEDIA_DIR / f"{kind}_{item_id}{ext}"


def ensure_cached(kind: str, item_id: int, poster_path: str | None) -> Path | None:
    """Download an image from Poster CDN into local cache."""
    url = media_url(poster_path)
    if not url:
        return None

    meta_path = _meta_path(kind, item_id)
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if meta.get("source") == url:
                data_path = Path(meta.get("file") or "")
                fetched = float(meta.get("fetched_at") or 0)
                if data_path.is_file() and time.time() - fetched < MEDIA_TTL:
                    return data_path
        except (json.JSONDecodeError, OSError, TypeError):
            pass

    try:
        resp = requests.get(url, timeout=TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.warning("poster media download %s %s: %s", kind, item_id, exc)
        return None

    ext = _guess_ext(url, resp.headers.get("Content-Type"))
    out = _data_path(kind, item_id, ext)
    try:
        out.write_bytes(resp.content)
        meta_path.write_text(
            json.dumps(
                {
                    "source": url,
                    "file": str(out),
                    "fetched_at": time.time(),
                    "content_type": resp.headers.get("Content-Type"),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except OSError as exc:
        log.warning("poster media save %s %s: %s", kind, item_id, exc)
        return None
    return out
