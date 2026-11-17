"""Central Craftyki ledger + expiring lots (factual history)."""
from __future__ import annotations

import json
from typing import Any

from database_functions.db import get_connection
from utils.kyiv_time import kyiv_now_str

conn = get_connection()
cursor = conn.cursor()

STATUS_PENDING = "pending"
STATUS_SUBMITTED = "submitted"
STATUS_POSTED = "posted"
STATUS_FAILED = "failed"
STATUS_VOID = "void"

# Reasons used across the app
REASON_CASHBACK = "cashback"
REASON_SPEND = "spend"
REASON_WELCOME = "welcome"
REASON_BIRTHDAY = "birthday"
REASON_ANNUAL_BIRTHDAY = "annual_birthday"
REASON_REFERRAL = "referral"
REASON_REFERRAL_EXPIRE = "referral_expire"
REASON_REFERRAL_REVERSE = "referral_reverse"
REASON_QUEST = "quest"
REASON_BURN_90D = "burn_90d"
REASON_ADMIN_GIFT = "admin_gift"


def create_bonus_ledger_tables() -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS bonus_ledger (
            id INTEGER PRIMARY KEY,
            op_key TEXT NOT NULL UNIQUE,
            user_id INTEGER,
            poster_client_id INTEGER,
            amount_uah REAL NOT NULL,
            reason TEXT NOT NULL,
            status TEXT NOT NULL,
            balance_before REAL,
            balance_after REAL,
            admin_user_id INTEGER,
            ref_type TEXT,
            ref_id TEXT,
            title TEXT,
            meta_json TEXT,
            error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT,
            posted_at TEXT
        )
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_bonus_ledger_user_created
        ON bonus_ledger(user_id, created_at DESC)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_bonus_ledger_status
        ON bonus_ledger(status)
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS bonus_lots (
            id INTEGER PRIMARY KEY,
            ledger_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            source TEXT NOT NULL,
            amount_uah REAL NOT NULL,
            remaining_uah REAL NOT NULL,
            expires_at TEXT,
            created_at TEXT NOT NULL,
            closed_at TEXT
        )
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_bonus_lots_user_exp
        ON bonus_lots(user_id, expires_at)
        """
    )
    conn.commit()


def _row(r) -> dict | None:
    return dict(r) if r else None


def get_by_op_key(op_key: str) -> dict | None:
    return _row(
        cursor.execute("SELECT * FROM bonus_ledger WHERE op_key = ?", (op_key,)).fetchone()
    )


def get_by_id(ledger_id: int) -> dict | None:
    return _row(
        cursor.execute("SELECT * FROM bonus_ledger WHERE id = ?", (int(ledger_id),)).fetchone()
    )


def create_pending(
    *,
    op_key: str,
    user_id: int | None,
    poster_client_id: int | None,
    amount_uah: float,
    reason: str,
    title: str | None = None,
    admin_user_id: int | None = None,
    ref_type: str | None = None,
    ref_id: str | None = None,
    meta: dict | None = None,
) -> dict:
    """Insert pending op or return existing row for the same op_key."""
    existing = get_by_op_key(op_key)
    if existing:
        return existing
    now = kyiv_now_str()
    cursor.execute(
        """
        INSERT INTO bonus_ledger (
            op_key, user_id, poster_client_id, amount_uah, reason, status,
            admin_user_id, ref_type, ref_id, title, meta_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            op_key,
            int(user_id) if user_id is not None else None,
            int(poster_client_id) if poster_client_id is not None else None,
            round(float(amount_uah), 2),
            reason,
            STATUS_PENDING,
            int(admin_user_id) if admin_user_id is not None else None,
            ref_type,
            str(ref_id) if ref_id is not None else None,
            title,
            json.dumps(meta, ensure_ascii=False) if meta else None,
            now,
            now,
        ),
    )
    conn.commit()
    return get_by_op_key(op_key) or {}


def mark_submitted(ledger_id: int, *, balance_before: float | None) -> None:
    now = kyiv_now_str()
    cursor.execute(
        """
        UPDATE bonus_ledger
        SET status = ?, balance_before = ?, updated_at = ?
        WHERE id = ? AND status IN (?, ?)
        """,
        (STATUS_SUBMITTED, balance_before, now, int(ledger_id), STATUS_PENDING, STATUS_SUBMITTED),
    )
    conn.commit()


def mark_posted(
    ledger_id: int,
    *,
    balance_after: float | None = None,
) -> None:
    now = kyiv_now_str()
    cursor.execute(
        """
        UPDATE bonus_ledger
        SET status = ?, balance_after = COALESCE(?, balance_after),
            posted_at = ?, updated_at = ?, error = NULL
        WHERE id = ?
        """,
        (STATUS_POSTED, balance_after, now, now, int(ledger_id)),
    )
    conn.commit()


def mark_failed(ledger_id: int, error: str) -> None:
    now = kyiv_now_str()
    cursor.execute(
        """
        UPDATE bonus_ledger
        SET status = ?, error = ?, updated_at = ?
        WHERE id = ?
        """,
        (STATUS_FAILED, (error or "")[:500], now, int(ledger_id)),
    )
    conn.commit()


def list_incomplete(*, limit: int = 100) -> list[dict]:
    rows = cursor.execute(
        """
        SELECT * FROM bonus_ledger
        WHERE status IN (?, ?)
        ORDER BY id ASC
        LIMIT ?
        """,
        (STATUS_PENDING, STATUS_SUBMITTED, int(limit)),
    ).fetchall()
    return [dict(r) for r in rows]


def list_for_user(user_id: int, *, limit: int = 80) -> list[dict]:
    rows = cursor.execute(
        """
        SELECT * FROM bonus_ledger
        WHERE user_id = ? AND status = ? AND amount_uah != 0
        ORDER BY COALESCE(posted_at, created_at) DESC, id DESC
        LIMIT ?
        """,
        (int(user_id), STATUS_POSTED, int(limit)),
    ).fetchall()
    return [dict(r) for r in rows]


def create_lot(
    *,
    ledger_id: int,
    user_id: int,
    source: str,
    amount_uah: float,
    expires_at: str | None,
) -> int:
    now = kyiv_now_str()
    amt = round(float(amount_uah), 2)
    cursor.execute(
        """
        INSERT INTO bonus_lots (
            ledger_id, user_id, source, amount_uah, remaining_uah, expires_at, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (int(ledger_id), int(user_id), source, amt, amt, expires_at, now),
    )
    conn.commit()
    return int(cursor.lastrowid)


def allocate_spend(user_id: int, spend_uah: float) -> float:
    """Reduce lot remainders (soonest expiry first). Returns unallocated spend."""
    left = round(float(spend_uah), 2)
    if left <= 0:
        return 0.0
    rows = cursor.execute(
        """
        SELECT id, remaining_uah FROM bonus_lots
        WHERE user_id = ? AND remaining_uah > 0 AND closed_at IS NULL
        ORDER BY
          CASE WHEN expires_at IS NULL THEN 1 ELSE 0 END,
          expires_at ASC,
          id ASC
        """,
        (int(user_id),),
    ).fetchall()
    now = kyiv_now_str()
    for row in rows:
        if left <= 0:
            break
        rem = round(float(row["remaining_uah"] or 0), 2)
        take = min(rem, left)
        new_rem = round(rem - take, 2)
        if new_rem <= 0:
            cursor.execute(
                "UPDATE bonus_lots SET remaining_uah = 0, closed_at = ? WHERE id = ?",
                (now, row["id"]),
            )
        else:
            cursor.execute(
                "UPDATE bonus_lots SET remaining_uah = ? WHERE id = ?",
                (new_rem, row["id"]),
            )
        left = round(left - take, 2)
    conn.commit()
    return left


def get_lot_remaining_for_ledger(ledger_id: int) -> float:
    row = cursor.execute(
        "SELECT remaining_uah FROM bonus_lots WHERE ledger_id = ?",
        (int(ledger_id),),
    ).fetchone()
    return round(float(row["remaining_uah"] or 0), 2) if row else 0.0


def close_lot_for_ledger(ledger_id: int) -> None:
    cursor.execute(
        """
        UPDATE bonus_lots
        SET remaining_uah = 0, closed_at = ?
        WHERE ledger_id = ? AND closed_at IS NULL
        """,
        (kyiv_now_str(), int(ledger_id)),
    )
    conn.commit()


def list_expired_lots(now_str: str) -> list[dict]:
    rows = cursor.execute(
        """
        SELECT * FROM bonus_lots
        WHERE expires_at IS NOT NULL
          AND expires_at <= ?
          AND remaining_uah > 0
          AND closed_at IS NULL
        ORDER BY expires_at ASC
        """,
        (now_str,),
    ).fetchall()
    return [dict(r) for r in rows]


REASON_TITLES_UK: dict[str, str] = {
    REASON_CASHBACK: "Кешбек з покупки",
    REASON_SPEND: "Списання на касі",
    REASON_WELCOME: "Вітальні Крафтики за реєстрацію",
    REASON_BIRTHDAY: "Крафтики за день народження",
    REASON_ANNUAL_BIRTHDAY: "Вітальний бонус у день народження",
    REASON_REFERRAL: "Крафтики за друга",
    REASON_REFERRAL_EXPIRE: "Згоряння реферальної винагороди",
    REASON_REFERRAL_REVERSE: "Скасування реферальної винагороди",
    REASON_QUEST: "Винагорода за квест",
    REASON_BURN_90D: "Згоряння Крафтиків (90 днів)",
    REASON_ADMIN_GIFT: "Подарунок від Крафт Кава",
}


def history_title(row: dict) -> str:
    if row.get("title"):
        return str(row["title"])
    return REASON_TITLES_UK.get(str(row.get("reason") or ""), "Операція з Крафтиками")
