"""Charge program state and cashback tiers."""
from __future__ import annotations

from datetime import datetime

from database_functions.client_db import conn, cursor, get_user
from database_functions.settings_db import get_cashback_percent


CHARGE_GOAL = 50
MAX_TIER = 10
MIN_TIER = 1


def migrate_loyalty_columns() -> None:
    cols = {row[1] for row in cursor.execute("PRAGMA table_info(users)").fetchall()}
    additions = {
        "loyalty_tier": "INTEGER",
        "charge_points": "REAL",
        "protected_tier": "INTEGER",
        "last_purchase_at": "TEXT",
        "last_charge_visit_at": "TEXT",
        "charge_visit_day": "TEXT",
        "charge_decay_cursor": "TEXT",
        "bonus_burned_at": "TEXT",
    }
    defaults = {
        "loyalty_tier": "5",
        "charge_points": "0",
        "protected_tier": "1",
    }
    for name, typedef in additions.items():
        if name not in cols:
            default = defaults.get(name)
            if default is not None:
                cursor.execute(
                    f"ALTER TABLE users ADD COLUMN {name} {typedef} DEFAULT {default}"
                )
            else:
                cursor.execute(f"ALTER TABLE users ADD COLUMN {name} {typedef}")
    conn.commit()
    _backfill_tiers()


def _backfill_tiers() -> None:
    try:
        base = int(round(get_cashback_percent()))
    except Exception:
        from config import CASHBACK_PERCENT

        base = int(round(float(CASHBACK_PERCENT)))
    base = max(MIN_TIER, min(MAX_TIER, base))
    cursor.execute(
        """
        UPDATE users
        SET loyalty_tier = ?, protected_tier = COALESCE(protected_tier, ?)
        WHERE loyalty_tier IS NULL OR loyalty_tier = 0
        """,
        (base, MIN_TIER),
    )
    conn.commit()


def init_loyalty_for_user(user_id: int) -> None:
    tier = int(round(get_cashback_percent()))
    tier = max(MIN_TIER, min(MAX_TIER, tier))
    cursor.execute(
        """
        UPDATE users SET
            loyalty_tier = COALESCE(loyalty_tier, ?),
            charge_points = COALESCE(charge_points, 0),
            protected_tier = COALESCE(protected_tier, ?)
        WHERE user_id = ?
        """,
        (tier, MIN_TIER, user_id),
    )
    conn.commit()


def get_loyalty_row(user_id: int) -> dict | None:
    user = get_user(user_id)
    if not user:
        return None
    return {
        "loyalty_tier": int(user.get("loyalty_tier") or MIN_TIER),
        "charge_points": float(user.get("charge_points") or 0),
        "protected_tier": int(user.get("protected_tier") or MIN_TIER),
        "last_purchase_at": user.get("last_purchase_at"),
        "last_charge_visit_at": user.get("last_charge_visit_at"),
        "charge_visit_day": user.get("charge_visit_day"),
        "charge_decay_cursor": user.get("charge_decay_cursor"),
        "bonus_burned_at": user.get("bonus_burned_at"),
        "poster_client_id": user.get("poster_client_id"),
    }


def save_loyalty_row(user_id: int, **fields) -> None:
    allowed = {
        "loyalty_tier",
        "charge_points",
        "protected_tier",
        "last_purchase_at",
        "last_charge_visit_at",
        "charge_visit_day",
        "charge_decay_cursor",
        "bonus_burned_at",
    }
    parts = []
    values = []
    for key, val in fields.items():
        if key not in allowed:
            continue
        parts.append(f"{key} = ?")
        values.append(val)
    if not parts:
        return
    values.append(user_id)
    cursor.execute(f"UPDATE users SET {', '.join(parts)} WHERE user_id = ?", values)
    conn.commit()
