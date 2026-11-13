"""Admin: client cards, purchase history, block Крафтики, gift top-ups."""
from __future__ import annotations

import asyncio
import logging

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

from keyboards.admin_keyboards import (
    admin_keyboard,
    get_client_card_keyboard,
    get_client_search_results_keyboard,
    get_clients_hub_keyboard,
    get_clients_list_keyboard,
    get_clients_sort_keyboard,
    get_clients_spot_filter_keyboard,
    get_referrals_browse_keyboard,
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

    birthday = (user.get("birthday") or "").strip()
    age_line = ""
    if birthday and birthday not in ("0000-00-00",):
        from database_functions.clients_admin_db import _age_years

        age = _age_years(birthday)
        age_line = f"ДН: {_esc(birthday[:10])}" + (f" · {age} р." if age is not None else "")
        age_line = age_line + "\n"

    ref_lines = ""
    try:
        from database_functions.clients_admin_db import (
            get_referrer_for_friend,
            list_friends_of_referrer,
        )
        from database_functions.referrals_db import referrer_stats

        brought_by = get_referrer_for_friend(uid)
        if brought_by:
            rname = (
                brought_by.get("display_name")
                or brought_by.get("user_first_name")
                or brought_by.get("referrer_user_id")
            )
            ref_lines += (
                f"Привів: <b>{_esc(rname)}</b> "
                f"(<code>{brought_by.get('referrer_user_id')}</code>) · "
                f"{_esc(brought_by.get('status') or '')}\n"
            )
        stats = referrer_stats(uid)
        friends = list_friends_of_referrer(uid, limit=5)
        if stats.get("registered_friends"):
            ref_lines += (
                f"Запросив друзів: <b>{stats['registered_friends']}</b> "
                f"(успішних {stats['successful']}, виплачено {stats['paid']})\n"
            )
            for fr in friends[:3]:
                fname = fr.get("display_name") or fr.get("user_first_name") or fr.get("friend_user_id")
                ref_lines += f"  · {_esc(fname)} · {_esc(fr.get('status') or '')}\n"
    except Exception as exc:
        log.debug("client card referrals: %s", exc)

    text = (
        f"👤 <b>{_esc(name)}</b>\n\n"
        f"Telegram ID: <code>{uid}</code>\n"
        f"Username: {uname}\n"
        f"Телефон: <code>{_esc(phone)}</code>\n"
        f"Картка: <code>{_esc(card)}</code>\n"
        f"Poster client_id: <code>{_esc(poster_id or '—')}</code>\n"
        f"{age_line}"
        f"\n{bal_line}\n"
        f"Кешбек зараз: <b>{pct:g}%</b> · Заряд: <b>{_uah(charge_n)}</b>\n"
        f"{block_line}\n\n"
        f"Реєстрація: {_esc(join)}\n"
        f"Активність: {_esc(activity)}"
    )
    if ref_lines:
        text += f"\n\n👥 <b>Реферали</b>\n{ref_lines.strip()}"
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
        "📋 Усі клієнти · 📊 Excel · сортування · хто кого привів · пошук.",
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
        "📋 Усі клієнти · 📊 Excel · сортування · хто кого привів · пошук.",
        parse_mode="HTML",
        reply_markup=get_clients_hub_keyboard(),
    )
    await callback.answer()


@router.callback_query(IsAdmin(), F.data == "clients_export_xlsx")
async def clients_export_xlsx(callback: types.CallbackQuery):
    import os
    from datetime import datetime

    from aiogram.types import FSInputFile

    from utils.admin_functions import generate_clients_export

    await callback.answer()
    await callback.message.answer(
        "📊 Формую Excel з клієнтами та статистикою…\n"
        "<i>Для великої бази це може зайняти хвилину.</i>",
        parse_mode="HTML",
    )

    try:
        filename, count = await asyncio.to_thread(generate_clients_export)
    except Exception as exc:
        log.exception("clients excel export")
        await callback.message.answer(f"Не вдалося сформувати Excel: {_esc(exc)}")
        return

    try:
        await callback.message.answer_document(
            FSInputFile(filename),
            caption=(
                f"📊 <b>Клієнти зі статистикою</b>\n"
                f"Записів: <b>{count}</b>\n"
                f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
                "<i>Витрати / Крафтики / кавʼярні — за чеками в боті. "
                "У файлі увімкнено фільтри Excel.</i>"
            ),
            parse_mode="HTML",
        )
    finally:
        if os.path.exists(filename):
            try:
                os.remove(filename)
            except OSError:
                pass


async def _render_clients_list(
    callback: types.CallbackQuery,
    state: FSMContext,
    *,
    sort: str,
    offset: int,
) -> None:
    from database_functions.clients_admin_db import (
        PAGE_SIZE,
        SORT_LABELS,
        list_clients_sorted,
    )

    data = await state.get_data()
    spot = data.get("clients_filter_spot") or None
    product = data.get("clients_filter_product") or None
    rows, total = list_clients_sorted(
        sort, offset=offset, limit=PAGE_SIZE, spot_name=spot, product_q=product
    )
    label = SORT_LABELS.get(sort, sort)
    filters = []
    if spot:
        filters.append(f"кавʼярня: {_esc(spot)}")
    if product:
        filters.append(f"продукт: {_esc(product)}")
    filt_s = ("\nФільтр: " + ", ".join(filters)) if filters else ""
    page = (offset // PAGE_SIZE) + 1
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    text = (
        f"📋 <b>Клієнти</b> · {label}\n"
        f"Всього: <b>{total}</b> · стор. {page}/{pages}"
        f"{filt_s}\n\n"
        "<i>₴ — сума чеків у боті · +К — нараховані Крафтики · р — вік</i>"
    )
    if not rows:
        text += "\n\nНікого не знайдено за цими умовами."
    kb = get_clients_list_keyboard(
        rows, sort=sort, offset=offset, total=total, page_size=PAGE_SIZE
    )
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(IsAdmin(), F.data.startswith("clients_list:"))
async def clients_list(callback: types.CallbackQuery, state: FSMContext):
    parts = (callback.data or "").split(":")
    # clients_list:sort:offset
    sort = parts[1] if len(parts) > 1 else "join_desc"
    try:
        offset = int(parts[2]) if len(parts) > 2 else 0
    except ValueError:
        offset = 0
    await _render_clients_list(callback, state, sort=sort, offset=offset)
    await callback.answer()


@router.callback_query(IsAdmin(), F.data == "clients_sort_menu")
async def clients_sort_menu(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "↕️ <b>Сортування та фільтри</b>\n\n"
        "Витрати й Крафтики — за чеками, що вже пройшли через бота.\n"
        "Вік — з дати народження в профілі.\n"
        "Кавʼярня / продукт — хто купував у цій точці або цей товар.",
        parse_mode="HTML",
        reply_markup=get_clients_sort_keyboard(),
    )
    await callback.answer()


@router.callback_query(IsAdmin(), F.data == "clients_clear_filters")
async def clients_clear_filters(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(clients_filter_spot=None, clients_filter_product=None)
    await _render_clients_list(callback, state, sort="join_desc", offset=0)
    await callback.answer("Фільтри скинуто")


@router.callback_query(IsAdmin(), F.data == "clients_filter_spot")
async def clients_filter_spot(callback: types.CallbackQuery, state: FSMContext):
    from database_functions.clients_admin_db import list_visit_spots

    spots = list_visit_spots(limit=12)
    await state.update_data(clients_spot_choices=spots)
    if not spots:
        await callback.answer(
            "Ще немає чеків із назвою кавʼярні в боті", show_alert=True
        )
        return
    await callback.message.edit_text(
        "📍 Обери кавʼярню — покажемо клієнтів, які там купували:",
        reply_markup=get_clients_spot_filter_keyboard(spots),
    )
    await callback.answer()


@router.callback_query(IsAdmin(), F.data.startswith("clients_spot:"))
async def clients_spot_pick(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    spots = data.get("clients_spot_choices") or []
    try:
        idx = int((callback.data or "").split(":")[-1])
    except ValueError:
        await callback.answer("Помилка", show_alert=True)
        return
    if idx < 0 or idx >= len(spots):
        from database_functions.clients_admin_db import list_visit_spots

        spots = list_visit_spots(limit=12)
    if idx < 0 or idx >= len(spots):
        await callback.answer("Кавʼярню не знайдено", show_alert=True)
        return
    await state.update_data(clients_filter_spot=spots[idx], clients_filter_product=None)
    await _render_clients_list(callback, state, sort="spent_desc", offset=0)
    await callback.answer()


@router.callback_query(IsAdmin(), F.data == "clients_filter_product")
async def clients_filter_product(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(ClientAdmin.filter_product)
    await callback.message.answer(
        "☕ Введи частину назви товару (напр. <b>капучино</b>).\n"
        "Або «Скасувати».",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(IsAdmin(), ClientAdmin.filter_product, F.text)
async def clients_filter_product_query(message: types.Message, state: FSMContext):
    raw = (message.text or "").strip()
    if raw.lower() in {"скасувати", "cancel", "/cancel"}:
        await state.set_state(None)
        await message.answer("Скасовано.", reply_markup=get_clients_hub_keyboard())
        return
    await state.update_data(clients_filter_product=raw, clients_filter_spot=None)
    await state.set_state(state=None)
    from database_functions.clients_admin_db import PAGE_SIZE, list_clients_sorted

    rows, total = list_clients_sorted(
        "spent_desc", offset=0, limit=PAGE_SIZE, product_q=raw
    )
    await message.answer(
        f"☕ Фільтр продукт: <b>{_esc(raw)}</b>\n"
        f"Знайдено: <b>{total}</b>",
        parse_mode="HTML",
        reply_markup=get_clients_list_keyboard(
            rows, sort="spent_desc", offset=0, total=total, page_size=PAGE_SIZE
        ),
    )


@router.callback_query(IsAdmin(), F.data.startswith("clients_refs:"))
async def clients_refs_browse(callback: types.CallbackQuery, state: FSMContext):
    from database_functions.clients_admin_db import list_recent_referrals

    await state.clear()
    try:
        offset = int((callback.data or "").split(":")[-1])
    except ValueError:
        offset = 0
    offset = max(0, offset)
    batch = list_recent_referrals(limit=offset + 11)
    page = batch[offset : offset + 10]
    has_more = len(batch) > offset + 10
    if not page and offset == 0:
        await callback.answer("Рефералів ще немає", show_alert=True)
        return
    text = (
        "👥 <b>Хто кого привів</b>\n\n"
        "Ліва кнопка — друг (кого запросили), «← хто» — запрошувач.\n"
        "Статуси: bound / pending_grant / paid / owner_review…"
    )
    kb = get_referrals_browse_keyboard(page, offset=offset, has_more=has_more)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()


@router.callback_query(IsAdmin(), F.data.startswith("client_refs:"))
async def client_refs_detail(callback: types.CallbackQuery):
    from database_functions.client_db import get_user
    from database_functions.clients_admin_db import (
        get_referrer_for_friend,
        list_friends_of_referrer,
    )
    from database_functions.referrals_db import referrer_stats

    uid = int((callback.data or "").split(":")[-1])
    user = get_user(uid)
    if not user:
        await callback.answer("Не знайдено", show_alert=True)
        return
    name = user.get("display_name") or user.get("user_first_name") or uid
    lines = [f"👥 <b>Реферали · {_esc(name)}</b>\n<code>{uid}</code>\n"]
    brought = get_referrer_for_friend(uid)
    if brought:
        rname = brought.get("display_name") or brought.get("user_first_name") or brought.get(
            "referrer_user_id"
        )
        lines.append(
            f"Цього клієнта привів: <b>{_esc(rname)}</b> "
            f"<code>{brought.get('referrer_user_id')}</code> · {_esc(brought.get('status'))}"
        )
    else:
        lines.append("Ніхто не приводив (або реферал не зафіксований).")
    stats = referrer_stats(uid)
    lines.append(
        f"\nЗапросив: <b>{stats['registered_friends']}</b> · "
        f"успішних <b>{stats['successful']}</b> · "
        f"виплачено <b>{stats['paid']}</b> · "
        f"+{_uah(stats['earned_uah'])} Крафтиків"
    )
    friends = list_friends_of_referrer(uid, limit=20)
    if friends:
        lines.append("")
        for fr in friends:
            fname = fr.get("display_name") or fr.get("user_first_name") or fr.get("friend_user_id")
            lines.append(
                f"· {_esc(fname)} <code>{fr.get('friend_user_id')}</code> · {_esc(fr.get('status'))}"
            )
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ До картки", callback_data=f"client_view:{uid}")],
            [InlineKeyboardButton(text="📋 Усі реферали", callback_data="clients_refs:0")],
        ]
    )
    await callback.message.answer("\n".join(lines), parse_mode="HTML", reply_markup=kb)
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
    if not user:
        await callback.answer("Клієнта не знайдено", show_alert=True)
        return
    if not user.get("poster_client_id"):
        await callback.answer("Покупок ще немає", show_alert=True)
        return

    await callback.answer()
    client_id = user["poster_client_id"]
    name = user.get("display_name") or user.get("user_first_name") or str(uid)
    kb = get_client_card_keyboard(
        uid, blocked=bool(int(user.get("bonuses_blocked") or 0))
    )
    header = f"📜 <b>Історія · {_esc(name)}</b>\n<code>{uid}</code>\n"

    accruals: dict[str, float] = {}
    try:
        for acc in list_bonus_accruals_for_user(uid):
            tid = str(acc.get("transaction_id") or "")
            if tid:
                accruals[tid] = float(acc.get("bonus_uah") or 0)
    except Exception:
        pass

    def _load() -> tuple[list[dict], dict[int, str]]:
        txs = poster.get_transactions_for_client(client_id, days=90, include_products=True)
        spots = {
            int(s["spot_id"]): s.get("spot_name") or ""
            for s in poster.get_spots()
            if s.get("spot_id") is not None
        }
        return txs, spots

    try:
        txs, spots = await asyncio.wait_for(asyncio.to_thread(_load), timeout=40)
    except asyncio.TimeoutError:
        log.warning("admin history timeout user=%s", uid)
        await callback.message.answer(
            header + "\nНе вдалося завантажити історію (таймаут Poster). Спробуй ще раз.",
            parse_mode="HTML",
            reply_markup=kb,
        )
        return
    except Exception as exc:
        log.warning("admin history user=%s: %s", uid, exc)
        await callback.message.answer(
            header + f"\nПомилка Poster: {_esc(exc)}",
            parse_mode="HTML",
            reply_markup=kb,
        )
        return

    txs = sorted(txs, key=lambda x: x.get("date_close_date") or "", reverse=True)[:25]
    if not txs:
        # Fallback: local loyalty log (purchases already credited in bot)
        from database_functions.settings_db import list_purchases_for_user

        local = list_purchases_for_user(uid, limit=25)
        if not local:
            await callback.message.answer(
                header + "\nПокупок ще немає",
                parse_mode="HTML",
                reply_markup=kb,
            )
            return
        lines = [header]
        for row in local:
            date = (row.get("date_close") or row.get("processed_at") or "—")[:16]
            payed = float(row.get("payed_sum_uah") or 0)
            spot = (row.get("spot_name") or "").strip()
            cashback = float(row.get("bonus_uah") or 0)
            spent = float(row.get("bonus_spent_uah") or 0)
            extra = []
            if cashback > 0:
                extra.append(f"+{_uah(cashback)} кешбек")
            if spent > 0:
                extra.append(f"−{_uah(spent)} списано")
            tail = f" · {', '.join(extra)}" if extra else ""
            spot_s = f" · {_esc(spot)}" if spot else ""
            lines.append(f"• {_esc(date)}{spot_s}: <b>{_uah(payed)}</b> грн{tail}")
            try:
                import json as _json

                items = _json.loads(row.get("products_json") or "[]")
            except Exception:
                items = []
            for it in items[:8]:
                qty = float(it.get("count") or 1)
                qty_s = f"{qty:g}× " if qty > 1 else ""
                lines.append(f"    ◦ {_esc(qty_s)}{_esc(it.get('name') or 'Товар')}")
        text = "\n".join(lines)
        if len(text) > 3900:
            text = text[:3900] + "\n…"
        await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)
        return

    lines = [header]
    for t in txs:
        tid = str(t.get("transaction_id") or poster.transaction_id_from_row(t) or "")
        date = (t.get("date_close_date") or "—")[:16]
        payed = poster.from_minor(t.get("payed_sum"))
        spent = poster.from_minor(t.get("payed_bonus") or 0)
        try:
            spot = spots.get(int(t.get("spot_id") or 0), "")
        except (TypeError, ValueError):
            spot = ""
        cashback = accruals.get(tid, 0.0)
        extra = []
        if cashback > 0:
            extra.append(f"+{_uah(cashback)} кешбек")
        if spent > 0:
            extra.append(f"−{_uah(spent)} списано")
        tail = f" · {', '.join(extra)}" if extra else ""
        spot_s = f" · {_esc(spot)}" if spot else ""
        lines.append(f"• {_esc(date)}{spot_s}: <b>{_uah(payed)}</b> грн{tail}")
        items = poster.tx_product_lines(t)
        if not items and tid:
            try:
                items = poster.tx_product_lines(poster.get_transaction(tid) or {})
            except Exception:
                items = []
        for it in items[:8]:
            qty = float(it.get("count") or 1)
            qty_s = f"{qty:g}× " if qty > 1 else ""
            lines.append(f"    ◦ {_esc(qty_s)}{_esc(it.get('name') or 'Товар')}")

    text = "\n".join(lines)
    if len(text) > 3900:
        text = text[:3900] + "\n…"

    await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)


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
        from database_functions.client_db import touch_bonus_accrual

        touch_bonus_accrual(uid)
        new_bal = poster.get_client_bonus_uah(cid)
        try:
            from services.wallet_sync import sync_wallets_for_user

            sync_wallets_for_user(int(uid), bonus=new_bal)
        except Exception:
            pass
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
