"""Persisted Telegram broadcast jobs (resume-safe)."""
from __future__ import annotations

import json

from database_functions.db import get_connection
from utils.kyiv_time import kyiv_now_str

conn = get_connection()
cursor = conn.cursor()

STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_CANCELLED = "cancelled"

RECIPIENT_PENDING = "pending"
RECIPIENT_SENT = "sent"
RECIPIENT_FAILED = "failed"
RECIPIENT_SKIPPED = "skipped"


def create_mailing_jobs_tables() -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS mailing_jobs (
            id INTEGER PRIMARY KEY,
            admin_user_id INTEGER,
            status TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            total INTEGER DEFAULT 0,
            sent INTEGER DEFAULT 0,
            failed INTEGER DEFAULT 0,
            skipped INTEGER DEFAULT 0,
            created_at TEXT,
            updated_at TEXT,
            finished_at TEXT
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS mailing_job_recipients (
            id INTEGER PRIMARY KEY,
            job_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            error TEXT,
            sent_at TEXT,
            UNIQUE(job_id, user_id)
        )
        """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_mailing_rec_job_status ON mailing_job_recipients(job_id, status)"
    )
    conn.commit()


def create_job(*, admin_user_id: int, payload: dict, recipient_ids: list[int]) -> int:
    now = kyiv_now_str()
    cursor.execute(
        """
        INSERT INTO mailing_jobs (admin_user_id, status, payload_json, total, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            int(admin_user_id),
            STATUS_RUNNING,
            json.dumps(payload, ensure_ascii=False),
            len(recipient_ids),
            now,
            now,
        ),
    )
    job_id = int(cursor.lastrowid)
    for uid in recipient_ids:
        cursor.execute(
            """
            INSERT OR IGNORE INTO mailing_job_recipients (job_id, user_id, status)
            VALUES (?, ?, ?)
            """,
            (job_id, int(uid), RECIPIENT_PENDING),
        )
    conn.commit()
    return job_id


def get_job(job_id: int) -> dict | None:
    row = cursor.execute("SELECT * FROM mailing_jobs WHERE id = ?", (int(job_id),)).fetchone()
    return dict(row) if row else None


def list_incomplete_jobs() -> list[dict]:
    rows = cursor.execute(
        "SELECT * FROM mailing_jobs WHERE status = ? ORDER BY id ASC",
        (STATUS_RUNNING,),
    ).fetchall()
    return [dict(r) for r in rows]


def list_pending_recipients(job_id: int, *, limit: int = 50) -> list[int]:
    rows = cursor.execute(
        """
        SELECT user_id FROM mailing_job_recipients
        WHERE job_id = ? AND status = ?
        ORDER BY id ASC
        LIMIT ?
        """,
        (int(job_id), RECIPIENT_PENDING, int(limit)),
    ).fetchall()
    return [int(r["user_id"]) for r in rows]


def mark_recipient(job_id: int, user_id: int, status: str, error: str | None = None) -> None:
    now = kyiv_now_str()
    cursor.execute(
        """
        UPDATE mailing_job_recipients
        SET status = ?, error = ?, sent_at = ?
        WHERE job_id = ? AND user_id = ? AND status = ?
        """,
        (status, (error or "")[:300] if error else None, now, int(job_id), int(user_id), RECIPIENT_PENDING),
    )
    conn.commit()
    _refresh_counters(job_id)


def _refresh_counters(job_id: int) -> None:
    row = cursor.execute(
        """
        SELECT
          SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) AS sent,
          SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) AS failed,
          SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) AS skipped,
          SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) AS pending
        FROM mailing_job_recipients WHERE job_id = ?
        """,
        (RECIPIENT_SENT, RECIPIENT_FAILED, RECIPIENT_SKIPPED, RECIPIENT_PENDING, int(job_id)),
    ).fetchone()
    sent = int(row["sent"] or 0)
    failed = int(row["failed"] or 0)
    skipped = int(row["skipped"] or 0)
    pending = int(row["pending"] or 0)
    now = kyiv_now_str()
    status = STATUS_RUNNING if pending > 0 else STATUS_DONE
    finished = None if pending > 0 else now
    cursor.execute(
        """
        UPDATE mailing_jobs
        SET sent = ?, failed = ?, skipped = ?, status = ?, updated_at = ?, finished_at = COALESCE(?, finished_at)
        WHERE id = ?
        """,
        (sent, failed, skipped, status, now, finished, int(job_id)),
    )
    conn.commit()


def job_stats(job_id: int) -> dict:
    job = get_job(job_id) or {}
    return {
        "id": job_id,
        "status": job.get("status"),
        "total": int(job.get("total") or 0),
        "sent": int(job.get("sent") or 0),
        "failed": int(job.get("failed") or 0),
        "skipped": int(job.get("skipped") or 0),
    }
