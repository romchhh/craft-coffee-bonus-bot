"""Бонуси: день народження, щорічний подарунок; реферал — у services.referrals."""
from __future__ import annotations

import logging
from datetime import datetime

from database_functions.client_db import (
    get_user,
    mark_annual_birthday_year,
    mark_birthday_bonus_given,
)
from database_functions.settings_db import (
    get_annual_birthday_bonus_uah,
    get_birthday_bonus_uah,
)
from services import poster
from services.poster_client_cache import invalidate_client
from services.referrals import (
    bind_referrer_on_registration,
    process_referral_on_first_purchase,
    referral_link_for,
)
from utils.kyiv_time import now_kyiv

log = logging.getLogger(__name__)

__all__ = [
    "referral_link_for",
    "grant_birthday_bonus",
    "bind_referrer_on_registration",
    "process_referral_on_first_purchase",
    "process_referral_on_registration",
    "maybe_grant_annual_birthday",
    "quests_payload",
]


def grant_birthday_bonus(user_id: int, poster_client_id: int | None) -> float:
    """Одноразовий бонус за внесення дати народження (профіль +20)."""
    user = get_user(user_id)
    if not user or user.get("birthday_bonus_given"):
        return 0.0
    amount = get_birthday_bonus_uah()
    if amount <= 0 or not poster_client_id:
        mark_birthday_bonus_given(user_id)
        return 0.0
    try:
        poster.change_client_bonus(poster_client_id, amount)
        invalidate_client(poster_client_id)
    except Exception as exc:
        log.warning("birthday bonus failed user=%s: %s", user_id, exc)
        raise
    mark_birthday_bonus_given(user_id)
    return amount


def process_referral_on_registration(new_user_id: int, referred_by: int | None) -> float:
    bind_referrer_on_registration(new_user_id, referred_by)
    return 0.0


def maybe_grant_annual_birthday(user_id: int) -> float:
    """Щорічний подарунок у день народження (Київ)."""
    user = get_user(user_id)
    if not user or not user.get("registered"):
        return 0.0
    bday = user.get("birthday")
    if not bday or bday in ("0000-00-00",):
        return 0.0
    try:
        bd = datetime.strptime(str(bday)[:10], "%Y-%m-%d")
    except ValueError:
        return 0.0
    now = now_kyiv()
    month, day = bd.month, bd.day
    if month == 2 and day == 29:
        try:
            datetime(now.year, 2, 29)
        except ValueError:
            day = 28
    if now.month != month or now.day != day:
        return 0.0
    if int(user.get("annual_birthday_year") or 0) == now.year:
        return 0.0
    amount = get_annual_birthday_bonus_uah()
    cid = user.get("poster_client_id")
    if amount <= 0 or not cid:
        mark_annual_birthday_year(user_id, now.year)
        return 0.0
    try:
        poster.change_client_bonus(int(cid), amount)
        invalidate_client(int(cid))
    except Exception as exc:
        log.warning("annual birthday failed user=%s: %s", user_id, exc)
        return 0.0
    mark_annual_birthday_year(user_id, now.year)
    return amount


def quests_payload(user_id: int) -> dict:
    from services.quests import build_quests_ui

    return build_quests_ui(int(user_id))
