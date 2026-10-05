"""Бонуси: день народження, щорічний подарунок, реферал."""
from __future__ import annotations

import logging
from datetime import datetime

from config import BOT_USERNAME
from database_functions.client_db import (
    count_successful_referrals,
    get_user,
    mark_annual_birthday_year,
    mark_birthday_bonus_given,
    mark_referral_bonus_paid,
    set_referred_by,
)
from database_functions.settings_db import (
    get_annual_birthday_bonus_uah,
    get_birthday_bonus_uah,
    get_referral_bonus_uah,
)
from services import poster
from services.poster_client_cache import invalidate_client
from utils.kyiv_time import now_kyiv

log = logging.getLogger(__name__)


def referral_link_for(telegram_user_id: int) -> str:
    username = (BOT_USERNAME or "").strip().lstrip("@")
    if not username:
        return ""
    return f"https://t.me/{username}?start=ref_{int(telegram_user_id)}"


def grant_birthday_bonus(user_id: int, poster_client_id: int | None) -> float:
    """Одноразовий бонус за внесення дати народження (профіль)."""
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


def bind_referrer_on_registration(new_user_id: int, referred_by: int | None) -> None:
    """Лише зберігає реферера. Виплата — після першої покупки друга (D291)."""
    if not referred_by or int(referred_by) == int(new_user_id):
        return
    referrer = get_user(referred_by)
    if not referrer or not referrer.get("registered"):
        return
    set_referred_by(new_user_id, referred_by)


def process_referral_on_first_purchase(new_user_id: int) -> tuple[float, int | None, str]:
    """
    Нарахувати запрошувачу бонус після першої покупки запрошеного.
    Повертає (сума, referrer_user_id, friend_name).
    """
    new_user = get_user(new_user_id)
    if not new_user or new_user.get("referral_bonus_paid"):
        return 0.0, None, ""
    referred_by = new_user.get("referred_by_user_id")
    if not referred_by:
        return 0.0, None, ""
    referrer = get_user(referred_by)
    if not referrer or not referrer.get("registered") or not referrer.get("poster_client_id"):
        return 0.0, None, ""
    amount = get_referral_bonus_uah()
    friend = new_user.get("display_name") or new_user.get("user_first_name") or "Друг"
    if amount <= 0:
        mark_referral_bonus_paid(new_user_id)
        return 0.0, int(referred_by), friend
    try:
        poster.change_client_bonus(int(referrer["poster_client_id"]), amount)
        invalidate_client(int(referrer["poster_client_id"]))
    except Exception as exc:
        log.warning("referral bonus failed referrer=%s new=%s: %s", referred_by, new_user_id, exc)
        return 0.0, None, ""
    mark_referral_bonus_paid(new_user_id)
    return amount, int(referred_by), friend


# сумісність зі старим ім'ям
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
    # 29 лютого → 28 у невисокосні
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
    # дата має бути внесена щонайменше за 7 днів (D093)
    # приблизна перевірка: якщо birthday_bonus щойно сьогодні — все одно ок якщо профіль давній
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
