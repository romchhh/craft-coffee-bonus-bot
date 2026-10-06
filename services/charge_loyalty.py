"""Charge, cashback tiers 1–10%, idle decay and bonus burn."""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta

from utils.kyiv_time import KYIV_TZ, now_kyiv, kyiv_now_str

from database_functions.charge_db import (
    CHARGE_GOAL,
    MAX_TIER,
    MIN_TIER,
    get_loyalty_row,
    init_loyalty_for_user,
    save_loyalty_row,
)
from urllib.parse import quote

from config import MAPS_URL
from services import poster

log = logging.getLogger(__name__)

MIN_PAY_UAH = 50
HIGH_PAY_UAH = 150
MIN_GAP_HOURS = 2
IDLE_DECAY_START_DAYS = 30
DECAY_PER_DAY = 0.5
BONUS_EXPIRE_DAYS = 90


def tier_to_percent(tier: int) -> float:
    return float(max(MIN_TIER, min(MAX_TIER, int(tier))))


def get_cashback_percent_for_user(telegram_user_id: int) -> float:
    row = get_loyalty_row(telegram_user_id)
    if not row:
        return 5.0
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


def _charge_for_amount(payed_uah: float, first_of_day: bool) -> float:
    if payed_uah < MIN_PAY_UAH:
        return 0.0
    high = payed_uah > HIGH_PAY_UAH
    if first_of_day:
        return 2.0 if high else 1.0
    return 1.5 if high else 0.5


def _level_up(tier: int, charge: float) -> tuple[int, float]:
    while charge >= CHARGE_GOAL and tier < MAX_TIER:
        charge -= CHARGE_GOAL
        tier += 1
    return tier, charge


def apply_idle_penalties(telegram_user_id: int) -> None:
    row = get_loyalty_row(telegram_user_id)
    if not row:
        return

    now = now_kyiv()
    last_purchase = parse_purchase_datetime(row.get("last_purchase_at"))
    charge = row["charge_points"]
    updates: dict = {}

    if last_purchase:
        days_idle = (now.date() - last_purchase.date()).days

        if days_idle > IDLE_DECAY_START_DAYS and charge > 0:
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
            while cursor_d < now.date() and charge > 0:
                charge = max(0.0, charge - DECAY_PER_DAY)
                cursor_d += timedelta(days=1)
            updates["charge_points"] = charge
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
    """Credit Charge for a purchase. Returns Charge added."""
    init_loyalty_for_user(telegram_user_id)
    row = get_loyalty_row(telegram_user_id)
    if not row:
        return 0.0

    at = closed_at or now_kyiv()
    payed = float(payed_sum_uah or 0)

    last_visit = parse_purchase_datetime(row.get("last_charge_visit_at"))
    if last_visit and (at - last_visit).total_seconds() < MIN_GAP_HOURS * 3600:
        save_loyalty_row(
            telegram_user_id,
            last_purchase_at=at.strftime("%Y-%m-%d %H:%M:%S"),
            bonus_burned_at=None,
        )
        return 0.0

    day_key = at.strftime("%Y-%m-%d")
    first_of_day = row.get("charge_visit_day") != day_key
    add = _charge_for_amount(payed, first_of_day)

    tier = row["loyalty_tier"]
    charge = row["charge_points"]
    if add > 0:
        charge += add
        tier, charge = _level_up(tier, charge)
        visit_day = day_key
        visit_at = at.strftime("%Y-%m-%d %H:%M:%S")
    else:
        visit_day = row.get("charge_visit_day")
        visit_at = row.get("last_charge_visit_at")

    save_loyalty_row(
        telegram_user_id,
        loyalty_tier=tier,
        charge_points=round(charge, 2),
        last_purchase_at=at.strftime("%Y-%m-%d %H:%M:%S"),
        last_charge_visit_at=visit_at,
        charge_visit_day=visit_day,
        charge_decay_cursor=None,
        bonus_burned_at=None,
    )
    return add


def get_maps_url() -> str:
    if MAPS_URL:
        return MAPS_URL
    try:
        for spot in poster.get_spots() or []:
            lat, lng = spot.get("lat"), spot.get("lng")
            if lat and lng:
                return f"https://www.google.com/maps?q={lat},{lng}"
            addr = (spot.get("spot_adress") or spot.get("spot_address") or "").strip()
            name = (spot.get("spot_name") or spot.get("name") or "Craft Coffee").strip()
            q = addr or name
            if q:
                return f"https://www.google.com/maps/search/?api=1&query={quote(q)}"
    except Exception as exc:
        log.debug("maps url from spots: %s", exc)
    return "https://www.google.com/maps/search/?api=1&query=Craft+Coffee"


def build_loyalty_ui(telegram_user_id: int, bonus_uah: float) -> dict:
    init_loyalty_for_user(telegram_user_id)
    apply_idle_penalties(telegram_user_id)
    row = get_loyalty_row(telegram_user_id) or {}

    tier = int(row.get("loyalty_tier") or MIN_TIER)
    charge = float(row.get("charge_points") or 0)
    next_tier = min(tier + 1, MAX_TIER)
    percent = tier_to_percent(tier)
    next_percent = tier_to_percent(next_tier) if tier < MAX_TIER else percent
    remaining = max(0.0, CHARGE_GOAL - charge) if tier < MAX_TIER else 0.0

    bonus_hint = None
    last_purchase = parse_purchase_datetime(row.get("last_purchase_at"))
    if last_purchase and bonus_uah > 0:
        expire = last_purchase.date() + timedelta(days=BONUS_EXPIRE_DAYS)
        bonus_hint = {
            "date": expire.strftime("%d.%m.%Y"),
            "amount": math.floor(bonus_uah * 100) / 100,
            "days_without_purchase": BONUS_EXPIRE_DAYS,
        }

    return {
        "cashback_percent": percent,
        "next_percent": next_percent,
        "charge": round(charge, 1),
        "charge_goal": CHARGE_GOAL,
        "charge_remaining": round(remaining, 1),
        "tier": tier,
        "max_tier": MAX_TIER,
        "levels": list(range(MIN_TIER, MAX_TIER + 1)),
        "bonus_hint": bonus_hint,
        "maps_url": get_maps_url(),
    }
