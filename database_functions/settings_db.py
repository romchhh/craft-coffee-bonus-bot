"""Loyalty settings (welcome bonus, cashback %)."""
from __future__ import annotations

from config import (
    ACH_DAYS_15_REWARD_UAH,
    ACH_DAYS_30_REWARD_UAH,
    ACH_DAYS_5_REWARD_UAH,
    ANNUAL_BIRTHDAY_BONUS_UAH,
    BIRTHDAY_BONUS_UAH,
    CASHBACK_PERCENT,
    QUEST_COMBO_REWARD_UAH,
    QUEST_DRINKS_REWARD_UAH,
    QUEST_VISITS_REWARD_UAH,
    QUEST_WINDOW_DAYS,
    REFERRAL_BONUS_UAH,
    WELCOME_BONUS_UAH,
)
from database_functions.db import get_connection

conn = get_connection()
cursor = conn.cursor()

REWARD_SETTING_KEYS = (
    "welcome_bonus_uah",
    "birthday_bonus_uah",
    "annual_birthday_bonus_uah",
    "referral_bonus_uah",
    "quest_visits_reward_uah",
    "quest_combo_reward_uah",
    "quest_drinks_reward_uah",
    "ach_days_5_reward_uah",
    "ach_days_15_reward_uah",
    "ach_days_30_reward_uah",
)


def _defaults() -> dict[str, str]:
    return {
        "welcome_bonus_uah": str(WELCOME_BONUS_UAH),
        "cashback_percent": str(CASHBACK_PERCENT),
        "birthday_bonus_uah": str(BIRTHDAY_BONUS_UAH),
        "annual_birthday_bonus_uah": str(ANNUAL_BIRTHDAY_BONUS_UAH),
        "referral_bonus_uah": str(REFERRAL_BONUS_UAH),
        "quest_visits_reward_uah": str(QUEST_VISITS_REWARD_UAH),
        "quest_combo_reward_uah": str(QUEST_COMBO_REWARD_UAH),
        "quest_drinks_reward_uah": str(QUEST_DRINKS_REWARD_UAH),
        "ach_days_5_reward_uah": str(ACH_DAYS_5_REWARD_UAH),
        "ach_days_15_reward_uah": str(ACH_DAYS_15_REWARD_UAH),
        "ach_days_30_reward_uah": str(ACH_DAYS_30_REWARD_UAH),
        "quest_window_days": str(QUEST_WINDOW_DAYS),
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


def get_birthday_bonus_uah() -> float:
    try:
        return float(get_setting("birthday_bonus_uah", str(BIRTHDAY_BONUS_UAH)))
    except ValueError:
        return float(BIRTHDAY_BONUS_UAH)


def get_referral_bonus_uah() -> float:
    try:
        return float(get_setting("referral_bonus_uah", str(REFERRAL_BONUS_UAH)))
    except ValueError:
        return float(REFERRAL_BONUS_UAH)


def _float_setting(key: str, fallback: float) -> float:
    try:
        return float(get_setting(key, str(fallback)))
    except ValueError:
        return float(fallback)


def get_annual_birthday_bonus_uah() -> float:
    return _float_setting("annual_birthday_bonus_uah", ANNUAL_BIRTHDAY_BONUS_UAH)


def get_quest_visits_reward_uah() -> float:
    return _float_setting("quest_visits_reward_uah", QUEST_VISITS_REWARD_UAH)


def get_quest_combo_reward_uah() -> float:
    return _float_setting("quest_combo_reward_uah", QUEST_COMBO_REWARD_UAH)


def get_quest_drinks_reward_uah() -> float:
    return _float_setting("quest_drinks_reward_uah", QUEST_DRINKS_REWARD_UAH)


def get_ach_days_5_reward_uah() -> float:
    return _float_setting("ach_days_5_reward_uah", ACH_DAYS_5_REWARD_UAH)


def get_ach_days_15_reward_uah() -> float:
    return _float_setting("ach_days_15_reward_uah", ACH_DAYS_15_REWARD_UAH)


def get_ach_days_30_reward_uah() -> float:
    return _float_setting("ach_days_30_reward_uah", ACH_DAYS_30_REWARD_UAH)


def get_quest_window_days() -> int:
    try:
        return max(1, int(float(get_setting("quest_window_days", str(QUEST_WINDOW_DAYS)))))
    except ValueError:
        return int(QUEST_WINDOW_DAYS)


def set_reward_uah(key: str, amount: float) -> None:
    if key not in REWARD_SETTING_KEYS and key != "cashback_percent":
        raise ValueError(f"unknown reward key: {key}")
    set_setting(key, f"{float(amount):g}")


def rewards_snapshot() -> dict[str, float]:
    return {
        "welcome_bonus_uah": get_welcome_bonus_uah(),
        "birthday_bonus_uah": get_birthday_bonus_uah(),
        "annual_birthday_bonus_uah": get_annual_birthday_bonus_uah(),
        "referral_bonus_uah": get_referral_bonus_uah(),
        "quest_visits_reward_uah": get_quest_visits_reward_uah(),
        "quest_combo_reward_uah": get_quest_combo_reward_uah(),
        "quest_drinks_reward_uah": get_quest_drinks_reward_uah(),
        "ach_days_5_reward_uah": get_ach_days_5_reward_uah(),
        "ach_days_15_reward_uah": get_ach_days_15_reward_uah(),
        "ach_days_30_reward_uah": get_ach_days_30_reward_uah(),
        "quest_window_days": float(get_quest_window_days()),
        "cashback_percent": get_cashback_percent(),
    }


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
    from utils.kyiv_time import kyiv_now_str

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
            kyiv_now_str(),
        ),
    )
    conn.commit()


def mark_transaction_ignored(
    transaction_id: str | int,
    *,
    poster_client_id: int | None = None,
    payed_sum_uah: float = 0,
    bonus_spent_uah: float = 0,
) -> None:
    """Receipt seen; no bonuses (not a bot client, etc.)."""
    mark_transaction_processed(
        transaction_id,
        poster_client_id=poster_client_id,
        telegram_user_id=None,
        payed_sum_uah=payed_sum_uah,
        bonus_uah=0,
        bonus_spent_uah=bonus_spent_uah,
    )


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
