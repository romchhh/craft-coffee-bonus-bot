"""Coffee shop spots / venues shown in Mini App (admin-managed)."""
from __future__ import annotations

from pathlib import Path

from config import PROJECT_ROOT
from database_functions.db import get_connection
from utils.kyiv_time import kyiv_now_str

conn = get_connection()
cursor = conn.cursor()

UPLOAD_DIR = PROJECT_ROOT / "webapp" / "uploads" / "spots"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
STATIC_LOCATIONS_DIR = PROJECT_ROOT / "webapp" / "locations"


def create_spots_table() -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS spots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            address TEXT NOT NULL,
            maps_url TEXT,
            photo_path TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT,
            updated_at TEXT
        )
        """
    )
    conn.commit()
    seed_spots_if_empty()


def seed_spots_if_empty() -> None:
    row = cursor.execute("SELECT COUNT(*) FROM spots").fetchone()
    if int(row[0] or 0) > 0:
        return
    try:
        from Content.locations import BRAND_LOCATIONS
    except Exception:
        return
    now = kyiv_now_str()
    for i, loc in enumerate(BRAND_LOCATIONS, start=1):
        slug = str(loc.get("slug") or "")
        photo_path = None
        if slug:
            static_file = STATIC_LOCATIONS_DIR / f"{slug}.jpg"
            if static_file.is_file():
                photo_path = f"locations/{slug}.jpg"
        cursor.execute(
            """
            INSERT INTO spots (name, address, maps_url, photo_path, sort_order, active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                str(loc.get("name") or "").strip(),
                str(loc.get("address") or "").strip(),
                str(loc.get("maps_url") or "").strip() or None,
                photo_path,
                i,
                now,
                now,
            ),
        )
    conn.commit()


def list_spots(*, active_only: bool = False) -> list[dict]:
    sql = "SELECT * FROM spots"
    if active_only:
        sql += " WHERE active = 1"
    sql += " ORDER BY sort_order ASC, id ASC"
    return [dict(r) for r in cursor.execute(sql).fetchall()]


def get_spot(spot_id: int) -> dict | None:
    row = cursor.execute(
        "SELECT * FROM spots WHERE id = ?",
        (int(spot_id),),
    ).fetchone()
    return dict(row) if row else None


def add_spot(
    *,
    name: str,
    address: str,
    maps_url: str | None = None,
    photo_path: str | None = None,
) -> int:
    now = kyiv_now_str()
    row = cursor.execute("SELECT COALESCE(MAX(sort_order), 0) FROM spots").fetchone()
    sort_order = int(row[0] or 0) + 1
    cursor.execute(
        """
        INSERT INTO spots (name, address, maps_url, photo_path, sort_order, active, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, 1, ?, ?)
        """,
        (
            name.strip(),
            address.strip(),
            (maps_url or "").strip() or None,
            photo_path,
            sort_order,
            now,
            now,
        ),
    )
    conn.commit()
    return int(cursor.lastrowid)


def set_photo(spot_id: int, photo_path: str | None) -> None:
    cursor.execute(
        "UPDATE spots SET photo_path = ?, updated_at = ? WHERE id = ?",
        (photo_path, kyiv_now_str(), int(spot_id)),
    )
    conn.commit()


def set_name(spot_id: int, name: str) -> None:
    cursor.execute(
        "UPDATE spots SET name = ?, updated_at = ? WHERE id = ?",
        (name.strip(), kyiv_now_str(), int(spot_id)),
    )
    conn.commit()


def set_address(spot_id: int, address: str) -> None:
    cursor.execute(
        "UPDATE spots SET address = ?, updated_at = ? WHERE id = ?",
        (address.strip(), kyiv_now_str(), int(spot_id)),
    )
    conn.commit()


def set_maps_url(spot_id: int, maps_url: str | None) -> None:
    cursor.execute(
        "UPDATE spots SET maps_url = ?, updated_at = ? WHERE id = ?",
        ((maps_url or "").strip() or None, kyiv_now_str(), int(spot_id)),
    )
    conn.commit()


def set_sort_order(spot_id: int, sort_order: int) -> None:
    cursor.execute(
        "UPDATE spots SET sort_order = ?, updated_at = ? WHERE id = ?",
        (int(sort_order), kyiv_now_str(), int(spot_id)),
    )
    conn.commit()


def set_active(spot_id: int, active: bool) -> None:
    cursor.execute(
        "UPDATE spots SET active = ?, updated_at = ? WHERE id = ?",
        (1 if active else 0, kyiv_now_str(), int(spot_id)),
    )
    conn.commit()


def local_photo_path(photo_path: str | None) -> Path | None:
    if not photo_path:
        return None
    rel = str(photo_path).lstrip("/")
    if rel.startswith("static/"):
        rel = rel[len("static/") :]
    candidates = [
        PROJECT_ROOT / "webapp" / rel,
        UPLOAD_DIR / Path(rel).name,
        STATIC_LOCATIONS_DIR / Path(rel).name,
    ]
    for p in candidates:
        if p.is_file():
            return p
    return None


def _maybe_unlink_upload(photo_path: str | None) -> None:
    if not photo_path:
        return
    path = local_photo_path(photo_path)
    if path and path.is_file() and "uploads/spots" in str(path):
        try:
            path.unlink()
        except OSError:
            pass


def clear_photo(spot_id: int) -> None:
    spot = get_spot(spot_id)
    set_photo(spot_id, None)
    if spot:
        _maybe_unlink_upload(spot.get("photo_path"))


def delete_spot(spot_id: int) -> None:
    spot = get_spot(spot_id)
    cursor.execute("DELETE FROM spots WHERE id = ?", (int(spot_id),))
    conn.commit()
    if spot:
        _maybe_unlink_upload(spot.get("photo_path"))


def photo_url(photo_path: str | None) -> str | None:
    if not photo_path:
        return None
    rel = str(photo_path).lstrip("/")
    if rel.startswith("static/"):
        return "/" + rel
    return "/static/" + rel
