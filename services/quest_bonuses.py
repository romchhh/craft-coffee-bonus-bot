"""Birthday bonuses (one-time profile and annual)."""
from __future__ import annotations

import logging
from datetime import datetime

from database_functions.client_db import (
    card_age_days,
    get_user,
    mark_annual_birthday_year,
    mark_birthday_bonus_given,
    touch_bonus_accrual,
)
from database_functions.settings_db import (
    get_annual_birthday_bonus_uah,
    get_birthday_bonus_uah,
)
from services import poster
from services.poster_client_cache import invalidate_client
from utils.kyiv_time import now_kyiv

log = logging.getLogger(__name__)

# Annual gift on birthday: card must exist ≥5 days before that birthday.
ANNUAL_BIRTHDAY_MIN_CARD_AGE_DAYS = 5


def grant_birthday_bonus(user_id: int, poster_client_id: int | None) -> float:
    """One-time reward for filling birthday — paid immediately (no card-age wait)."""
    user = get_user(user_id)
    if not user or user.get("birthday_bonus_given"):
        return 0.0
    if int(user.get("bonuses_blocked") or 0):
        log.info("birthday bonus skipped — blocked user=%s", user_id)
        return 0.0
    amount = get_birthday_bonus_uah()
    if amount <= 0 or not poster_client_id:
        mark_birthday_bonus_given(user_id)
        return 0.0
    from database_functions import bonus_ledger_db as ldb
    from services.bonus_ops import apply_bonus_delta

    result = apply_bonus_delta(
        op_key=f"birthday:user:{user_id}",
        amount_uah=amount,
        reason=ldb.REASON_BIRTHDAY,
        user_id=user_id,
        poster_client_id=int(poster_client_id),
        title=ldb.REASON_TITLES_UK[ldb.REASON_BIRTHDAY],
        create_lot=True,
    )
    if result.get("status") != "ok":
        log.warning("birthday bonus failed user=%s: %s", user_id, result)
        raise RuntimeError(result.get("error") or "birthday_bonus_failed")
    mark_birthday_bonus_given(user_id)
    touch_bonus_accrual(user_id)
    try:
        from services.wallet_sync import sync_wallets_for_user

        sync_wallets_for_user(user_id, bonus=result.get("balance_after"))
    except Exception:
        pass
    return amount


def maybe_grant_annual_birthday(user_id: int) -> float:
    """
    Greeting bonus on the actual birthday day.
    Only if the loyalty card was registered at least 5 days before this birthday.
    """
    user = get_user(user_id)
    if not user or not user.get("registered"):
        return 0.0
    if int(user.get("bonuses_blocked") or 0):
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

    age = card_age_days(user)
    if age is None or age < ANNUAL_BIRTHDAY_MIN_CARD_AGE_DAYS:
        log.info(
            "annual birthday skipped — card registered < %sd before birthday user=%s age=%s",
            ANNUAL_BIRTHDAY_MIN_CARD_AGE_DAYS,
            user_id,
            age,
        )
        # Mark year so we don't retry spam; they weren't eligible this year.
        mark_annual_birthday_year(user_id, now.year)
        return 0.0

    amount = get_annual_birthday_bonus_uah()
    cid = user.get("poster_client_id")
    if amount <= 0 or not cid:
        mark_annual_birthday_year(user_id, now.year)
        return 0.0
    from database_functions import bonus_ledger_db as ldb
    from services.bonus_ops import apply_bonus_delta

    result = apply_bonus_delta(
        op_key=f"annual_birthday:user:{user_id}:{now.year}",
        amount_uah=amount,
        reason=ldb.REASON_ANNUAL_BIRTHDAY,
        user_id=user_id,
        poster_client_id=int(cid),
        title=ldb.REASON_TITLES_UK[ldb.REASON_ANNUAL_BIRTHDAY],
        create_lot=True,
    )
    if result.get("status") != "ok":
        log.warning("annual birthday failed user=%s: %s", user_id, result)
        return 0.0
    mark_annual_birthday_year(user_id, now.year)
    touch_bonus_accrual(user_id)
    try:
        from services.wallet_sync import sync_wallets_for_user

        sync_wallets_for_user(user_id, bonus=result.get("balance_after"))
    except Exception:
        pass
    return amount


def quests_payload(user_id: int) -> dict:
    from services.quests import build_quests_ui

    return build_quests_ui(int(user_id))
