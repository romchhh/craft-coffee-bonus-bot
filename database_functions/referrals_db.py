"""Реферальні запрошення (D291): статус, умови, відкладене нарахування."""
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
    d = dict(row)
    d["terms"] = _loads(d.get("terms_json"))
    return d


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
) -> dict:
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
    return get_by_friend(friend_user_id)  # type: ignore[return-value]


def update_referral(friend_user_id: int, **fields: Any) -> None:
    if not fields:
        return
    cols = []
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
    return [_row(r) for r in rows if r]


def list_owner_review() -> list[dict]:
    rows = cursor.execute(
        "SELECT * FROM referrals WHERE status = ? ORDER BY qualified_at ASC",
        (STATUS_OWNER_REVIEW,),
    ).fetchall()
    return [_row(r) for r in rows if r]


def list_by_qualifying_tx(transaction_id: str) -> list[dict]:
    rows = cursor.execute(
        "SELECT * FROM referrals WHERE qualifying_tx_id = ?",
        (str(transaction_id),),
    ).fetchall()
    return [_row(r) for r in rows if r]


def count_referrer_success_on_day(referrer_user_id: int, day_yyyy_mm_dd: str) -> int:
    """Успішні кваліфікації за календарний день Києва (qualified_at)."""
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
    registered = cursor.execute(
        "SELECT COUNT(*) FROM referrals WHERE referrer_user_id = ?",
        (rid,),
    ).fetchone()[0]
    successful = cursor.execute(
        """
        SELECT COUNT(*) FROM referrals
        WHERE referrer_user_id = ? AND status IN (?, ?)
        """,
        (rid, STATUS_PAID, STATUS_PENDING_GRANT),
    ).fetchone()[0]
    paid = cursor.execute(
        "SELECT COUNT(*) FROM referrals WHERE referrer_user_id = ? AND status = ?",
        (rid, STATUS_PAID),
    ).fetchone()[0]
    review = cursor.execute(
        "SELECT COUNT(*) FROM referrals WHERE referrer_user_id = ? AND status = ?",
        (rid, STATUS_OWNER_REVIEW),
    ).fetchone()[0]
    earned = cursor.execute(
        """
        SELECT COALESCE(SUM(amount_uah), 0) FROM referrals
        WHERE referrer_user_id = ? AND status = ?
        """,
        (rid, STATUS_PAID),
    ).fetchone()[0]
    return {
        "registered_friends": int(registered or 0),
        "successful": int(successful or 0),
        "paid": int(paid or 0),
        "owner_review": int(review or 0),
        "earned_uah": float(earned or 0),
    }


def list_active_for_refund_scan() -> list[dict]:
    rows = cursor.execute(
        """
        SELECT * FROM referrals
        WHERE qualifying_tx_id IS NOT NULL
          AND status IN (?, ?, ?)
        """,
        (STATUS_PENDING_GRANT, STATUS_OWNER_REVIEW, STATUS_PAID),
    ).fetchall()
    return [_row(r) for r in rows if r]


def list_by_status(status: str) -> list[dict]:
    rows = cursor.execute(
        "SELECT * FROM referrals WHERE status = ?",
        (status,),
    ).fetchall()
    return [_row(r) for r in rows if r]
