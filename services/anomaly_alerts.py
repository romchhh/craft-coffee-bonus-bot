"""Scan anomalies and notify owner via Telegram (deduped)."""
from __future__ import annotations

import json
import logging

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from database_functions import anomaly_alerts_db as adb
from database_functions.anomalies_db import (
    enrich_with_users,
    frequent_cashback,
    high_cashback_week,
    micro_checks,
    referral_friends_today,
    user_name_link,
)
from utils.kyiv_time import now_kyiv

log = logging.getLogger(__name__)

# Unique friends registered via referral link per Kyiv calendar day
REFERRAL_FRIENDS_DAY_ALERT = 11


def _owner_ids() -> list[int]:
    ids: set[int] = set()
    try:
        from config import administrators

        for x in administrators or []:
            ids.add(int(x))
    except Exception:
        pass
    try:
        from database_functions.admin_db import get_all_admin_ids

        for x in get_all_admin_ids() or []:
            ids.add(int(x))
    except Exception:
        pass
    return sorted(ids)


def _client_card_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👤 Картка в адмінці",
                    callback_data=f"client_view:{int(user_id)}",
                )
            ]
        ]
    )


async def notify_anomaly(
    bot,
    *,
    anomaly_key: str,
    anomaly_type: str,
    user_id,
    summary: str,
    metrics: dict,
) -> bool:
    if not adb.record_alert(
        anomaly_key=anomaly_key,
        anomaly_type=anomaly_type,
        user_id=int(user_id) if user_id is not None else None,
        summary=summary,
        metrics_json=json.dumps(metrics, ensure_ascii=False),
    ):
        return False
    text = (
        "⚠️ <b>Аномалія лояльності</b>\n\n"
        f"Тип: <b>{anomaly_type}</b>\n"
        f"Час: <code>{now_kyiv().strftime('%d.%m.%Y %H:%M')}</code> (Київ)\n"
        f"{summary}\n\n"
        "<i>Деталі — в адмінці «👤 Клієнти» → аномалії.</i>"
    )
    kb = None
    try:
        if user_id is not None:
            kb = _client_card_keyboard(int(user_id))
    except (TypeError, ValueError):
        kb = None
    for aid in _owner_ids():
        try:
            await bot.send_message(aid, text, parse_mode="HTML", reply_markup=kb)
        except Exception as exc:
            log.info("anomaly notify failed admin=%s: %s", aid, exc)
    return True


async def scan_and_notify(bot) -> dict:
    report = {"notified": 0}
    day = now_kyiv().strftime("%Y-%m-%d")

    for r in enrich_with_users(referral_friends_today(min_count=REFERRAL_FRIENDS_DAY_ALERT)):
        uid = r["user_id"]
        key = f"ref_friends_day:{day}:{uid}"
        name = user_name_link(uid, r.get("name"))
        ok = await notify_anomaly(
            bot,
            anomaly_key=key,
            anomaly_type="Реферали: ≥11 друзів за день",
            user_id=uid,
            summary=(
                f"Клієнт {name} (<code>{uid}</code>) "
                f"додав <b>{r['cnt']}</b> унікальних друзів сьогодні "
                f"(підтверджена реєстрація за реф. посиланням)."
            ),
            metrics={"cnt": r["cnt"], "day": day},
        )
        if ok:
            report["notified"] += 1

    for r in enrich_with_users(frequent_cashback(hours=24, min_count=4)):
        uid = r["user_id"]
        key = f"freq_cashback:{day}:{uid}"
        name = user_name_link(uid, r.get("name"))
        ok = await notify_anomaly(
            bot,
            anomaly_key=key,
            anomaly_type="Часті нарахування кешбеку (24 год)",
            user_id=uid,
            summary=(
                f"{name} (<code>{uid}</code>): "
                f"{r['cnt']}× · +{r['total_bonus']:g}"
            ),
            metrics=dict(r),
        )
        if ok:
            report["notified"] += 1

    for r in enrich_with_users(high_cashback_week(min_uah=80)):
        uid = r["user_id"]
        week = now_kyiv().strftime("%Y-W%W")
        key = f"high_cashback_week:{week}:{uid}"
        name = user_name_link(uid, r.get("name"))
        ok = await notify_anomaly(
            bot,
            anomaly_key=key,
            anomaly_type="Багато кешбеку за тиждень",
            user_id=uid,
            summary=(
                f"{name} (<code>{uid}</code>): +{r['total_bonus']:g} "
                f"({r['cnt']} чеків)"
            ),
            metrics=dict(r),
        )
        if ok:
            report["notified"] += 1

    for r in enrich_with_users(micro_checks(hours=24, max_payed=55, min_count=5)):
        uid = r["user_id"]
        key = f"micro_checks:{day}:{uid}"
        name = user_name_link(uid, r.get("name"))
        ok = await notify_anomaly(
            bot,
            anomaly_key=key,
            anomaly_type="Часті малі чеки",
            user_id=uid,
            summary=(
                f"{name} (<code>{uid}</code>): {r['cnt']}× ≤55 грн"
            ),
            metrics=dict(r),
        )
        if ok:
            report["notified"] += 1

    return report
