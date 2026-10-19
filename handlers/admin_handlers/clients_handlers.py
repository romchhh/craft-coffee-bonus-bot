"""Admin: client cards, purchase history, block Крафтики, gift top-ups."""
from __future__ import annotations

import logging

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

from keyboards.admin_keyboards import (
    admin_keyboard,
    get_client_card_keyboard,
    get_client_search_results_keyboard,
    get_clients_hub_keyboard,
)
from states.admin_states import ClientAdmin
from utils.filters import IsAdmin

log = logging.getLogger(__name__)
router = Router()


def _esc(s: object) -> str:
    return (
        str(s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _uah(n: float) -> str:
    v = float(n or 0)
    if abs(v - round(v)) < 1e-9:
        return f"{int(round(v))}"
    return f"{v:.2f}".rstrip("0").rstrip(".")


async def _build_client_card(user: dict) -> tuple[str, types.InlineKeyboardMarkup]:
    from database_functions.charge_db import get_loyalty_row
    from services import poster
    from services.charge_loyalty import get_cashback_percent_for_user

    uid = int(user["user_id"])
    name = (
        user.get("display_name")
        or " ".join(
            x for x in [user.get("user_first_name"), user.get("user_last_name")] if x
        )
        or "—"
    )
    username = (user.get("user_name") or "").strip()
    phone = (user.get("user_phone") or "—").strip() or "—"
    card = (user.get("card_number") or "—").strip() or "—"
    poster_id = user.get("poster_client_id")
    blocked = bool(int(user.get("bonuses_blocked") or 0))
    join = (user.get("join_date") or "—")[:16]
    activity = (user.get("last_activity") or "—")[:16]

    balance = None
    if poster_id:
        try:
            balance = poster.get_client_bonus_uah(poster_id)
        except Exception as exc:
            log.warning("admin client balance user=%s: %s", uid, exc)

    try:
        pct = get_cashback_percent_for_user(uid)
        row = get_loyalty_row(uid) or {}
        charge_n = float(row.get("charge_points") or 0)
    except Exception:
        pct = 1.0
        charge_n = 0.0

    bal_line = (
        f"Баланс Крафтиків: <b>{_uah(balance)}</b>"
        if balance is not None
        else "Баланс Крафтиків: <i>не вдалося зчитати з Poster</i>"
    )
    block_line = (
        "🚫 <b>Крафтики ЗАБЛОКОВАНО</b> (кешбек і автонарахування вимкнені)"
        if blocked
        else "✅ Крафтики активні"
    )
    uname = f"@{_esc(username)}" if username else "—"

    text = (
        f"👤 <b>{_esc(name)}</b>\n\n"
        f"Telegram ID: <code>{uid}</code>\n"
        f"Username: {uname}\n"
        f"Телефон: <code>{_esc(phone)}</code>\n"
        f"Картка: <code>{_esc(card)}</code>\n"
        f"Poster client_id: <code>{_esc(poster_id or '—')}</code>\n\n"
        f"{bal_line}\n"
        f"Кешбек зараз: <b>{pct:g}%</b> · Заряд: <b>{_uah(charge_n)}</b>\n"
        f"{block_line}\n\n"
        f"Реєстрація: {_esc(join)}\n"
        f"Активність: {_esc(activity)}"
    )
    return text, get_client_card_keyboard(uid, blocked=blocked)


@router.message(IsAdmin(), F.text == "👤 Клієнти")
async def clients_hub(message: types.Message, state: FSMContext):
    from database_functions.client_db import count_bonuses_blocked
    from database_functions.loyalty_stats_db import get_loyalty_statistics_summary

    await state.clear()
    loyalty = get_loyalty_statistics_summary()
    blocked = count_bonuses_blocked()
    await message.answer(
        "👤 <b>Клієнти</b>\n\n"
        f"У програмі: <b>{loyalty['registered_clients']}</b>\n"
        f"З блокуванням Крафтиків: <b>{blocked}</b>\n\n"
        "Пошук за телефоном, Telegram ID, номером картки, @username або імʼям.",
        parse_mode="HTML",
        reply_markup=get_clients_hub_keyboard(),
    )


@router.callback_query(IsAdmin(), F.data == "clients_hub")
async def clients_hub_cb(callback: types.CallbackQuery, state: FSMContext):
    from database_functions.client_db import count_bonuses_blocked
    from database_functions.loyalty_stats_db import get_loyalty_statistics_summary

    await state.clear()
    loyalty = get_loyalty_statistics_summary()
    blocked = count_bonuses_blocked()
    await callback.message.edit_text(
        "👤 <b>Клієнти</b>\n\n"
        f"У програмі: <b>{loyalty['registered_clients']}</b>\n"
        f"З блокуванням Крафтиків: <b>{blocked}</b>\n\n"
        "Пошук за телефоном, Telegram ID, номером картки, @username або імʼям.",
        parse_mode="HTML",
        reply_markup=get_clients_hub_keyboard(),
    )
    await callback.answer()


@router.callback_query(IsAdmin(), F.data == "clients_search")
async def clients_search_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(ClientAdmin.search)
    await callback.message.answer(
        "🔎 Введи запит: <b>телефон</b>, <b>Telegram ID</b>, "
        "<b>номер картки</b>, <b>@username</b> або <b>імʼя</b>.\n"
        "Або «Скасувати».",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(IsAdmin(), ClientAdmin.search, F.text)
async def clients_search_query(message: types.Message, state: FSMContext):
    from database_functions.client_db import search_clients

    raw = (message.text or "").strip()
    if raw.lower() in {"скасувати", "cancel", "/cancel"}:
        await state.clear()
        await message.answer("Скасовано.", reply_markup=admin_keyboard())
        return

    found = search_clients(raw)
    await state.clear()
    if not found:
        await message.answer(
            "Нікого не знайдено. Спробуй інший запит у меню «👤 Клієнти».",
            reply_markup=get_clients_hub_keyboard(),
        )
        return
    if len(found) == 1:
        text, kb = await _build_client_card(found[0])
        await message.answer(text, parse_mode="HTML", reply_markup=kb)
        return
    await message.answer(
        f"Знайдено <b>{len(found)}</b> (показую до 12):",
        parse_mode="HTML",
        reply_markup=get_client_search_results_keyboard(found),
    )


@router.callback_query(IsAdmin(), F.data == "clients_recent")
async def clients_recent(callback: types.CallbackQuery, state: FSMContext):
    from database_functions.client_db import list_recent_registered

    await state.clear()
    rows = list_recent_registered(12)
    if not rows:
        await callback.answer("Немає зареєстрованих", show_alert=True)
        return
    await callback.message.edit_text(
        "🆕 <b>Останні зареєстровані</b>",
        parse_mode="HTML",
        reply_markup=get_client_search_results_keyboard(rows),
    )
    await callback.answer()


@router.callback_query(IsAdmin(), F.data == "clients_anomalies")
async def clients_anomalies(callback: types.CallbackQuery, state: FSMContext):
    import asyncio

    from database_functions.anomalies_db import build_anomalies_report

    await state.clear()
    await callback.answer("Аналізую…")
    text = await asyncio.to_thread(build_anomalies_report)
    try:
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=get_clients_hub_keyboard(),
        )
    except Exception:
        await callback.message.answer(
            text,
            parse_mode="HTML",
            reply_markup=get_clients_hub_keyboard(),
        )


@router.callback_query(IsAdmin(), F.data == "clients_blocked")
async def clients_blocked_list(callback: types.CallbackQuery, state: FSMContext):
    from database_functions.db import get_connection

    await state.clear()
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT * FROM users
        WHERE registered = 1 AND COALESCE(bonuses_blocked, 0) = 1
        ORDER BY COALESCE(last_activity, '') DESC
        LIMIT 20
        """
    ).fetchall()
    users = [dict(r) for r in rows]
    if not users:
        await callback.answer("Немає заблокованих", show_alert=True)
        return
    await callback.message.edit_text(
        f"🚫 <b>Заблоковані Крафтики</b> · {len(users)}",
        parse_mode="HTML",
        reply_markup=get_client_search_results_keyboard(users),
    )
    await callback.answer()


@router.callback_query(IsAdmin(), F.data.startswith("client_view:"))
async def client_view(callback: types.CallbackQuery, state: FSMContext):
    from database_functions.client_db import get_user

    await state.clear()
    uid = int((callback.data or "").split(":", 1)[-1])
    user = get_user(uid)
    if not user or not user.get("registered"):
        await callback.answer("Клієнта не знайдено", show_alert=True)
        return
    text, kb = await _build_client_card(user)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()


@router.callback_query(IsAdmin(), F.data.startswith("client_hist:"))
async def client_history(callback: types.CallbackQuery):
    from database_functions.client_db import get_user
    from database_functions.settings_db import list_bonus_accruals_for_user
    from services import poster

    uid = int((callback.data or "").split(":", 1)[-1])
    user = get_user(uid)
    if not user or not user.get("poster_client_id"):
        await callback.answer("Немає Poster-клієнта", show_alert=True)
        return

    await callback.answer("Завантажую історію…")
    client_id = user["poster_client_id"]
    name = user.get("display_name") or user.get("user_first_name") or str(uid)

    accruals: dict[str, float] = {}
    try:
        for acc in list_bonus_accruals_for_user(uid):
            tid = str(acc.get("transaction_id") or "")
            if tid:
                accruals[tid] = float(acc.get("bonus_uah") or 0)
    except Exception:
        pass

    lines = [f"📜 <b>Історія · {_esc(name)}</b>\n<code>{uid}</code>\n"]
    try:
        txs = poster.get_transactions_for_client(client_id, days=90)
        spots = {int(s["spot_id"]): s.get("spot_name") or "" for s in poster.get_spots()}
        txs = sorted(txs, key=lambda x: x.get("date_close_date") or "", reverse=True)[:25]
        if not txs:
            lines.append("<i>Чеків за ~90 днів не знайдено.</i>")
        for t in txs:
            tid = str(t.get("transaction_id") or poster.transaction_id_from_row(t) or "")
            date = (t.get("date_close_date") or "—")[:16]
            payed = poster.from_minor(t.get("payed_sum"))
            spent = poster.from_minor(t.get("payed_bonus") or 0)
            spot = spots.get(int(t.get("spot_id") or 0), "")
            cashback = accruals.get(tid, 0.0)
            extra = []
            if cashback > 0:
                extra.append(f"+{_uah(cashback)} кешбек")
            if spent > 0:
                extra.append(f"−{_uah(spent)} списано")
            tail = f" · {', '.join(extra)}" if extra else ""
            spot_s = f" · {_esc(spot)}" if spot else ""
            lines.append(
                f"• {_esc(date)}{spot_s}: <b>{_uah(payed)}</b> грн{tail}"
            )
    except Exception as exc:
        log.warning("admin history user=%s: %s", uid, exc)
        lines.append(f"<i>Помилка Poster: {_esc(exc)}</i>")

    text = "\n".join(lines)
    if len(text) > 3900:
        text = text[:3900] + "\n…"

    await callback.message.answer(
        text,
        parse_mode="HTML",
        reply_markup=get_client_card_keyboard(
            uid, blocked=bool(int(user.get("bonuses_blocked") or 0))
        ),
    )


@router.callback_query(IsAdmin(), F.data.startswith("client_block:"))
async def client_block(callback: types.CallbackQuery):
    from database_functions.client_db import get_user, set_bonuses_blocked

    uid = int((callback.data or "").split(":", 1)[-1])
    user = get_user(uid)
    if not user:
        await callback.answer("Не знайдено", show_alert=True)
        return
    set_bonuses_blocked(uid, True)
    user = get_user(uid) or user
    text, kb = await _build_client_card(user)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer("Крафтики заблоковано")


@router.callback_query(IsAdmin(), F.data.startswith("client_unblock:"))
async def client_unblock(callback: types.CallbackQuery):
    from database_functions.client_db import get_user, set_bonuses_blocked

    uid = int((callback.data or "").split(":", 1)[-1])
    user = get_user(uid)
    if not user:
        await callback.answer("Не знайдено", show_alert=True)
        return
    set_bonuses_blocked(uid, False)
    user = get_user(uid) or user
    text, kb = await _build_client_card(user)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer("Крафтики розблоковано")


@router.callback_query(IsAdmin(), F.data.startswith("client_gift:"))
async def client_gift_start(callback: types.CallbackQuery, state: FSMContext):
    from database_functions.client_db import get_user

    uid = int((callback.data or "").split(":", 1)[-1])
    user = get_user(uid)
    if not user or not user.get("poster_client_id"):
        await callback.answer("Немає Poster-клієнта", show_alert=True)
        return
    await state.set_state(ClientAdmin.gift_amount)
    await state.update_data(gift_user_id=uid)
    await callback.message.answer(
        f"🎁 Скільки Крафтиків подарувати клієнту <code>{uid}</code>?\n"
        "Введи число (наприклад <code>20</code> або <code>15.5</code>).\n"
        "Або «Скасувати».",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(IsAdmin(), ClientAdmin.gift_amount, F.text)
async def client_gift_amount(message: types.Message, state: FSMContext):
    from database_functions.client_db import get_user
    from services import poster
    from services.poster_client_cache import invalidate_client

    raw = (message.text or "").strip().replace(",", ".")
    if raw.lower() in {"скасувати", "cancel", "/cancel"}:
        await state.clear()
        await message.answer("Скасовано.", reply_markup=admin_keyboard())
        return

    data = await state.get_data()
    uid = int(data.get("gift_user_id") or 0)
    user = get_user(uid)
    if not user or not user.get("poster_client_id"):
        await state.clear()
        await message.answer("Клієнта не знайдено.", reply_markup=admin_keyboard())
        return

    try:
        amount = float(raw)
    except ValueError:
        await message.answer("Некоректне число. Приклад: <code>20</code>", parse_mode="HTML")
        return
    if amount <= 0 or amount > 5000:
        await message.answer("Сума має бути від 0.01 до 5000.")
        return

    cid = int(user["poster_client_id"])
    try:
        poster.change_client_bonus(cid, amount)
        invalidate_client(cid)
        new_bal = poster.get_client_bonus_uah(cid)
    except Exception as exc:
        log.exception("admin gift user=%s", uid)
        await message.answer(f"Не вдалося нарахувати в Poster: {_esc(exc)}")
        return

    await state.clear()
    name = user.get("display_name") or user.get("user_first_name") or str(uid)
    await message.answer(
        f"✅ Нараховано <b>+{_uah(amount)}</b> Крафтиків клієнту <b>{_esc(name)}</b> "
        f"(<code>{uid}</code>).\n"
        f"Новий баланс: <b>{_uah(new_bal)}</b>",
        parse_mode="HTML",
        reply_markup=admin_keyboard(),
    )
    text, kb = await _build_client_card(get_user(uid) or user)
    await message.answer(text, parse_mode="HTML", reply_markup=kb)

    # Optional client notify
    try:
        from main import bot

        await bot.send_message(
            uid,
            f"🎁 <b>+{_uah(amount)} Крафтиків</b> від Крафт Кава.\n"
            "Дякуємо, що з нами ☕",
            parse_mode="HTML",
        )
    except Exception as exc:
        log.info("gift notify failed user=%s: %s", uid, exc)
