"""Referral invites: statuses and grant progress."""
from __future__ import annotations

import json
from typing import Any

from database_functions.db import get_connection
from utils.kyiv_time import kyiv_now_str

conn = get_connection()
cursor = conn.cursor()

STATUS_BOUND = "bound"
STATUS_PENDING_GRANT = "pending_grant"
STATUS_OWNER_REVIEW = "owner_review"
STATUS_PAID = "paid"
STATUS_REVERSED = "reversed"
STATUS_EXPIRED = "expired"


def create_referrals_table() -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            friend_user_id INTEGER NOT NULL UNIQUE,
            referrer_user_id INTEGER NOT NULL,
            click_at TEXT,
            registered_at TEXT,
            terms_json TEXT,
            status TEXT NOT NULL,
            amount_uah REAL NOT NULL DEFAULT 0,
            qualifying_tx_id TEXT,
            qualifying_payed_sum_uah REAL,
            qualified_at TEXT,
            available_at TEXT,
            granted_at TEXT,
            expires_at TEXT,
            reversed_at TEXT,
            created_at TEXT,
            updated_at TEXT
        )
        """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_referrals_referrer_status "
        "ON referrals(referrer_user_id, status)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_referrals_status_available "
        "ON referrals(status, available_at)"
    )
    conn.commit()


def _loads(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _row(row) -> dict | None:
    if not row:
        return None
    data = dict(row)
    data["terms"] = _loads(data.get("terms_json"))
    return data


def get_by_friend(friend_user_id: int | str) -> dict | None:
    row = cursor.execute(
        "SELECT * FROM referrals WHERE friend_user_id = ?",
        (int(friend_user_id),),
    ).fetchone()
    return _row(row)


def get_by_id(referral_id: int) -> dict | None:
    row = cursor.execute(
        "SELECT * FROM referrals WHERE id = ?",
        (int(referral_id),),
    ).fetchone()
    return _row(row)


def create_referral(
    *,
    friend_user_id: int,
    referrer_user_id: int,
    click_at: str | None,
    registered_at: str,
    terms: dict[str, Any],
    amount_uah: float,
) -> dict | None:
    now = kyiv_now_str()
    cursor.execute(
        """
        INSERT INTO referrals (
            friend_user_id, referrer_user_id, click_at, registered_at,
            terms_json, status, amount_uah, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(friend_user_id) DO NOTHING
        """,
        (
            int(friend_user_id),
            int(referrer_user_id),
            click_at,
            registered_at,
            json.dumps(terms, ensure_ascii=False),
            STATUS_BOUND,
            float(amount_uah),
            now,
            now,
        ),
    )
    conn.commit()
    return get_by_friend(friend_user_id)


def update_referral(friend_user_id: int, **fields: Any) -> None:
    if not fields:
        return
    cols: list[str] = []
    vals: list[Any] = []
    for key, value in fields.items():
        if key == "terms":
            cols.append("terms_json = ?")
            vals.append(json.dumps(value, ensure_ascii=False))
        else:
            cols.append(f"{key} = ?")
            vals.append(value)
    cols.append("updated_at = ?")
    vals.append(kyiv_now_str())
    vals.append(int(friend_user_id))
    cursor.execute(
        f"UPDATE referrals SET {', '.join(cols)} WHERE friend_user_id = ?",
        vals,
    )
    conn.commit()


def list_pending_grants(now_str: str) -> list[dict]:
    rows = cursor.execute(
        """
        SELECT * FROM referrals
        WHERE status = ? AND available_at IS NOT NULL AND available_at <= ?
        ORDER BY available_at ASC
        """,
        (STATUS_PENDING_GRANT, now_str),
    ).fetchall()
    return [_row(r) for r in rows]


def list_owner_review() -> list[dict]:
    rows = cursor.execute(
        "SELECT * FROM referrals WHERE status = ? ORDER BY qualified_at ASC",
        (STATUS_OWNER_REVIEW,),
    ).fetchall()
    return [_row(r) for r in rows]


def list_by_qualifying_tx(transaction_id: str) -> list[dict]:
    rows = cursor.execute(
        "SELECT * FROM referrals WHERE qualifying_tx_id = ?",
        (str(transaction_id),),
    ).fetchall()
    return [_row(r) for r in rows]


def list_by_status(status: str) -> list[dict]:
    rows = cursor.execute(
        "SELECT * FROM referrals WHERE status = ?",
        (status,),
    ).fetchall()
    return [_row(r) for r in rows]


def count_referrer_success_on_day(referrer_user_id: int, day_yyyy_mm_dd: str) -> int:
    row = cursor.execute(
        """
        SELECT COUNT(*) FROM referrals
        WHERE referrer_user_id = ?
          AND status IN (?, ?, ?)
          AND substr(qualified_at, 1, 10) = ?
        """,
        (
            int(referrer_user_id),
            STATUS_PENDING_GRANT,
            STATUS_OWNER_REVIEW,
            STATUS_PAID,
            day_yyyy_mm_dd,
        ),
    ).fetchone()
    return int(row[0] or 0)


def referrer_stats(referrer_user_id: int) -> dict[str, int | float]:
    rid = int(referrer_user_id)
    row = cursor.execute(
        """
        SELECT
            COUNT(*) AS registered_friends,
            SUM(CASE WHEN status IN (?, ?) THEN 1 ELSE 0 END) AS successful,
            SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) AS paid,
            SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) AS owner_review,
            COALESCE(SUM(CASE WHEN status = ? THEN amount_uah ELSE 0 END), 0) AS earned_uah
        FROM referrals
        WHERE referrer_user_id = ?
        """,
        (
            STATUS_PAID,
            STATUS_PENDING_GRANT,
            STATUS_PAID,
            STATUS_OWNER_REVIEW,
            STATUS_PAID,
            rid,
        ),
    ).fetchone()
    return {
        "registered_friends": int(row["registered_friends"] or 0),
        "successful": int(row["successful"] or 0),
        "paid": int(row["paid"] or 0),
        "owner_review": int(row["owner_review"] or 0),
        "earned_uah": float(row["earned_uah"] or 0),
    }
