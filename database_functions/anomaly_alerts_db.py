"""Deduped anomaly alert log for Telegram owner notifications."""
from __future__ import annotations

from database_functions.db import get_connection
from utils.kyiv_time import kyiv_now_str

conn = get_connection()
cursor = conn.cursor()


def create_anomaly_alerts_tables() -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS anomaly_alerts (
            id INTEGER PRIMARY KEY,
            anomaly_key TEXT NOT NULL UNIQUE,
            anomaly_type TEXT NOT NULL,
            user_id INTEGER,
            summary TEXT,
            metrics_json TEXT,
            created_at TEXT NOT NULL,
            notified_at TEXT
        )
        """
    )
    conn.commit()


def already_notified(anomaly_key: str) -> bool:
    row = cursor.execute(
        "SELECT 1 FROM anomaly_alerts WHERE anomaly_key = ?",
        (anomaly_key,),
    ).fetchone()
    return row is not None


def record_alert(
    *,
    anomaly_key: str,
    anomaly_type: str,
    user_id: int | None,
    summary: str,
    metrics_json: str | None = None,
) -> bool:
    """Insert alert; returns True if newly recorded (should notify)."""
    if already_notified(anomaly_key):
        return False
    now = kyiv_now_str()
    try:
        cursor.execute(
            """
            INSERT INTO anomaly_alerts (
                anomaly_key, anomaly_type, user_id, summary, metrics_json, created_at, notified_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (anomaly_key, anomaly_type, user_id, summary, metrics_json, now, now),
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
