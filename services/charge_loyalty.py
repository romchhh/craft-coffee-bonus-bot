"""Charge, cashback tiers 1–10%, idle decay and bonus burn."""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta

from database_functions.charge_db import (
    MAX_TIER,
    MIN_TIER,
    TIER_THRESHOLDS,
    charges_to_reach,
    get_loyalty_row,
    init_loyalty_for_user,
    save_loyalty_row,
    tier_from_charges,
)
from services import poster
from utils.kyiv_time import KYIV_TZ, kyiv_now_str, now_kyiv

log = logging.getLogger(__name__)

MIN_PAY_UAH = 50
IDLE_DECAY_START_DAYS = 30
DECAY_PER_DAY = 0.5
BONUS_EXPIRE_DAYS = 90


def tier_to_percent(tier: int) -> float:
    return float(max(MIN_TIER, min(MAX_TIER, int(tier))))


def get_cashback_percent_for_user(telegram_user_id: int) -> float:
    row = get_loyalty_row(telegram_user_id)
    if not row:
        return float(MIN_TIER)
    return tier_to_percent(row["loyalty_tier"])


def parse_purchase_datetime(raw: str | None) -> datetime | None:
    if not raw:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(raw[:19], fmt)
            return dt.replace(tzinfo=KYIV_TZ)
        except ValueError:
            continue
    return None


def apply_idle_penalties(telegram_user_id: int) -> None:
    row = get_loyalty_row(telegram_user_id)
    if not row:
        return

    now = now_kyiv()
    last_purchase = parse_purchase_datetime(row.get("last_purchase_at"))
    charge = float(row["charge_points"] or 0)
    updates: dict = {}

    if last_purchase:
        days_idle = (now.date() - last_purchase.date()).days

        # Decay only unfinished progress toward the next tier (above current threshold).
        if days_idle > IDLE_DECAY_START_DAYS:
            tier = tier_from_charges(charge)
            floor = float(charges_to_reach(tier))
            progress = max(0.0, charge - floor)
            if progress > 0:
                decay_start = last_purchase.date() + timedelta(days=IDLE_DECAY_START_DAYS)
                cursor_s = row.get("charge_decay_cursor")
                if cursor_s:
                    try:
                        cursor_d = datetime.strptime(cursor_s[:10], "%Y-%m-%d").date()
                    except ValueError:
                        cursor_d = decay_start
                else:
                    cursor_d = decay_start
                if cursor_d < decay_start:
                    cursor_d = decay_start
                while cursor_d < now.date() and progress > 0:
                    progress = max(0.0, progress - DECAY_PER_DAY)
                    cursor_d += timedelta(days=1)
                charge = floor + progress
                updates["charge_points"] = charge
                updates["loyalty_tier"] = tier_from_charges(charge)
                updates["charge_decay_cursor"] = cursor_d.strftime("%Y-%m-%d")

        if days_idle >= BONUS_EXPIRE_DAYS and not row.get("bonus_burned_at"):
            cid = row.get("poster_client_id")
            if cid:
                try:
                    bal = poster.get_client_bonus_uah(cid)
                    if bal > 0:
                        poster.change_client_bonus(cid, -bal)
                except Exception as exc:
                    log.warning("bonus burn failed user=%s: %s", telegram_user_id, exc)
            updates["bonus_burned_at"] = kyiv_now_str()

    if updates:
        save_loyalty_row(telegram_user_id, **updates)


def on_purchase_closed(
    telegram_user_id: int,
    payed_sum_uah: float,
    closed_at: datetime | None = None,
) -> float:
    """Credit Charge for a purchase. 1 Charge per receipt with cash pay >= 50 UAH."""
    init_loyalty_for_user(telegram_user_id)
    row = get_loyalty_row(telegram_user_id)
    if not row:
        return 0.0

    at = closed_at or now_kyiv()
    payed = float(payed_sum_uah or 0)
    add = 1.0 if payed + 1e-9 >= MIN_PAY_UAH else 0.0

    charge = float(row["charge_points"] or 0) + add
    tier = tier_from_charges(charge)

    save_loyalty_row(
        telegram_user_id,
        loyalty_tier=tier,
        charge_points=round(charge, 2),
        last_purchase_at=at.strftime("%Y-%m-%d %H:%M:%S"),
        last_charge_visit_at=at.strftime("%Y-%m-%d %H:%M:%S") if add else row.get("last_charge_visit_at"),
        charge_visit_day=at.strftime("%Y-%m-%d") if add else row.get("charge_visit_day"),
        charge_decay_cursor=None,
        bonus_burned_at=None,
    )
    return add


def build_loyalty_ui(telegram_user_id: int, bonus_uah: float) -> dict:
    init_loyalty_for_user(telegram_user_id)
    apply_idle_penalties(telegram_user_id)
    row = get_loyalty_row(telegram_user_id) or {}

    charge = float(row.get("charge_points") or 0)
    tier = tier_from_charges(charge)
    if int(row.get("loyalty_tier") or 0) != tier:
        save_loyalty_row(telegram_user_id, loyalty_tier=tier)
    percent = tier_to_percent(tier)
    next_tier = min(tier + 1, MAX_TIER)
    next_percent = tier_to_percent(next_tier) if tier < MAX_TIER else percent
    goal = float(charges_to_reach(next_tier)) if tier < MAX_TIER else float(charges_to_reach(MAX_TIER))
    floor = float(charges_to_reach(tier))
    remaining = max(0.0, goal - charge) if tier < MAX_TIER else 0.0
    # Progress bar within current → next segment
    segment = max(1.0, goal - floor)
    progress_in_segment = min(segment, max(0.0, charge - floor))

    bonus_hint = None
    last_purchase = parse_purchase_datetime(row.get("last_purchase_at"))
    if last_purchase and bonus_uah > 0:
        expire = last_purchase.date() + timedelta(days=BONUS_EXPIRE_DAYS)
        bonus_hint = {
            "date": expire.strftime("%d.%m.%Y"),
            "amount": math.floor(bonus_uah * 100) / 100,
            "days_without_purchase": BONUS_EXPIRE_DAYS,
        }

    how_next = None
    if tier < MAX_TIER:
        how_next = {
            "target_percent": next_percent,
            "need_charges": int(goal),
            "remaining": int(math.ceil(remaining)),
            "per_check": f"1 Заряд = чек від {MIN_PAY_UAH:g} грн",
        }

    return {
        "cashback_percent": percent,
        "next_percent": next_percent,
        "charge": round(charge, 1),
        "charge_goal": int(goal) if tier < MAX_TIER else int(charges_to_reach(MAX_TIER)),
        "charge_floor": int(floor),
        "charge_remaining": round(remaining, 1),
        "charge_segment": round(segment, 1),
        "charge_in_segment": round(progress_in_segment, 1),
        "tier": tier,
        "max_tier": MAX_TIER,
        "levels": list(range(MIN_TIER, MAX_TIER + 1)),
        "thresholds": {str(k): v for k, v in TIER_THRESHOLDS.items()},
        "bonus_hint": bonus_hint,
        "how_next": how_next,
        "min_check_uah": MIN_PAY_UAH,
    }
