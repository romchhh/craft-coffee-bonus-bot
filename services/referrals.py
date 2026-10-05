"""Реферальна програма Kraft (D291)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from config import (
    BOT_USERNAME,
    REFERRAL_BONUS_UAH,
    REFERRAL_DAILY_AUTO_LIMIT,
    REFERRAL_INVITE_TTL_DAYS,
    REFERRAL_MIN_CASH_UAH,
    REFERRAL_PURCHASE_WINDOW_DAYS,
    REFERRAL_REWARD_VALID_DAYS,
)
from database_functions.client_db import get_user, mark_referral_bonus_paid
from database_functions import referrals_db as rdb
from database_functions.settings_db import get_referral_bonus_uah
from services import poster
from services.poster_client_cache import invalidate_client
from utils.kyiv_time import KYIV_TZ, kyiv_now_str, now_kyiv

log = logging.getLogger(__name__)


def referral_link_for(telegram_user_id: int) -> str:
    username = (BOT_USERNAME or "").strip().lstrip("@")
    if not username:
        return ""
    return f"https://t.me/{username}?start=ref_{int(telegram_user_id)}"


def current_terms() -> dict[str, Any]:
    return {
        "amount_uah": get_referral_bonus_uah(),
        "min_cash_uah": REFERRAL_MIN_CASH_UAH,
        "purchase_window_days": REFERRAL_PURCHASE_WINDOW_DAYS,
        "invite_ttl_days": REFERRAL_INVITE_TTL_DAYS,
        "reward_valid_days": REFERRAL_REWARD_VALID_DAYS,
        "daily_auto_limit": REFERRAL_DAILY_AUTO_LIMIT,
        "available_next_kyiv_midnight": True,
    }


def _parse_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    text = str(raw).strip()
    for fmt, n in (("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%d %H:%M", 16), ("%Y-%m-%d", 10)):
        try:
            return datetime.strptime(text[:n], fmt).replace(tzinfo=KYIV_TZ)
        except ValueError:
            continue
    return None


def next_kyiv_midnight(after: datetime | None = None) -> datetime:
    at = after or now_kyiv()
    if at.tzinfo is None:
        at = at.replace(tzinfo=KYIV_TZ)
    day = (at + timedelta(days=1)).date()
    return datetime(day.year, day.month, day.day, 0, 0, 0, tzinfo=KYIV_TZ)


def referrer_has_first_purchase(referrer_user_id: int) -> bool:
    user = get_user(referrer_user_id)
    if not user or not user.get("registered"):
        return False
    if user.get("last_purchase_at"):
        return True
    row = None
    try:
        from database_functions.db import get_connection

        conn = get_connection()
        row = conn.execute(
            """
            SELECT 1 FROM processed_transactions
            WHERE telegram_user_id = ? AND COALESCE(payed_sum_uah, 0) > 0
            LIMIT 1
            """,
            (int(referrer_user_id),),
        ).fetchone()
    except Exception:
        pass
    return bool(row)


def can_share_invite(referrer_user_id: int) -> bool:
    return referrer_has_first_purchase(int(referrer_user_id))


def remember_referral_click(friend_user_id: int, referrer_user_id: int) -> bool:
    """
    Перший запрошувач закріплюється. Незавершене запрошення — 30 днів.
    Повертає True, якщо referrer збережено/залишено.
    """
    if int(friend_user_id) == int(referrer_user_id):
        return False
    friend = get_user(friend_user_id)
    if friend and friend.get("registered"):
        return False
    referrer = get_user(referrer_user_id)
    if not referrer or not referrer.get("registered"):
        return False

    from database_functions.client_db import set_referred_by_sticky

    return set_referred_by_sticky(
        friend_user_id,
        referrer_user_id,
        ttl_days=REFERRAL_INVITE_TTL_DAYS,
    )


def bind_referrer_on_registration(new_user_id: int, referred_by: int | None) -> bool:
    """
    Закріплює запрошувача після реєстрації + знімок умов.
    Запрошувач має мати власну першу покупку.
    """
    if not referred_by or int(referred_by) == int(new_user_id):
        return False
    if rdb.get_by_friend(new_user_id):
        return False

    new_user = get_user(new_user_id)
    referrer = get_user(referred_by)
    if not new_user or not new_user.get("registered"):
        return False
    if not referrer or not referrer.get("registered"):
        return False
    if not referrer_has_first_purchase(int(referred_by)):
        log.info(
            "referral bind skipped: referrer %s has no first purchase (friend %s)",
            referred_by,
            new_user_id,
        )
        return False

    from database_functions.client_db import set_referred_by_sticky

    # фіксуємо sticky (якщо ще не було з кліку)
    set_referred_by_sticky(
        new_user_id,
        int(referred_by),
        ttl_days=REFERRAL_INVITE_TTL_DAYS,
        force_keep_existing=True,
    )
    fresh = get_user(new_user_id) or new_user
    actual_ref = fresh.get("referred_by_user_id")
    if not actual_ref or int(actual_ref) != int(referred_by):
        # інший запрошувач уже закріплений — не перезаписуємо
        if actual_ref:
            referred_by = int(actual_ref)
        else:
            return False

    terms = current_terms()
    amount = float(terms["amount_uah"] or REFERRAL_BONUS_UAH)
    # строк 30 днів — від завершеної реєстрації, не від першого /start
    registered_at = kyiv_now_str()
    click_at = fresh.get("referral_click_at")
    rdb.create_referral(
        friend_user_id=int(new_user_id),
        referrer_user_id=int(referred_by),
        click_at=click_at,
        registered_at=registered_at,
        terms=terms,
        amount_uah=amount,
    )
    return True


def _terms_of(ref: dict) -> dict[str, Any]:
    terms = dict(ref.get("terms") or {})
    terms.setdefault("amount_uah", ref.get("amount_uah") or get_referral_bonus_uah())
    terms.setdefault("min_cash_uah", REFERRAL_MIN_CASH_UAH)
    terms.setdefault("purchase_window_days", REFERRAL_PURCHASE_WINDOW_DAYS)
    return terms


def _within_purchase_window(ref: dict, at: datetime) -> bool:
    start = _parse_dt(ref.get("registered_at"))
    if not start:
        return False
    days = int(_terms_of(ref).get("purchase_window_days") or REFERRAL_PURCHASE_WINDOW_DAYS)
    return start <= at < start + timedelta(days=days)


def qualify_referral_on_purchase(
    friend_user_id: int,
    *,
    payed_sum_uah: float,
    transaction_id: str,
    closed_at: datetime | None = None,
) -> dict[str, Any]:
    """
    Кваліфікує покупку друга (≥ min cash у вікні 30 днів).
    Не нараховує одразу — ставить pending_grant / owner_review.
    """
    ref = rdb.get_by_friend(friend_user_id)
    if not ref:
        # міграція зі старого referred_by без рядка referrals
        user = get_user(friend_user_id)
        if user and user.get("referred_by_user_id") and not user.get("referral_bonus_paid"):
            bind_referrer_on_registration(int(friend_user_id), int(user["referred_by_user_id"]))
            ref = rdb.get_by_friend(friend_user_id)
    if not ref:
        return {"status": "skip", "reason": "no_referral"}

    if ref["status"] in (rdb.STATUS_PAID, rdb.STATUS_PENDING_GRANT, rdb.STATUS_OWNER_REVIEW):
        return {"status": "skip", "reason": f"already_{ref['status']}"}
    if ref["status"] not in (rdb.STATUS_BOUND, rdb.STATUS_REVERSED):
        return {"status": "skip", "reason": f"status_{ref['status']}"}

    at = closed_at or now_kyiv()
    if at.tzinfo is None:
        at = at.replace(tzinfo=KYIV_TZ)

    if not _within_purchase_window(ref, at):
        rdb.update_referral(int(friend_user_id), status=rdb.STATUS_EXPIRED)
        return {"status": "skip", "reason": "window_expired"}

    terms = _terms_of(ref)
    min_cash = float(terms.get("min_cash_uah") or REFERRAL_MIN_CASH_UAH)
    if float(payed_sum_uah or 0) + 1e-9 < min_cash:
        return {"status": "skip", "reason": "below_min_cash", "min_cash": min_cash}

    day_key = at.strftime("%Y-%m-%d")
    daily = rdb.count_referrer_success_on_day(int(ref["referrer_user_id"]), day_key)
    limit = int(terms.get("daily_auto_limit") or REFERRAL_DAILY_AUTO_LIMIT)
    available = next_kyiv_midnight(at)
    amount = float(terms.get("amount_uah") or ref.get("amount_uah") or get_referral_bonus_uah())
    qualified_at = at.strftime("%Y-%m-%d %H:%M:%S")

    # 6-е і далі за день → Owner (рахуємо вже кваліфіковані сьогодні; це буде наступне)
    if daily >= limit:
        status = rdb.STATUS_OWNER_REVIEW
        available_at = None
    else:
        status = rdb.STATUS_PENDING_GRANT
        available_at = available.strftime("%Y-%m-%d %H:%M:%S")

    rdb.update_referral(
        int(friend_user_id),
        status=status,
        amount_uah=amount,
        qualifying_tx_id=str(transaction_id),
        qualifying_payed_sum_uah=float(payed_sum_uah),
        qualified_at=qualified_at,
        available_at=available_at,
        reversed_at=None,
    )
    return {
        "status": status,
        "amount_uah": amount,
        "referrer_user_id": int(ref["referrer_user_id"]),
        "available_at": available_at,
        "friend_name": (get_user(friend_user_id) or {}).get("display_name")
        or (get_user(friend_user_id) or {}).get("user_first_name")
        or "Друг",
    }


def grant_pending_referral(ref: dict) -> dict[str, Any]:
    """Фактичне нарахування після available_at (00:00 Києва)."""
    if ref.get("status") != rdb.STATUS_PENDING_GRANT:
        return {"status": "skip", "reason": "not_pending"}
    referrer = get_user(ref["referrer_user_id"])
    if not referrer or not referrer.get("poster_client_id"):
        return {"status": "error", "reason": "no_referrer_poster"}
    amount = float(ref.get("amount_uah") or 0)
    if amount <= 0:
        rdb.update_referral(int(ref["friend_user_id"]), status=rdb.STATUS_PAID, granted_at=kyiv_now_str())
        mark_referral_bonus_paid(int(ref["friend_user_id"]))
        return {"status": "ok", "amount_uah": 0}

    try:
        poster.change_client_bonus(int(referrer["poster_client_id"]), amount)
        invalidate_client(int(referrer["poster_client_id"]))
    except Exception as exc:
        log.warning("referral grant failed ref=%s: %s", ref.get("id"), exc)
        return {"status": "error", "reason": str(exc)}

    now = now_kyiv()
    valid_days = int(_terms_of(ref).get("reward_valid_days") or REFERRAL_REWARD_VALID_DAYS)
    expires = (now + timedelta(days=valid_days)).strftime("%Y-%m-%d %H:%M:%S")
    granted_at = now.strftime("%Y-%m-%d %H:%M:%S")
    rdb.update_referral(
        int(ref["friend_user_id"]),
        status=rdb.STATUS_PAID,
        granted_at=granted_at,
        expires_at=expires,
    )
    mark_referral_bonus_paid(int(ref["friend_user_id"]))
    friend = get_user(ref["friend_user_id"]) or {}
    return {
        "status": "ok",
        "amount_uah": amount,
        "referrer_user_id": int(ref["referrer_user_id"]),
        "friend_name": friend.get("display_name") or friend.get("user_first_name") or "Друг",
        "expires_at": expires,
    }


async def process_due_referral_grants(bot=None) -> dict[str, Any]:
    now_str = now_kyiv().strftime("%Y-%m-%d %H:%M:%S")
    pending = rdb.list_pending_grants(now_str)
    report = {"checked": len(pending), "granted": [], "errors": []}
    for ref in pending:
        result = grant_pending_referral(ref)
        if result.get("status") == "ok":
            report["granted"].append(result)
            if bot is not None and float(result.get("amount_uah") or 0) > 0:
                try:
                    from Content.texts import get_referral_bonus_notification
                    from keyboards.client_keyboards import get_open_card_inline

                    await bot.send_message(
                        int(result["referrer_user_id"]),
                        get_referral_bonus_notification(
                            result.get("friend_name") or "Друг",
                            float(result["amount_uah"]),
                        ),
                        parse_mode="HTML",
                        reply_markup=get_open_card_inline(),
                    )
                except Exception as exc:
                    log.info("referral grant notify failed: %s", exc)
        elif result.get("status") == "error":
            report["errors"].append(result)
    return report


def approve_owner_review(referral_id: int) -> dict[str, Any]:
    ref = rdb.get_by_id(referral_id)
    if not ref or ref.get("status") != rdb.STATUS_OWNER_REVIEW:
        return {"status": "skip", "reason": "not_in_review"}
    available = next_kyiv_midnight(now_kyiv())
    rdb.update_referral(
        int(ref["friend_user_id"]),
        status=rdb.STATUS_PENDING_GRANT,
        available_at=available.strftime("%Y-%m-%d %H:%M:%S"),
    )
    return {
        "status": "ok",
        "friend_user_id": int(ref["friend_user_id"]),
        "available_at": available.strftime("%Y-%m-%d %H:%M:%S"),
    }


def reverse_referral_for_tx(transaction_id: str, *, payed_sum_uah: float | None = None) -> list[dict]:
    """
    Якщо кваліфікуючий чек більше не відповідає (повернення / < min cash) —
    анулює 10 бонусів запрошувача (допускає від’ємний баланс).
    """
    results = []
    for ref in rdb.list_by_qualifying_tx(str(transaction_id)):
        terms = _terms_of(ref)
        min_cash = float(terms.get("min_cash_uah") or REFERRAL_MIN_CASH_UAH)
        # якщо передали актуальну суму і вона все ще ок — не чіпаємо
        if payed_sum_uah is not None and float(payed_sum_uah) + 1e-9 >= min_cash:
            results.append({"friend_user_id": ref["friend_user_id"], "status": "still_ok"})
            continue
        if ref["status"] not in (
            rdb.STATUS_PAID,
            rdb.STATUS_PENDING_GRANT,
            rdb.STATUS_OWNER_REVIEW,
        ):
            continue

        clawed = 0.0
        if ref["status"] == rdb.STATUS_PAID:
            amount = float(ref.get("amount_uah") or 0)
            referrer = get_user(ref["referrer_user_id"])
            if amount > 0 and referrer and referrer.get("poster_client_id"):
                try:
                    poster.change_client_bonus(int(referrer["poster_client_id"]), -amount)
                    invalidate_client(int(referrer["poster_client_id"]))
                    clawed = amount
                except Exception as exc:
                    log.warning("referral clawback failed friend=%s: %s", ref["friend_user_id"], exc)

        from database_functions.db import get_connection

        get_connection().execute(
            "UPDATE users SET referral_bonus_paid = 0, last_activity = ? WHERE user_id = ?",
            (kyiv_now_str(), int(ref["friend_user_id"])),
        )
        get_connection().commit()

        rdb.update_referral(
            int(ref["friend_user_id"]),
            status=rdb.STATUS_REVERSED,
            qualifying_tx_id=None,
            qualifying_payed_sum_uah=None,
            qualified_at=None,
            available_at=None,
            granted_at=None,
            expires_at=None,
            reversed_at=kyiv_now_str(),
        )
        results.append(
            {
                "friend_user_id": ref["friend_user_id"],
                "status": "reversed",
                "clawed_uah": clawed,
            }
        )
    return results


def review_transaction_for_referral(transaction_id: str) -> dict[str, Any]:
    """Перевірка чека після webhook changed (повернення тощо)."""
    tid = str(transaction_id)
    refs = rdb.list_by_qualifying_tx(tid)
    if not refs:
        return {"status": "skip", "reason": "no_referral_tx"}
    try:
        tx = poster.get_transaction(tid)
    except Exception as exc:
        return {"status": "error", "reason": str(exc)}
    if not tx or not poster.is_transaction_closed(tx):
        return {"status": "reversed", "results": reverse_referral_for_tx(tid, payed_sum_uah=None)}
    payed = poster.from_minor(tx.get("payed_sum"))
    return {"status": "checked", "results": reverse_referral_for_tx(tid, payed_sum_uah=payed)}


def expire_stale_bound() -> int:
    """Позначити bound-запрошення з простроченим вікном покупки."""
    now = now_kyiv()
    n = 0
    for ref in rdb.list_by_status(rdb.STATUS_BOUND):
        if not _within_purchase_window(ref, now):
            rdb.update_referral(int(ref["friend_user_id"]), status=rdb.STATUS_EXPIRED)
            n += 1
    return n


def referral_ui_payload(user_id: int) -> dict[str, Any]:
    can = can_share_invite(int(user_id))
    stats = rdb.referrer_stats(int(user_id))
    terms = current_terms()
    return {
        "referral_bonus_uah": float(terms["amount_uah"]),
        "referral_min_cash_uah": float(terms["min_cash_uah"]),
        "referral_link": referral_link_for(int(user_id)) if can else "",
        "referral_can_invite": can,
        "referrals_count": int(stats["paid"]),
        "referrals_registered": int(stats["registered_friends"]),
        "referrals_successful": int(stats["successful"]),
        "referrals_earned_uah": float(stats["earned_uah"]),
        "referrals_owner_review": int(stats["owner_review"]),
        "referral_hint": (
            f"+{terms['amount_uah']:g} грн після покупки друга від {terms['min_cash_uah']:g} грн грошима "
            f"(протягом {terms['purchase_window_days']} днів). "
            "Бонуси стають доступні наступного дня о 00:00 за Києвом."
            if can
            else "Посилання для запрошень відкриється після твоєї першої покупки в Kraft."
        ),
    }


# сумісність зі старим API
def process_referral_on_first_purchase(
    new_user_id: int,
    *,
    payed_sum_uah: float = 0.0,
    transaction_id: str = "",
    closed_at: datetime | None = None,
) -> tuple[float, int | None, str]:
    """
    Сумісність: більше НЕ нараховує одразу.
    Повертає (0, referrer, name) якщо лише кваліфіковано; виплата — у cron.
    """
    result = qualify_referral_on_purchase(
        int(new_user_id),
        payed_sum_uah=payed_sum_uah,
        transaction_id=transaction_id or "",
        closed_at=closed_at,
    )
    if result.get("status") in (rdb.STATUS_PENDING_GRANT, rdb.STATUS_OWNER_REVIEW):
        return 0.0, result.get("referrer_user_id"), result.get("friend_name") or ""
    return 0.0, None, ""
