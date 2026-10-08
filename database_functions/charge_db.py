"""Charge program state and cashback tiers."""
from __future__ import annotations

import random

from database_functions.client_db import conn, cursor, get_user

MAX_TIER = 10
MIN_TIER = 1

# Cumulative Charge needed to reach each cashback % (1% starts at 0).
TIER_THRESHOLDS: dict[int, int] = {
    1: 0,
    2: 15,
    3: 25,
    4: 50,
    5: 100,
    6: 200,
    7: 400,
    8: 800,
    9: 1600,
    10: 3000,
}


def charges_to_reach(tier: int) -> int:
    return int(TIER_THRESHOLDS.get(int(tier), 0))


def tier_from_charges(total_charges: float) -> int:
    total = float(total_charges or 0)
    tier = MIN_TIER
    for t in range(MIN_TIER + 1, MAX_TIER + 1):
        if total + 1e-9 >= TIER_THRESHOLDS[t]:
            tier = t
        else:
            break
    return tier


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
        "card_short_id": "TEXT",
    }
    defaults = {
        "loyalty_tier": "1",
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
    _normalize_starting_tiers()
    _ensure_short_ids()


def _normalize_starting_tiers() -> None:
    """New clients start at 1%. Reset idle accounts still on the old default 5%."""
    cursor.execute(
        """
        UPDATE users
        SET loyalty_tier = 1, protected_tier = COALESCE(protected_tier, 1)
        WHERE (loyalty_tier IS NULL OR loyalty_tier = 0)
           OR (
                COALESCE(charge_points, 0) = 0
                AND last_purchase_at IS NULL
                AND COALESCE(loyalty_tier, 0) = 5
           )
        """
    )
    conn.commit()


def _used_card_numbers() -> set[str]:
    """All Poster/display card numbers already taken in our DB."""
    used: set[str] = set()
    for row in cursor.execute(
        "SELECT card_number, card_short_id FROM users "
        "WHERE card_number IS NOT NULL OR card_short_id IS NOT NULL"
    ).fetchall():
        for key in ("card_number", "card_short_id"):
            val = str(row[key] or "").strip()
            if val:
                used.add(val)
    return used


def _ensure_short_ids() -> None:
    """Keep card_short_id identical to Poster card_number (no separate code)."""
    rows = cursor.execute(
        "SELECT user_id, card_number, card_short_id FROM users WHERE registered = 1"
    ).fetchall()
    used = _used_card_numbers()
    for row in rows:
        card = str(row["card_number"] or "").strip()
        short = str(row["card_short_id"] or "").strip()
        if card:
            if short != card:
                cursor.execute(
                    "UPDATE users SET card_short_id = ? WHERE user_id = ?",
                    (card, row["user_id"]),
                )
            continue
        if short:
            continue
        code = _next_free_card_number(used)
        used.add(code)
        cursor.execute(
            "UPDATE users SET card_number = ?, card_short_id = ? WHERE user_id = ?",
            (code, code, row["user_id"]),
        )
    conn.commit()


def _next_free_card_number(used: set[str] | None = None) -> str:
    """Allocate an 8-digit Poster card number with a unique last-4 suffix."""
    if used is None:
        used = _used_card_numbers()
    used_tails = {str(s)[-4:].zfill(4) for s in used if str(s).isdigit() and len(str(s)) >= 4}
    tails = list(range(1000, 10000))
    random.shuffle(tails)
    for tail_n in tails:
        tail = f"{tail_n:04d}"
        if tail in used_tails:
            continue
        for _ in range(40):
            head = f"{random.randint(10, 99):02d}{random.randint(10, 99):02d}"
            code = head + tail
            if code not in used:
                return code
    raise RuntimeError("card_number space exhausted")


def allocate_card_number() -> str:
    """New bonus card number for Poster (8 digits, unique last-4)."""
    return _next_free_card_number()


def allocate_card_short_id() -> str:
    """Alias — short id is the same as Poster card_number."""
    return allocate_card_number()


def init_loyalty_for_user(user_id: int) -> None:
    cursor.execute(
        """
        UPDATE users SET
            loyalty_tier = COALESCE(loyalty_tier, 1),
            charge_points = COALESCE(charge_points, 0),
            protected_tier = COALESCE(protected_tier, 1)
        WHERE user_id = ?
        """,
        (user_id,),
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
        "card_short_id": user.get("card_short_id"),
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
        "card_short_id",
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
