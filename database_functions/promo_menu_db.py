"""Seasonal / promo drinks shown in Mini App menu (admin-managed)."""
from __future__ import annotations

from pathlib import Path

from config import PROJECT_ROOT
from database_functions.db import get_connection
from utils.kyiv_time import kyiv_now_str

conn = get_connection()
cursor = conn.cursor()

UPLOAD_DIR = PROJECT_ROOT / "webapp" / "uploads" / "menu"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def create_promo_menu_table() -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS promo_menu_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            price_uah REAL NOT NULL,
            photo_path TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT,
            updated_at TEXT
        )
        """
    )
    conn.commit()


def list_items(*, active_only: bool = False) -> list[dict]:
    sql = "SELECT * FROM promo_menu_items"
    if active_only:
        sql += " WHERE active = 1"
    sql += " ORDER BY sort_order ASC, id DESC"
    return [dict(r) for r in cursor.execute(sql).fetchall()]


def get_item(item_id: int) -> dict | None:
    row = cursor.execute(
        "SELECT * FROM promo_menu_items WHERE id = ?",
        (int(item_id),),
    ).fetchone()
    return dict(row) if row else None


def add_item(*, title: str, price_uah: float, photo_path: str | None = None) -> int:
    now = kyiv_now_str()
    row = cursor.execute("SELECT COALESCE(MAX(sort_order), 0) FROM promo_menu_items").fetchone()
    sort_order = int(row[0] or 0) + 1
    cursor.execute(
        """
        INSERT INTO promo_menu_items (title, price_uah, photo_path, sort_order, active, created_at, updated_at)
        VALUES (?, ?, ?, ?, 1, ?, ?)
        """,
        (title.strip(), float(price_uah), photo_path, sort_order, now, now),
    )
    conn.commit()
    return int(cursor.lastrowid)


def set_photo(item_id: int, photo_path: str | None) -> None:
    cursor.execute(
        "UPDATE promo_menu_items SET photo_path = ?, updated_at = ? WHERE id = ?",
        (photo_path, kyiv_now_str(), int(item_id)),
    )
    conn.commit()


def set_title(item_id: int, title: str) -> None:
    cursor.execute(
        "UPDATE promo_menu_items SET title = ?, updated_at = ? WHERE id = ?",
        (title.strip(), kyiv_now_str(), int(item_id)),
    )
    conn.commit()


def set_price(item_id: int, price_uah: float) -> None:
    cursor.execute(
        "UPDATE promo_menu_items SET price_uah = ?, updated_at = ? WHERE id = ?",
        (float(price_uah), kyiv_now_str(), int(item_id)),
    )
    conn.commit()


def set_sort_order(item_id: int, sort_order: int) -> None:
    cursor.execute(
        "UPDATE promo_menu_items SET sort_order = ?, updated_at = ? WHERE id = ?",
        (int(sort_order), kyiv_now_str(), int(item_id)),
    )
    conn.commit()


def set_active(item_id: int, active: bool) -> None:
    cursor.execute(
        "UPDATE promo_menu_items SET active = ?, updated_at = ? WHERE id = ?",
        (1 if active else 0, kyiv_now_str(), int(item_id)),
    )
    conn.commit()


def local_photo_path(photo_path: str | None) -> Path | None:
    if not photo_path:
        return None
    rel = str(photo_path).lstrip("/")
    candidates = [
        PROJECT_ROOT / "webapp" / rel,
        UPLOAD_DIR / Path(rel).name,
    ]
    for p in candidates:
        if p.is_file():
            return p
    return None


def clear_photo(item_id: int) -> None:
    item = get_item(item_id)
    set_photo(item_id, None)
    if not item or not item.get("photo_path"):
        return
    path = local_photo_path(item.get("photo_path"))
    if path and path.is_file() and "uploads/menu" in str(path):
        try:
            path.unlink()
        except OSError:
            pass


def delete_item(item_id: int) -> None:
    item = get_item(item_id)
    cursor.execute("DELETE FROM promo_menu_items WHERE id = ?", (int(item_id),))
    conn.commit()
    if item and item.get("photo_path"):
        path = local_photo_path(item.get("photo_path"))
        if path and path.is_file() and "uploads/menu" in str(path):
            try:
                path.unlink()
            except OSError:
                pass


def photo_url(photo_path: str | None) -> str | None:
    if not photo_path:
        return None
    rel = str(photo_path).lstrip("/")
    if rel.startswith("static/"):
        return "/" + rel
    return "/static/" + rel
