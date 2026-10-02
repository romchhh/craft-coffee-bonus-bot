"""Налаштування лояльності (вітальний бонус, % кешбеку)."""
from __future__ import annotations

import sqlite3

from config import CASHBACK_PERCENT, DB_PATH, WELCOME_BONUS_UAH

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()


def _defaults() -> dict[str, str]:
    return {
        "welcome_bonus_uah": str(WELCOME_BONUS_UAH),
        "cashback_percent": str(CASHBACK_PERCENT),
    }


def create_settings_table():
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS processed_transactions (
            transaction_id TEXT PRIMARY KEY,
            poster_client_id INTEGER,
            telegram_user_id INTEGER,
            payed_sum_uah REAL,
            bonus_uah REAL,
            processed_at TEXT
        )
        """
    )
    conn.commit()
    _migrate_processed_transactions()
    for key, value in _defaults().items():
        cursor.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )
    conn.commit()


def _migrate_processed_transactions() -> None:
    cols = {row[1] for row in cursor.execute("PRAGMA table_info(processed_transactions)").fetchall()}
    if "bonus_spent_uah" not in cols:
        cursor.execute(
            "ALTER TABLE processed_transactions ADD COLUMN bonus_spent_uah REAL DEFAULT 0"
        )
        conn.commit()


def get_setting(key: str, default: str | None = None) -> str:
    row = cursor.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if row:
        return row["value"]
    if default is not None:
        return default
    return _defaults().get(key, "")


def set_setting(key: str, value: str) -> None:
    cursor.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value)),
    )
    conn.commit()


def get_welcome_bonus_uah() -> float:
    try:
        return float(get_setting("welcome_bonus_uah", str(WELCOME_BONUS_UAH)))
    except ValueError:
        return float(WELCOME_BONUS_UAH)


def get_cashback_percent() -> float:
    try:
        return float(get_setting("cashback_percent", str(CASHBACK_PERCENT)))
    except ValueError:
        return float(CASHBACK_PERCENT)


def set_welcome_bonus_uah(amount: float) -> None:
    set_setting("welcome_bonus_uah", f"{float(amount):g}")


def set_cashback_percent(percent: float) -> None:
    set_setting("cashback_percent", f"{float(percent):g}")


def is_transaction_processed(transaction_id: str | int) -> bool:
    row = cursor.execute(
        "SELECT 1 FROM processed_transactions WHERE transaction_id = ?",
        (str(transaction_id),),
    ).fetchone()
    return row is not None


def mark_transaction_processed(
    transaction_id: str | int,
    *,
    poster_client_id: int | None,
    telegram_user_id: int | None,
    payed_sum_uah: float,
    bonus_uah: float,
    bonus_spent_uah: float = 0,
) -> None:
    from datetime import datetime

    cursor.execute(
        """
        INSERT OR IGNORE INTO processed_transactions (
            transaction_id, poster_client_id, telegram_user_id,
            payed_sum_uah, bonus_uah, bonus_spent_uah, processed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(transaction_id),
            poster_client_id,
            telegram_user_id,
            payed_sum_uah,
            bonus_uah,
            float(bonus_spent_uah or 0),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    conn.commit()


def list_bonus_accruals_for_user(telegram_user_id: int, limit: int = 40) -> list[dict]:
    rows = cursor.execute(
        """
        SELECT transaction_id, payed_sum_uah, bonus_uah, processed_at
        FROM processed_transactions
        WHERE telegram_user_id = ? AND bonus_uah > 0
        ORDER BY processed_at DESC
        LIMIT ?
        """,
        (int(telegram_user_id), limit),
    ).fetchall()
    return [dict(r) for r in rows]
