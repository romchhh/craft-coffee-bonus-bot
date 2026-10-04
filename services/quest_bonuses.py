"""Бонуси за квести: день народження та реферал."""
from __future__ import annotations

import logging

from config import BOT_USERNAME
from database_functions.client_db import (
    count_successful_referrals,
    get_user,
    mark_birthday_bonus_given,
    mark_referral_bonus_paid,
    set_referred_by,
)
from database_functions.settings_db import get_birthday_bonus_uah, get_referral_bonus_uah
from services import poster
from services.poster_client_cache import invalidate_client

log = logging.getLogger(__name__)


def referral_link_for(telegram_user_id: int) -> str:
    username = (BOT_USERNAME or "").strip().lstrip("@")
    if not username:
        return ""
    return f"https://t.me/{username}?start=ref_{int(telegram_user_id)}"


def grant_birthday_bonus(user_id: int, poster_client_id: int | None) -> float:
    """Нарахувати бонус за день народження один раз. Повертає суму або 0."""
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
    """
    Після першої реєстрації нового клієнта: +бонус запросившому.
    Повертає нараховану суму рефереру (0 якщо нічого).
    """
    if not referred_by or int(referred_by) == int(new_user_id):
        return 0.0
    referrer = get_user(referred_by)
    if not referrer or not referrer.get("registered") or not referrer.get("poster_client_id"):
        return 0.0
    new_user = get_user(new_user_id)
    if not new_user:
        return 0.0
    if new_user.get("referral_bonus_paid"):
        return 0.0
    amount = get_referral_bonus_uah()
    if amount <= 0:
        set_referred_by(new_user_id, referred_by)
        mark_referral_bonus_paid(new_user_id)
        return 0.0
    try:
        poster.change_client_bonus(int(referrer["poster_client_id"]), amount)
        invalidate_client(int(referrer["poster_client_id"]))
    except Exception as exc:
        log.warning("referral bonus failed referrer=%s new=%s: %s", referred_by, new_user_id, exc)
        return 0.0
    set_referred_by(new_user_id, referred_by)
    mark_referral_bonus_paid(new_user_id)
    return amount


def quests_payload(user_id: int) -> dict:
    user = get_user(user_id) or {}
    birthday = user.get("birthday")
    has_bday = bool(birthday and birthday != "0000-00-00")
    return {
        "birthday_bonus_uah": get_birthday_bonus_uah(),
        "referral_bonus_uah": get_referral_bonus_uah(),
        "birthday_filled": has_bday,
        "birthday_bonus_claimed": bool(user.get("birthday_bonus_given")),
        "referral_link": referral_link_for(user_id),
        "referrals_count": count_successful_referrals(user_id),
    }
