"""Timed / featured quest campaigns (test + future promos)."""
from __future__ import annotations

import json

from database_functions.db import get_connection
from utils.kyiv_time import kyiv_now_str

conn = get_connection()
cursor = conn.cursor()

STATUS_DRAFT = "draft"
STATUS_ACTIVE = "active"
STATUS_ENDED = "ended"


def create_quest_campaigns_tables() -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS quest_campaigns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            description TEXT,
            quest_keys_json TEXT,
            status TEXT NOT NULL DEFAULT 'draft',
            starts_at TEXT,
            ends_at TEXT,
            created_at TEXT,
            updated_at TEXT
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS quest_campaign_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            quest_key TEXT,
            meta TEXT,
            created_at TEXT
        )
        """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_qcamp_events_camp ON quest_campaign_events(campaign_id)"
    )
    conn.commit()
    _seed_test_campaign()


def _seed_test_campaign() -> None:
    row = cursor.execute(
        "SELECT id FROM quest_campaigns WHERE key = ?", ("test_visits",)
    ).fetchone()
    if row:
        return
    now = kyiv_now_str()
    cursor.execute(
        """
        INSERT INTO quest_campaigns
            (key, title, description, quest_keys_json, status, starts_at, ends_at, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "test_visits",
            "Тест: 3 візити",
            "Тестова акція — зроби 3 візити й отримай нагороду. Пізніше тут зʼявляться сезонні квести.",
            json.dumps(["visits"], ensure_ascii=False),
            STATUS_DRAFT,
            None,
            None,
            now,
            now,
        ),
    )
    conn.commit()


def list_campaigns(*, include_ended: bool = True) -> list[dict]:
    if include_ended:
        rows = cursor.execute(
            "SELECT * FROM quest_campaigns ORDER BY id DESC"
        ).fetchall()
    else:
        rows = cursor.execute(
            """
            SELECT * FROM quest_campaigns
            WHERE status IN (?, ?)
            ORDER BY id DESC
            """,
            (STATUS_ACTIVE, STATUS_DRAFT),
        ).fetchall()
    return [_normalize(dict(r)) for r in rows]


def list_active_campaigns() -> list[dict]:
    now = kyiv_now_str()
    rows = cursor.execute(
        """
        SELECT * FROM quest_campaigns
        WHERE status = ?
          AND (starts_at IS NULL OR starts_at <= ?)
          AND (ends_at IS NULL OR ends_at >= ?)
        ORDER BY id DESC
        """,
        (STATUS_ACTIVE, now, now),
    ).fetchall()
    return [_normalize(dict(r)) for r in rows]


def get_campaign(campaign_id: int) -> dict | None:
    row = cursor.execute(
        "SELECT * FROM quest_campaigns WHERE id = ?", (int(campaign_id),)
    ).fetchone()
    return _normalize(dict(row)) if row else None


def get_campaign_by_key(key: str) -> dict | None:
    row = cursor.execute(
        "SELECT * FROM quest_campaigns WHERE key = ?", (str(key),)
    ).fetchone()
    return _normalize(dict(row)) if row else None


def set_campaign_status(campaign_id: int, status: str) -> None:
    cursor.execute(
        """
        UPDATE quest_campaigns
        SET status = ?, updated_at = ?
        WHERE id = ?
        """,
        (status, kyiv_now_str(), int(campaign_id)),
    )
    conn.commit()


def activate_campaign(campaign_id: int, *, ends_at: str | None = None) -> None:
    now = kyiv_now_str()
    cursor.execute(
        """
        UPDATE quest_campaigns
        SET status = ?, starts_at = COALESCE(starts_at, ?), ends_at = COALESCE(?, ends_at), updated_at = ?
        WHERE id = ?
        """,
        (STATUS_ACTIVE, now, ends_at, now, int(campaign_id)),
    )
    conn.commit()


def end_campaign(campaign_id: int) -> None:
    set_campaign_status(campaign_id, STATUS_ENDED)


def log_campaign_event(
    campaign_id: int,
    user_id: int,
    event_type: str,
    *,
    quest_key: str | None = None,
    meta: dict | None = None,
) -> None:
    cursor.execute(
        """
        INSERT INTO quest_campaign_events
            (campaign_id, user_id, event_type, quest_key, meta, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            int(campaign_id),
            int(user_id),
            str(event_type),
            quest_key,
            json.dumps(meta or {}, ensure_ascii=False) if meta else None,
            kyiv_now_str(),
        ),
    )
    conn.commit()


def campaign_stats(campaign_id: int) -> dict:
    row = cursor.execute(
        """
        SELECT
            COUNT(*) AS events,
            COUNT(DISTINCT user_id) AS unique_users,
            SUM(CASE WHEN event_type = 'view' THEN 1 ELSE 0 END) AS views,
            SUM(CASE WHEN event_type = 'complete' THEN 1 ELSE 0 END) AS completes
        FROM quest_campaign_events
        WHERE campaign_id = ?
        """,
        (int(campaign_id),),
    ).fetchone()
    return {
        "events": int(row["events"] or 0) if row else 0,
        "unique_users": int(row["unique_users"] or 0) if row else 0,
        "views": int(row["views"] or 0) if row else 0,
        "completes": int(row["completes"] or 0) if row else 0,
    }


def _normalize(d: dict) -> dict:
    raw = d.get("quest_keys_json")
    keys: list[str] = []
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                keys = [str(x) for x in data]
        except json.JSONDecodeError:
            keys = []
    d["quest_keys"] = keys
    return d
