"""Обробка закритих чеків Poster: нарахування кешбеку + повідомлення в Telegram."""
from __future__ import annotations

import logging
import math
from typing import Any

from database_functions.client_db import get_user_by_poster_client_id
from database_functions.settings_db import (
    is_transaction_processed,
    mark_transaction_processed,
)
from services import poster
from services.charge_loyalty import (
    get_cashback_percent_for_user,
    on_purchase_closed,
    parse_purchase_datetime,
)

log = logging.getLogger(__name__)


def _round_bonus(amount: float) -> float:
    """Округлення до копійки вниз (як у правилах лояльності)."""
    return math.floor(amount * 100) / 100


async def process_closed_transaction(transaction_id: str | int, bot=None) -> dict[str, Any]:
    """
    Якщо чек закритий і прив’язаний до клієнта з бота —
    нараховує % кешбеку від оплати грошима і шле подяку в Telegram.
    """
    tid = str(transaction_id)
    if is_transaction_processed(tid):
        return {"status": "skip", "reason": "already_processed"}

    try:
        tx = poster.get_transaction(tid)
    except Exception as exc:
        log.exception("get_transaction %s", tid)
        return {"status": "error", "reason": str(exc)}

    if not tx:
        return {"status": "skip", "reason": "not_found"}

    status = str(tx.get("status") or "")
    if not poster.is_transaction_closed(tx):
        return {"status": "skip", "reason": f"status_{status}"}

    client_id_raw = tx.get("client_id") or 0
    try:
        client_id = int(client_id_raw)
    except (TypeError, ValueError):
        client_id = 0
    if client_id <= 0:
        return {"status": "skip", "reason": "no_client"}

    user = get_user_by_poster_client_id(client_id)
    if not user:
        # Чек з клієнтом Poster, але не з нашого бота — ігноруємо
        mark_transaction_processed(
            tid,
            poster_client_id=client_id,
            telegram_user_id=None,
            payed_sum_uah=poster.from_minor(tx.get("payed_sum")),
            bonus_uah=0,
            bonus_spent_uah=poster.from_minor(tx.get("payed_bonus") or 0),
        )
        return {"status": "skip", "reason": "client_not_in_bot"}

    payed_sum_uah = poster.from_minor(tx.get("payed_sum"))  # готівка + карта
    bonus_spent_uah = poster.from_minor(tx.get("payed_bonus") or 0)
    percent = get_cashback_percent_for_user(int(user["user_id"]))
    bonus_uah = _round_bonus(payed_sum_uah * percent / 100.0)

    closed_raw = tx.get("date_close_date") or tx.get("date_close") or ""
    closed_at = None
    if closed_raw:
        closed_at = parse_purchase_datetime(str(closed_raw))

    # Позначити одразу, щоб не задвоїти при повторному webhook
    mark_transaction_processed(
        tid,
        poster_client_id=client_id,
        telegram_user_id=int(user["user_id"]),
        payed_sum_uah=payed_sum_uah,
        bonus_uah=bonus_uah,
        bonus_spent_uah=bonus_spent_uah,
    )

    try:
        on_purchase_closed(int(user["user_id"]), payed_sum_uah, closed_at)
    except Exception as exc:
        log.warning("charge credit failed user=%s: %s", user["user_id"], exc)

    quest_events: list[dict] = []
    try:
        from services.quests import on_purchase_for_quests

        quest_events = on_purchase_for_quests(int(user["user_id"]), tx, closed_at=closed_at)
    except Exception as exc:
        log.warning("quests update failed user=%s: %s", user["user_id"], exc)

    try:
        from services.referrals import qualify_referral_on_purchase

        ref_result = qualify_referral_on_purchase(
            int(user["user_id"]),
            payed_sum_uah=payed_sum_uah,
            transaction_id=tid,
            closed_at=closed_at,
        )
        if ref_result.get("status") == "owner_review" and bot is not None:
            try:
                await bot.send_message(
                    int(ref_result["referrer_user_id"]),
                    "⏳ <b>Винагорода на перевірці</b>\n\n"
                    f"Запрошення друга <b>{ref_result.get('friend_name') or 'Друг'}</b> "
                    "отримано. Нарахування після перевірки Owner.",
                    parse_mode="HTML",
                )
            except Exception as exc:
                log.info("referral review notify failed: %s", exc)
        # фактичне +повідомлення — наступного дня о 00:00 (cron)
    except Exception as exc:
        log.warning("referral on purchase failed user=%s: %s", user["user_id"], exc)

    balance_uah = None
    if bonus_uah > 0:
        try:
            poster.change_client_bonus(client_id, bonus_uah)
            try:
                from services.poster_client_cache import invalidate_client

                invalidate_client(client_id)
            except Exception:
                pass
            balance_uah = poster.get_client_bonus_uah(client_id)
        except Exception as exc:
            log.exception("change_client_bonus client=%s tx=%s", client_id, tid)
            return {"status": "error", "reason": f"bonus_failed: {exc}"}
    elif quest_events:
        try:
            balance_uah = poster.get_client_bonus_uah(client_id)
        except Exception:
            pass

    if bot is not None:
        try:
            await _send_thanks(
                bot,
                telegram_id=int(user["user_id"]),
                name=user.get("display_name") or user.get("user_first_name") or "",
                payed_sum_uah=payed_sum_uah,
                bonus_uah=bonus_uah,
                percent=percent,
                balance_uah=balance_uah,
            )
        except Exception as exc:
            log.warning("telegram notify failed user=%s: %s", user["user_id"], exc)
        for ev in quest_events:
            if not ev.get("completed"):
                continue
            reward = float(ev.get("reward_uah") or 0)
            title = ev.get("title") or "Квест"
            if ev.get("symbolic") and reward <= 0:
                text = f"🏅 <b>{title}</b>\n\nВідзнаку додано в розділ «Квести»."
            elif reward > 0:
                text = (
                    f"🎯 <b>{title}</b>\n\n"
                    f"Нараховано <b>+{reward:g} грн</b> бонусів."
                )
            else:
                continue
            try:
                from keyboards.client_keyboards import get_open_card_inline

                await bot.send_message(
                    int(user["user_id"]),
                    text,
                    parse_mode="HTML",
                    reply_markup=get_open_card_inline(),
                )
            except Exception as exc:
                log.info("quest notify failed: %s", exc)

    return {
        "status": "ok",
        "transaction_id": tid,
        "client_id": client_id,
        "telegram_user_id": int(user["user_id"]),
        "payed_sum_uah": payed_sum_uah,
        "bonus_uah": bonus_uah,
        "balance_uah": balance_uah,
        "quest_events": quest_events,
    }


async def _send_thanks(
    bot,
    *,
    telegram_id: int,
    name: str,
    payed_sum_uah: float,
    bonus_uah: float,
    percent: float,
    balance_uah: float | None,
) -> None:
    from keyboards.client_keyboards import get_open_card_inline

    who = f", {name}" if name else ""
    inline = get_open_card_inline()
    mini_line = (
        "\n\nВідкрий <b>цифрову картку</b> в мініапі — баланс і штрихкод завжди під рукою 👇"
        if inline
        else ""
    )
    if bonus_uah > 0:
        balance_line = ""
        if balance_uah is not None:
            balance_line = f"\nЗагальний баланс: <b>{balance_uah:g} грн</b> бонусів."
        text = (
            f"☕ Дякуємо за замовлення{who}!\n\n"
            f"Сума покупки: <b>{payed_sum_uah:g} грн</b>\n"
            f"Нараховано кешбек {percent:g}%: <b>+{bonus_uah:g} грн</b> бонусів."
            f"{balance_line}"
            f"{mini_line}\n\n"
            "Гарного дня від Craft Coffee 🤎"
        )
    else:
        text = (
            f"☕ Дякуємо за замовлення{who}!\n\n"
            f"Сума покупки: <b>{payed_sum_uah:g} грн</b>\n"
            "Чекаємо знову в Craft Coffee!"
            f"{mini_line}"
        )
    await bot.send_message(
        telegram_id,
        text,
        parse_mode="HTML",
        reply_markup=inline,
    )
