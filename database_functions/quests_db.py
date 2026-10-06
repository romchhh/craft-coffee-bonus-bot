"""Quest and achievement progress."""
from __future__ import annotations

import json
from typing import Any

from database_functions.db import get_connection
from utils.kyiv_time import kyiv_now_str

conn = get_connection()
cursor = conn.cursor()

# Quest / achievement keys
QUEST_VISITS = "visits"
QUEST_COMBO = "combo"
QUEST_DRINKS = "drinks"
ACH_FIRST = "first_purchase"
ACH_DAYS = "days"


def create_quests_tables() -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS quest_progress (
            user_id INTEGER NOT NULL,
            quest_key TEXT NOT NULL,
            cycle_id TEXT NOT NULL,
            progress REAL NOT NULL DEFAULT 0,
            target REAL NOT NULL DEFAULT 1,
            completed INTEGER NOT NULL DEFAULT 0,
            reward_paid INTEGER NOT NULL DEFAULT 0,
            reward_uah REAL NOT NULL DEFAULT 0,
            meta TEXT,
            started_at TEXT,
            completed_at TEXT,
            updated_at TEXT,
            PRIMARY KEY (user_id, quest_key, cycle_id)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS quest_event_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            transaction_id TEXT,
            quest_key TEXT,
            note TEXT,
            created_at TEXT
        )
        """
    )
    conn.commit()


def _meta_loads(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def get_progress(user_id: int, quest_key: str, cycle_id: str) -> dict | None:
    row = cursor.execute(
        """
        SELECT * FROM quest_progress
        WHERE user_id = ? AND quest_key = ? AND cycle_id = ?
        """,
        (int(user_id), quest_key, cycle_id),
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["meta"] = _meta_loads(d.get("meta"))
    return d


def list_progress_for_user(user_id: int) -> list[dict]:
    rows = cursor.execute(
        "SELECT * FROM quest_progress WHERE user_id = ? ORDER BY quest_key, cycle_id",
        (int(user_id),),
    ).fetchall()
    out = []
    for row in rows:
        d = dict(row)
        d["meta"] = _meta_loads(d.get("meta"))
        out.append(d)
    return out


def upsert_progress(
    user_id: int,
    quest_key: str,
    cycle_id: str,
    *,
    progress: float,
    target: float,
    completed: bool = False,
    reward_paid: bool | None = None,
    reward_uah: float | None = None,
    meta: dict | None = None,
    started_at: str | None = None,
    completed_at: str | None = None,
) -> None:
    existing = get_progress(user_id, quest_key, cycle_id)
    now = kyiv_now_str()
    meta_s = json.dumps(meta if meta is not None else (existing or {}).get("meta") or {}, ensure_ascii=False)
    if existing is None:
        cursor.execute(
            """
            INSERT INTO quest_progress (
                user_id, quest_key, cycle_id, progress, target,
                completed, reward_paid, reward_uah, meta, started_at, completed_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(user_id),
                quest_key,
                cycle_id,
                float(progress),
                float(target),
                1 if completed else 0,
                1 if reward_paid else 0,
                float(reward_uah or 0),
                meta_s,
                started_at or now,
                completed_at,
                now,
            ),
        )
    else:
        cursor.execute(
            """
            UPDATE quest_progress SET
                progress = ?,
                target = ?,
                completed = ?,
                reward_paid = COALESCE(?, reward_paid),
                reward_uah = COALESCE(?, reward_uah),
                meta = ?,
                started_at = COALESCE(started_at, ?),
                completed_at = COALESCE(?, completed_at),
                updated_at = ?
            WHERE user_id = ? AND quest_key = ? AND cycle_id = ?
            """,
            (
                float(progress),
                float(target),
                1 if completed else 0,
                (1 if reward_paid else 0) if reward_paid is not None else None,
                float(reward_uah) if reward_uah is not None else None,
                meta_s,
                started_at or now,
                completed_at,
                now,
                int(user_id),
                quest_key,
                cycle_id,
            ),
        )
    conn.commit()


def mark_reward_paid(user_id: int, quest_key: str, cycle_id: str, reward_uah: float) -> None:
    cursor.execute(
        """
        UPDATE quest_progress
        SET reward_paid = 1, reward_uah = ?, completed = 1,
            completed_at = COALESCE(completed_at, ?), updated_at = ?
        WHERE user_id = ? AND quest_key = ? AND cycle_id = ?
        """,
        (float(reward_uah), kyiv_now_str(), kyiv_now_str(), int(user_id), quest_key, cycle_id),
    )
    conn.commit()


def log_quest_event(
    user_id: int,
    *,
    transaction_id: str | None = None,
    quest_key: str | None = None,
    note: str = "",
) -> None:
    cursor.execute(
        """
        INSERT INTO quest_event_log (user_id, transaction_id, quest_key, note, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (int(user_id), transaction_id, quest_key, note, kyiv_now_str()),
    )
    conn.commit()


def has_event_for_tx(user_id: int, transaction_id: str, quest_key: str) -> bool:
    row = cursor.execute(
        """
        SELECT 1 FROM quest_event_log
        WHERE user_id = ? AND transaction_id = ? AND quest_key = ?
        LIMIT 1
        """,
        (int(user_id), str(transaction_id), quest_key),
    ).fetchone()
    return row is not None


def export_meta(meta: dict[str, Any]) -> str:
    return json.dumps(meta, ensure_ascii=False)
