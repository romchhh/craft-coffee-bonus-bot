"""Admin: client cards, purchase history, block Крафтики, gift top-ups."""
from __future__ import annotations

import asyncio
import logging

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

from keyboards.admin_keyboards import (
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


def _browse_nav_meta(browse: dict | None) -> tuple[str | None, bool, bool]:
    """Return (label, has_prev, has_next) for card navigation."""
    if not browse:
        return None, False, False
    ids = [int(x) for x in (browse.get("ids") or [])]
    if not ids:
        return None, False, False
    try:
        pos = int(browse.get("pos") or 0)
    except (TypeError, ValueError):
        pos = 0
    pos = max(0, min(pos, len(ids) - 1))
    mode = browse.get("mode") or ""
    offset = int(browse.get("offset") or 0)
    total = int(browse.get("total") or len(ids))
    if mode == "list":
        abs_i = offset + pos + 1
        label = f"{abs_i}/{total}"
        has_prev = pos > 0 or offset > 0
        has_next = pos < len(ids) - 1 or (offset + len(ids)) < total
    else:
        label = f"{pos + 1}/{len(ids)}"
        has_prev = pos > 0
        has_next = pos < len(ids) - 1
    return label, has_prev, has_next


def _back_label_for_browse(browse: dict | None) -> str:
    mode = (browse or {}).get("mode") or ""
    return {
        "list": "◀️ До списку",
        "search": "◀️ До пошуку",
        "recent": "◀️ До останніх",
        "blocked": "◀️ До заблокованих",
        "refs": "◀️ До рефералів",
        "anomaly": "🏠 Меню клієнтів",
    }.get(mode, "◀️ Назад")


async def _set_browse(state: FSMContext, **fields) -> dict:
    data = await state.get_data()
    browse = dict(data.get("clients_browse") or {})
    browse.update(fields)
    await state.update_data(clients_browse=browse)
    return browse


def _normalize_filter_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        s = value.strip()
        return [s] if s else []
    out: list[str] = []
    for x in value:
        s = str(x or "").strip()
        if s and s not in out:
            out.append(s)
    return out


def _filters_from_data(data: dict) -> tuple[list[str], list[str]]:
    """Active spot/product filters (supports legacy single-value keys)."""
    spots = data.get("clients_filter_spots")
    products = data.get("clients_filter_products")
    if spots is None and data.get("clients_filter_spot"):
        spots = [data.get("clients_filter_spot")]
    if products is None and data.get("clients_filter_product"):
        products = [data.get("clients_filter_product")]
    browse = data.get("clients_browse") or {}
    if spots is None and browse.get("spots"):
        spots = browse.get("spots")
    elif spots is None and browse.get("spot"):
        spots = [browse.get("spot")]
    if products is None and browse.get("products"):
        products = browse.get("products")
    elif products is None and browse.get("product"):
        products = [browse.get("product")]
    return _normalize_filter_list(spots), _normalize_filter_list(products)


async def _save_filters(
    state: FSMContext,
    *,
    spots: list[str] | None = None,
    products: list[str] | None = None,
) -> tuple[list[str], list[str]]:
    data = await state.get_data()
    cur_spots, cur_products = _filters_from_data(data)
    if spots is not None:
        cur_spots = _normalize_filter_list(spots)
    if products is not None:
        cur_products = _normalize_filter_list(products)
    await state.update_data(
        clients_filter_spots=cur_spots,
        clients_filter_products=cur_products,
        # legacy keys cleared so they don't resurrect
        clients_filter_spot=None,
        clients_filter_product=None,
    )
    return cur_spots, cur_products


def _filters_caption(spots: list[str], products: list[str]) -> str:
    bits: list[str] = []
    if spots:
        bits.append("кавʼярні: " + ", ".join(_esc(s) for s in spots))
    if products:
        bits.append("продукти: " + ", ".join(_esc(p) for p in products))
    return ("\nФільтри: " + " · ".join(bits)) if bits else ""


def _build_client_card_sync(
    user: dict,
    *,
    browse: dict | None = None,
    refresh_balance: bool = False,
) -> tuple[str, types.InlineKeyboardMarkup]:
    """Sync card builder — call via asyncio.to_thread from handlers."""
    from database_functions.charge_db import get_loyalty_row
    from database_functions.client_db import set_last_known_bonus
    from database_functions.clients_admin_db import (
        _age_years,
        get_client_admin_details,
        get_referrer_for_friend,
        list_friends_of_referrer,
    )
    from database_functions.anomalies_db import user_name_link
    from database_functions.referrals_db import referrer_stats
    from services.charge_loyalty import get_cashback_percent_for_user
    from utils.kyiv_time import format_date_ua, format_dt_ua

    uid = int(user["user_id"])
    name = (
        user.get("display_name")
        or " ".join(
            x for x in [user.get("user_first_name"), user.get("user_last_name")] if x
        )
        or "—"
    )
    username = (user.get("user_name") or "").strip()
    name_html = user_name_link(uid, name, username)
    phone = (user.get("user_phone") or "—").strip() or "—"
    card = (user.get("card_number") or "—").strip() or "—"
    poster_id = user.get("poster_client_id")

    blocked = bool(int(user.get("bonuses_blocked") or 0))
    join = format_dt_ua(user.get("registered_at") or user.get("join_date"))
    activity = format_dt_ua(user.get("last_activity"))
    mailing_off = bool(int(user.get("mailing_opt_out") or 0))

    balance = None
    balance_note = ""
    if refresh_balance and poster_id:
        try:
            from services import poster

            balance = float(poster.get_client_bonus_uah(poster_id, timeout=6.0))
            try:
                set_last_known_bonus(uid, balance)
            except Exception:
                pass
            balance_note = " · Poster зараз"
        except Exception as exc:
            log.warning("admin client balance user=%s: %s", uid, exc)
            balance_note = " · Poster недоступний"
    if balance is None and user.get("last_known_bonus") is not None:
        try:
            balance = float(user["last_known_bonus"])
            as_of = format_dt_ua(user.get("last_known_bonus_at"), empty="")
            if not refresh_balance:
                balance_note = f" · локально{(' · ' + as_of) if as_of else ''}"
            elif not balance_note:
                balance_note = " (останній відомий)"
        except (TypeError, ValueError):
            pass

    try:
        pct = get_cashback_percent_for_user(uid)
        row = get_loyalty_row(uid) or {}
        charge_n = float(row.get("charge_points") or 0)
    except Exception:
        pct = 1.0
        charge_n = 0.0

    stats = get_client_admin_details(uid)
    birthday = (user.get("birthday") or "").strip()
    age_line = "ДН: не вказано"
    if birthday and birthday not in ("0000-00-00",):
        age = _age_years(birthday)
        age_line = f"ДН: <code>{_esc(format_date_ua(birthday))}</code>" + (
            f" · <b>{age}</b> р." if age is not None else ""
        )

    bal_line = (
        f"Баланс: <b>{_uah(balance)}</b> Крафтиків{balance_note}"
        if balance is not None
        else "Баланс: <i>немає локальних даних — натисни «♻️ Баланс Poster»</i>"
    )
    block_line = (
        "🚫 <b>Крафтики ЗАБЛОКОВАНО</b>"
        if blocked
        else "✅ Крафтики активні"
    )
    u_raw = username.lstrip("@")
    if u_raw and all(ch.isalnum() or ch == "_" for ch in u_raw):
        uname = f'<a href="https://t.me/{u_raw}">@{_esc(u_raw)}</a>'
    elif username:
        uname = f"@{_esc(username)}"
    else:
        uname = "—"
    personal = user.get("personal_cashback_percent")
    personal_s = f" · перс. <b>{float(personal):g}%</b>" if personal is not None else ""

    flags = []
    if int(user.get("welcome_bonus_given") or 0):
        flags.append("вітальний ✓")
    if int(user.get("birthday_bonus_given") or 0):
        flags.append("ДН ✓")
    if mailing_off:
        flags.append("розсилка ✗")
    flags_s = ", ".join(flags) if flags else "—"

    last_buy = format_dt_ua(stats.get("last_purchase_at"))
    spots = (stats.get("spots_visited") or "").strip()
    top_spot = (stats.get("top_spot") or "").strip()

    ref_lines = ""
    try:
        brought_by = get_referrer_for_friend(uid)
        if brought_by:
            rid = brought_by.get("referrer_user_id")
            rname = (
                brought_by.get("display_name")
                or brought_by.get("user_first_name")
                or rid
            )
            rphone = (brought_by.get("user_phone") or "").strip()
            ref_lines += (
                f"Привів: {user_name_link(rid, rname, brought_by.get('user_name'))} "
                f"<code>{rid}</code>"
                + (f" · {_esc(rphone)}" if rphone else "")
                + f" · {_esc(brought_by.get('status') or '')}\n"
            )
        stats_ref = referrer_stats(uid)
        friends = list_friends_of_referrer(uid, limit=8)
        if stats_ref.get("registered_friends"):
            ref_lines += (
                f"Запросив: <b>{stats_ref['registered_friends']}</b> "
                f"(успішних {stats_ref['successful']}, "
                f"виплачено {stats_ref['paid']}, "
                f"+{_uah(stats_ref.get('earned_uah') or 0)} К)\n"
            )
            for fr in friends[:5]:
                fid = fr.get("friend_user_id")
                fname = (
                    fr.get("display_name")
                    or fr.get("user_first_name")
                    or fid
                )
                ref_lines += (
                    f"  · {user_name_link(fid, fname, fr.get('user_name'))} "
                    f"<code>{fid}</code> "
                    f"· {_esc(fr.get('status') or '')}\n"
                )
    except Exception as exc:
        log.debug("client card referrals: %s", exc)

    text = (
        f"👤 {name_html}\n"
        f"{block_line}\n\n"
        f"<b>Профіль</b>\n"
        f"Telegram ID: <code>{uid}</code>\n"
        f"Username: {uname}\n"
        f"Телефон: <code>{_esc(phone)}</code>\n"
        f"Картка: <code>{_esc(card)}</code>\n"
        f"Poster ID: <code>{_esc(poster_id or '—')}</code>\n"
        f"{age_line}\n"
        f"Реєстрація: {_esc(join)}\n"
        f"Активність: {_esc(activity)}\n"
        f"Прапорці: {_esc(flags_s)}\n\n"
        f"<b>Крафтики / кешбек</b>\n"
        f"{bal_line}\n"
        f"Кешбек зараз: <b>{pct:g}%</b>{personal_s}\n"
        f"Заряд: <b>{_uah(charge_n)}</b>\n\n"
        f"<b>Покупки (бот)</b>\n"
        f"Чеків: <b>{stats['purchases_count']}</b> · "
        f"витрачено <b>{_uah(stats['spent_uah'])}</b> грн\n"
        f"Нараховано: <b>+{_uah(stats['bonus_earned_uah'])}</b> · "
        f"списано: <b>−{_uah(stats['bonus_spent_uah'])}</b>\n"
        f"Остання покупка: {_esc(last_buy)}\n"
        f"Улюблена кавʼярня: {_esc(top_spot or '—')}\n"
        f"Кавʼярні: {_esc(spots or '—')}"
    )
    if ref_lines:
        text += f"\n\n👥 <b>Реферали</b>\n{ref_lines.strip()}"

    nav_label, has_prev, has_next = _browse_nav_meta(browse)
    kb = get_client_card_keyboard(
        uid,
        blocked=blocked,
        nav_label=nav_label,
        has_prev=has_prev,
        has_next=has_next,
        back_label=_back_label_for_browse(browse),
    )
    return text, kb


async def _build_client_card(
    user: dict,
    *,
    browse: dict | None = None,
    refresh_balance: bool = False,
) -> tuple[str, types.InlineKeyboardMarkup]:
    return await asyncio.to_thread(
        _build_client_card_sync,
        user,
        browse=browse,
        refresh_balance=refresh_balance,
    )


async def _show_client_by_id(
    callback: types.CallbackQuery,
    state: FSMContext,
    uid: int,
    *,
    answer_text: str | None = None,
    refresh_balance: bool = False,
) -> None:
    from database_functions.client_db import get_user

    data = await state.get_data()
    browse = dict(data.get("clients_browse") or {})
    ids = [int(x) for x in (browse.get("ids") or [])]
    if ids and uid in ids:
        browse["pos"] = ids.index(uid)
        await state.update_data(clients_browse=browse)
    user = get_user(uid)
    if not user or not user.get("registered"):
        await callback.answer("Клієнта не знайдено", show_alert=True)
        return
    if refresh_balance:
        await callback.answer("Опитую Poster…")
    text, kb = await _build_client_card(
        user, browse=browse, refresh_balance=refresh_balance
    )
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)
    if not refresh_balance:
        await callback.answer(answer_text)


def _hub_text_sync() -> str:
    from database_functions.client_db import count_bonuses_blocked
    from database_functions.loyalty_stats_db import get_loyalty_statistics_summary

    loyalty = get_loyalty_statistics_summary()
    blocked = count_bonuses_blocked()
    return (
        "👤 <b>Клієнти</b>\n\n"
        f"У програмі: <b>{loyalty['registered_clients']}</b>\n"
        f"З блокуванням Крафтиків: <b>{blocked}</b>\n\n"
        "Картки й списки — з локальної БД (швидко).\n"
        "Живий баланс Poster — кнопка «♻️ Баланс Poster» на картці."
    )


async def _hub_text() -> str:
    return await asyncio.to_thread(_hub_text_sync)


@router.message(IsAdmin(), F.text == "👤 Клієнти")
async def clients_hub(message: types.Message, state: FSMContext):
    await state.update_data(clients_browse=None)
    await state.set_state(None)
    await message.answer(
        await _hub_text(),
        parse_mode="HTML",
        reply_markup=get_clients_hub_keyboard(),
    )


@router.callback_query(IsAdmin(), F.data == "clients_hub")
async def clients_hub_cb(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(clients_browse=None)
    await state.set_state(None)
    try:
        await callback.message.edit_text(
            await _hub_text(),
            parse_mode="HTML",
            reply_markup=get_clients_hub_keyboard(),
        )
    except Exception:
        await callback.message.answer(
            await _hub_text(),
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
                "<i>Витрати / кавʼярні — з чеків у боті. "
                "Баланс — last known (без живого Poster). Фільтри Excel увімкнено.</i>"
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
    spots, products = _filters_from_data(data)
    rows, total = await asyncio.to_thread(
        list_clients_sorted,
        sort,
        offset=offset,
        limit=PAGE_SIZE,
        spot_names=spots,
        product_qs=products,
    )
    ids = [int(r["user_id"]) for r in rows]
    await _set_browse(
        state,
        mode="list",
        sort=sort,
        offset=offset,
        total=total,
        ids=ids,
        pos=0,
        query=None,
        spots=spots,
        products=products,
        spot=spots[0] if len(spots) == 1 else None,
        product=products[0] if len(products) == 1 else None,
    )
    label = SORT_LABELS.get(sort, sort)
    filt_s = _filters_caption(spots, products)
    page = (offset // PAGE_SIZE) + 1
    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    text = (
        f"📋 <b>Клієнти</b> · {label}\n"
        f"Всього: <b>{total}</b> · стор. {page}/{pages}"
        f"{filt_s}\n\n"
        "<i>Натисни клієнта · ⬅️➡️ між картками · Назад повертає в цей список</i>\n"
        "<i>₴ чеки · +К нараховано · р вік</i>"
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
async def clients_sort_menu(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    spots, products = _filters_from_data(data)
    active = _filters_caption(spots, products)
    extra = f"\n\n<b>Активні зараз</b>{active}" if active else (
        "\n\n<i>Можна обрати кілька кавʼярень і кілька продуктів разом "
        "(кавʼярні — «будь-яка з обраних», продукти — «усі разом»).</i>"
    )
    await callback.message.edit_text(
        "↕️ <b>Сортування та фільтри</b>\n\n"
        "Витрати й Крафтики — за чеками, що вже пройшли через бота.\n"
        "Вік — з дати народження в профілі.\n"
        "Кавʼярня / продукт — хто купував у цій точці або цей товар."
        f"{extra}",
        parse_mode="HTML",
        reply_markup=get_clients_sort_keyboard(spots=spots, products=products),
    )
    await callback.answer()


@router.callback_query(IsAdmin(), F.data == "clients_clear_filters")
async def clients_clear_filters(callback: types.CallbackQuery, state: FSMContext):
    await _save_filters(state, spots=[], products=[])
    data = await state.get_data()
    sort = ((data.get("clients_browse") or {}).get("sort")) or "join_desc"
    await _render_clients_list(callback, state, sort=sort, offset=0)
    await callback.answer("Фільтри скинуто")


@router.callback_query(IsAdmin(), F.data == "clients_clear_spots")
async def clients_clear_spots(callback: types.CallbackQuery, state: FSMContext):
    await _save_filters(state, spots=[])
    data = await state.get_data()
    choices = data.get("clients_spot_choices") or []
    if not choices:
        from database_functions.clients_admin_db import list_visit_spots

        choices = list_visit_spots(limit=12)
        await state.update_data(clients_spot_choices=choices)
    await callback.message.edit_text(
        "📍 Обери одну або кілька кавʼярень (повторний тап знімає):\n"
        "Потім «Готово».",
        reply_markup=get_clients_spot_filter_keyboard(choices, selected=[]),
    )
    await callback.answer("Кавʼярні скинуто")


@router.callback_query(IsAdmin(), F.data == "clients_apply_filters")
async def clients_apply_filters(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    sort = ((data.get("clients_browse") or {}).get("sort")) or "spent_desc"
    await _render_clients_list(callback, state, sort=sort, offset=0)
    await callback.answer()


@router.callback_query(IsAdmin(), F.data.startswith("clients_rm_spot:"))
async def clients_rm_spot(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    spots, products = _filters_from_data(data)
    try:
        idx = int((callback.data or "").split(":")[-1])
    except ValueError:
        await callback.answer()
        return
    if 0 <= idx < len(spots):
        spots = [s for i, s in enumerate(spots) if i != idx]
        await _save_filters(state, spots=spots)
    spots, products = _filters_from_data(await state.get_data())
    active = _filters_caption(spots, products)
    extra = f"\n\n<b>Активні зараз</b>{active}" if active else ""
    await callback.message.edit_text(
        "↕️ <b>Сортування та фільтри</b>\n\n"
        "Витрати й Крафтики — за чеками, що вже пройшли через бота.\n"
        "Вік — з дати народження в профілі.\n"
        "Кавʼярня / продукт — хто купував у цій точці або цей товар."
        f"{extra}",
        parse_mode="HTML",
        reply_markup=get_clients_sort_keyboard(spots=spots, products=products),
    )
    await callback.answer("Прибрано")


@router.callback_query(IsAdmin(), F.data.startswith("clients_rm_product:"))
async def clients_rm_product(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    spots, products = _filters_from_data(data)
    try:
        idx = int((callback.data or "").split(":")[-1])
    except ValueError:
        await callback.answer()
        return
    if 0 <= idx < len(products):
        products = [p for i, p in enumerate(products) if i != idx]
        await _save_filters(state, products=products)
    spots, products = _filters_from_data(await state.get_data())
    active = _filters_caption(spots, products)
    extra = f"\n\n<b>Активні зараз</b>{active}" if active else ""
    await callback.message.edit_text(
        "↕️ <b>Сортування та фільтри</b>\n\n"
        "Витрати й Крафтики — за чеками, що вже пройшли через бота.\n"
        "Вік — з дати народження в профілі.\n"
        "Кавʼярня / продукт — хто купував у цій точці або цей товар."
        f"{extra}",
        parse_mode="HTML",
        reply_markup=get_clients_sort_keyboard(spots=spots, products=products),
    )
    await callback.answer("Прибрано")


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
    data = await state.get_data()
    selected, _ = _filters_from_data(data)
    await callback.message.edit_text(
        "📍 Обери <b>одну або кілька</b> кавʼярень (повторний тап знімає).\n"
        "Потім натисни «Готово» — продукт-фільтри збережуться.",
        parse_mode="HTML",
        reply_markup=get_clients_spot_filter_keyboard(spots, selected=selected),
    )
    await callback.answer()


@router.callback_query(IsAdmin(), F.data.startswith("clients_spot:"))
async def clients_spot_pick(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    choices = data.get("clients_spot_choices") or []
    try:
        idx = int((callback.data or "").split(":")[-1])
    except ValueError:
        await callback.answer("Помилка", show_alert=True)
        return
    if idx < 0 or idx >= len(choices):
        from database_functions.clients_admin_db import list_visit_spots

        choices = list_visit_spots(limit=12)
        await state.update_data(clients_spot_choices=choices)
    if idx < 0 or idx >= len(choices):
        await callback.answer("Кавʼярню не знайдено", show_alert=True)
        return
    selected, _ = _filters_from_data(data)
    name = choices[idx]
    if name in selected:
        selected = [s for s in selected if s != name]
    else:
        selected = [*selected, name]
    await _save_filters(state, spots=selected)
    await callback.message.edit_reply_markup(
        reply_markup=get_clients_spot_filter_keyboard(choices, selected=selected)
    )
    await callback.answer("Додано" if name in selected else "Прибрано")


@router.callback_query(IsAdmin(), F.data == "clients_filter_product")
async def clients_filter_product(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    _, products = _filters_from_data(data)
    already = ""
    if products:
        already = (
            "\nУже обрано: <b>"
            + "</b>, <b>".join(_esc(p) for p in products)
            + "</b>\nНовий запит <b>додасться</b> до списку."
        )
    await state.set_state(ClientAdmin.filter_product)
    await callback.message.answer(
        "☕ Введи частину назви товару (напр. <b>капучино</b>).\n"
        "Можна додати кілька продуктів по черзі."
        f"{already}\n"
        "Або «Скасувати».",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(IsAdmin(), ClientAdmin.filter_product, F.text)
async def clients_filter_product_query(message: types.Message, state: FSMContext):
    raw = (message.text or "").strip()
    if raw.lower() in {"скасувати", "cancel", "/cancel"}:
        await state.set_state(None)
        data = await state.get_data()
        spots, products = _filters_from_data(data)
        await message.answer(
            "Скасовано.",
            reply_markup=get_clients_sort_keyboard(spots=spots, products=products),
        )
        return
    data = await state.get_data()
    spots, products = _filters_from_data(data)
    if raw not in products:
        products = [*products, raw]
    await _save_filters(state, products=products)
    await state.set_state(None)
    from database_functions.clients_admin_db import (
        PAGE_SIZE,
        SORT_LABELS,
        list_clients_sorted,
    )

    browse = data.get("clients_browse") or {}
    sort = browse.get("sort") or "spent_desc"
    rows, total = await asyncio.to_thread(
        list_clients_sorted,
        sort,
        offset=0,
        limit=PAGE_SIZE,
        spot_names=spots,
        product_qs=products,
    )
    ids = [int(r["user_id"]) for r in rows]
    await _set_browse(
        state,
        mode="list",
        sort=sort,
        offset=0,
        total=total,
        ids=ids,
        pos=0,
        products=products,
        spots=spots,
        product=products[0] if len(products) == 1 else None,
        spot=spots[0] if len(spots) == 1 else None,
        query=None,
    )
    label = SORT_LABELS.get(sort, sort)
    await message.answer(
        f"📋 <b>Клієнти</b> · {label}\n"
        f"Всього: <b>{total}</b>"
        f"{_filters_caption(spots, products)}\n"
        "<i>Відкрий картку · ⬅️➡️ · Назад збереже фільтри</i>",
        parse_mode="HTML",
        reply_markup=get_clients_list_keyboard(
            rows, sort=sort, offset=0, total=total, page_size=PAGE_SIZE
        ),
    )


@router.callback_query(IsAdmin(), F.data.startswith("clients_refs:"))
async def clients_refs_browse(callback: types.CallbackQuery, state: FSMContext):
    from database_functions.clients_admin_db import list_recent_referrals

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
    ids: list[int] = []
    for ref in page:
        for key in ("friend_user_id", "referrer_user_id"):
            try:
                rid = int(ref.get(key) or 0)
            except (TypeError, ValueError):
                rid = 0
            if rid and rid not in ids:
                ids.append(rid)
    await _set_browse(
        state,
        mode="refs",
        offset=offset,
        total=len(ids),
        ids=ids,
        pos=0,
        sort=None,
        query=None,
    )
    text = (
        "👥 <b>Хто кого привів</b>\n\n"
        "Ліва кнопка — друг, «← хто» — запрошувач.\n"
        "З картки ⬅️➡️ гортає відкритих у цій сторінці · Назад повертає сюди."
    )
    kb = get_referrals_browse_keyboard(page, offset=offset, has_more=has_more)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()


@router.callback_query(IsAdmin(), F.data.startswith("client_refs:"))
async def client_refs_detail(callback: types.CallbackQuery, state: FSMContext):
    from database_functions.anomalies_db import user_name_link
    from database_functions.client_db import get_user
    from database_functions.clients_admin_db import (
        get_referrer_for_friend,
        list_friends_of_referrer,
    )
    from database_functions.referrals_db import referrer_stats
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    uid = int((callback.data or "").split(":")[-1])
    user = get_user(uid)
    if not user:
        await callback.answer("Не знайдено", show_alert=True)
        return
    name = user.get("display_name") or user.get("user_first_name") or uid
    lines = [
        f"👥 <b>Реферали · {user_name_link(uid, name, user.get('user_name'))}</b>\n"
        f"<code>{uid}</code>\n"
    ]
    brought = get_referrer_for_friend(uid)
    if brought:
        rid = brought.get("referrer_user_id")
        rname = brought.get("display_name") or brought.get("user_first_name") or rid
        rphone = (brought.get("user_phone") or "").strip()
        lines.append(
            f"Цього клієнта привів: {user_name_link(rid, rname, brought.get('user_name'))} "
            f"<code>{rid}</code>"
            + (f" · {_esc(rphone)}" if rphone else "")
            + f" · {_esc(brought.get('status'))}"
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
    friend_ids = [uid]
    if brought and brought.get("referrer_user_id"):
        friend_ids.append(int(brought["referrer_user_id"]))
    if friends:
        lines.append("")
        for fr in friends:
            fid = int(fr.get("friend_user_id") or 0)
            fname = fr.get("display_name") or fr.get("user_first_name") or fid or "—"
            if fid and fid not in friend_ids:
                friend_ids.append(fid)
            lines.append(
                f"· {user_name_link(fid or None, fname, fr.get('user_name'))} "
                f"<code>{fr.get('friend_user_id')}</code> · {_esc(fr.get('status'))}"
            )
    # Keep ability to open related people without wiping list context parent
    data = await state.get_data()
    browse = dict(data.get("clients_browse") or {})
    if browse.get("mode") not in {"list", "search", "recent", "blocked"}:
        await _set_browse(state, mode="refs", ids=friend_ids, pos=0, total=len(friend_ids), offset=0)

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ До картки", callback_data=f"client_view:{uid}")],
            [InlineKeyboardButton(text="📋 Усі реферали", callback_data="clients_refs:0")],
            [InlineKeyboardButton(text="◀️ Назад у список", callback_data="clients_back")],
        ]
    )
    try:
        await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=kb)
    except Exception:
        await callback.message.answer("\n".join(lines), parse_mode="HTML", reply_markup=kb)
    await callback.answer()


@router.callback_query(IsAdmin(), F.data == "clients_search")
async def clients_search_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(ClientAdmin.search)
    await callback.message.answer(
        "🔎 Введи запит: <b>телефон</b>, <b>Telegram ID</b>, "
        "<b>номер картки</b>, <b>Poster ID</b>, <b>@username</b> або <b>імʼя</b>.\n"
        "Або «Скасувати».",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(IsAdmin(), ClientAdmin.search, F.text)
async def clients_search_query(message: types.Message, state: FSMContext):
    from database_functions.client_db import search_clients
    from database_functions.clients_admin_db import enrich_clients_list_metrics

    raw = (message.text or "").strip()
    if raw.lower() in {"скасувати", "cancel", "/cancel"}:
        await state.set_state(None)
        await message.answer("Скасовано.", reply_markup=get_clients_hub_keyboard())
        return

    found = await asyncio.to_thread(
        lambda: enrich_clients_list_metrics(search_clients(raw, limit=40))
    )
    await state.set_state(None)
    ids = [int(u["user_id"]) for u in found]
    await _set_browse(
        state,
        mode="search",
        query=raw,
        ids=ids,
        pos=0,
        offset=0,
        total=len(ids),
        sort=None,
    )
    if not found:
        await message.answer(
            f"За запитом «{_esc(raw)}» нікого не знайдено.",
            parse_mode="HTML",
            reply_markup=get_clients_hub_keyboard(),
        )
        return
    if len(found) == 1:
        text, kb = await _build_client_card(
            found[0], browse=(await state.get_data()).get("clients_browse")
        )
        await message.answer(text, parse_mode="HTML", reply_markup=kb)
        return
    await message.answer(
        f"🔎 Запит: <b>{_esc(raw)}</b>\n"
        f"Знайдено: <b>{len(found)}</b>\n"
        "<i>Відкрий картку · ⬅️➡️ між результатами · Назад сюди</i>",
        parse_mode="HTML",
        reply_markup=get_client_search_results_keyboard(found, back="clients_back"),
    )


@router.callback_query(IsAdmin(), F.data == "clients_recent")
async def clients_recent(callback: types.CallbackQuery, state: FSMContext):
    from database_functions.client_db import list_recent_registered
    from database_functions.clients_admin_db import enrich_clients_list_metrics

    rows = await asyncio.to_thread(
        lambda: enrich_clients_list_metrics(list_recent_registered(25))
    )
    if not rows:
        await callback.answer("Немає зареєстрованих", show_alert=True)
        return
    ids = [int(u["user_id"]) for u in rows]
    await _set_browse(
        state, mode="recent", ids=ids, pos=0, offset=0, total=len(ids), sort=None, query=None
    )
    text = (
        f"🆕 <b>Останні зареєстровані</b> · {len(rows)}\n"
        "<i>Гортай картки ⬅️➡️ · Назад повертає до цього списку</i>"
    )
    kb = get_client_search_results_keyboard(rows, back="clients_back")
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()


@router.callback_query(IsAdmin(), F.data == "clients_anomalies")
async def clients_anomalies(callback: types.CallbackQuery, state: FSMContext):
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    from database_functions.anomalies_db import (
        build_anomalies_report,
        busy_referrers,
        enrich_with_users,
        frequent_cashback,
        high_cashback_week,
        micro_checks,
        referral_friends_today,
    )

    await callback.answer("Аналізую…")
    text = await asyncio.to_thread(build_anomalies_report)

    # Collect unique clients from current anomaly slices for quick open
    def _collect_ids() -> list[tuple[int, str]]:
        seen: set[int] = set()
        out: list[tuple[int, str]] = []
        buckets = [
            enrich_with_users(frequent_cashback(hours=24, min_count=4)),
            enrich_with_users(high_cashback_week(min_uah=80)),
            enrich_with_users(micro_checks(hours=24, max_payed=55, min_count=5)),
            enrich_with_users(referral_friends_today(min_count=11)),
            enrich_with_users(busy_referrers(days=7, min_count=11)),
        ]
        for bucket in buckets:
            for r in bucket:
                uid = int(r["user_id"])
                if uid in seen:
                    continue
                seen.add(uid)
                name = (r.get("name") or str(uid)).strip() or str(uid)
                if len(name) > 28:
                    name = name[:27] + "…"
                out.append((uid, name))
                if len(out) >= 12:
                    return out
        return out

    clients = await asyncio.to_thread(_collect_ids)
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=f"➡️ {name}",
                callback_data=f"anomaly_client:{uid}",
            )
        ]
        for uid, name in clients
    ]
    rows.append(
        [InlineKeyboardButton(text="🏠 Меню клієнтів", callback_data="clients_hub")]
    )
    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(IsAdmin(), F.data == "clients_blocked")
async def clients_blocked_list(callback: types.CallbackQuery, state: FSMContext):
    from database_functions.clients_admin_db import enrich_clients_list_metrics
    from database_functions.db import get_connection

    def _load():
        conn = get_connection()
        rows = conn.execute(
            """
            SELECT * FROM users
            WHERE registered = 1 AND COALESCE(bonuses_blocked, 0) = 1
            ORDER BY COALESCE(last_activity, '') DESC
            LIMIT 40
            """
        ).fetchall()
        return enrich_clients_list_metrics([dict(r) for r in rows])

    users = await asyncio.to_thread(_load)
    if not users:
        await callback.answer("Немає заблокованих", show_alert=True)
        return
    ids = [int(u["user_id"]) for u in users]
    await _set_browse(
        state, mode="blocked", ids=ids, pos=0, offset=0, total=len(ids), sort=None, query=None
    )
    text = (
        f"🚫 <b>Заблоковані Крафтики</b> · {len(users)}\n"
        "<i>Гортай картки ⬅️➡️ · Назад повертає до цього списку</i>"
    )
    kb = get_client_search_results_keyboard(users, back="clients_back")
    try:
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer()


@router.callback_query(IsAdmin(), F.data.startswith("client_view:"))
async def client_view(callback: types.CallbackQuery, state: FSMContext):
    uid = int((callback.data or "").split(":", 1)[-1])
    await _show_client_by_id(callback, state, uid, refresh_balance=False)


@router.callback_query(IsAdmin(), F.data.startswith("anomaly_client:"))
async def anomaly_open_client(callback: types.CallbackQuery, state: FSMContext):
    """From anomaly alert: open full client card as a new message (keep the alert)."""
    from database_functions.client_db import get_user

    try:
        uid = int((callback.data or "").split(":", 1)[-1])
    except ValueError:
        await callback.answer("Невірний клієнт", show_alert=True)
        return
    user = get_user(uid)
    if not user or not user.get("registered"):
        await callback.answer("Клієнта не знайдено в базі бота", show_alert=True)
        return
    await callback.answer()
    browse = await _set_browse(
        state,
        mode="anomaly",
        ids=[uid],
        pos=0,
        offset=0,
        total=1,
        query=None,
    )
    text, kb = await _build_client_card(user, browse=browse, refresh_balance=False)
    await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(IsAdmin(), F.data.startswith("client_bal:"))
async def client_balance_poster(callback: types.CallbackQuery, state: FSMContext):
    """Kick Poster refresh in background; keep showing local card meanwhile."""
    from database_functions.client_db import get_user
    from services.balance_sync import refresh_user_balance

    uid = int((callback.data or "").split(":", 1)[-1])
    # Instant local card; Poster goes to background task
    await _show_client_by_id(
        callback,
        state,
        uid,
        refresh_balance=False,
        answer_text="Оновлюю баланс у фоні…",
    )

    data = await state.get_data()
    browse = dict(data.get("clients_browse") or {})
    chat_id = callback.message.chat.id
    msg_id = callback.message.message_id
    bot = callback.message.bot

    async def _bg() -> None:
        try:
            bal = await refresh_user_balance(uid)
            user = get_user(uid)
            if not user:
                return
            text, kb = await _build_client_card(
                user, browse=browse, refresh_balance=False
            )
            note = (
                f"✅ Баланс з Poster: <b>{_uah(bal)}</b>"
                if bal is not None
                else "⚠️ Не вдалося оновити баланс з Poster"
            )
            try:
                await bot.edit_message_text(
                    text,
                    chat_id=chat_id,
                    message_id=msg_id,
                    parse_mode="HTML",
                    reply_markup=kb,
                )
            except Exception:
                await bot.send_message(
                    chat_id, text, parse_mode="HTML", reply_markup=kb
                )
            await bot.send_message(chat_id, note, parse_mode="HTML")
        except Exception as exc:
            log.warning("bg balance refresh user=%s: %s", uid, exc)
            try:
                await bot.send_message(chat_id, f"⚠️ Оновлення балансу: {_esc(exc)}")
            except Exception:
                pass

    asyncio.create_task(_bg(), name=f"client_bal_{uid}")


@router.callback_query(IsAdmin(), F.data == "clients_back")
async def clients_back(callback: types.CallbackQuery, state: FSMContext):
    """Restore previous list / search without resetting filters."""
    data = await state.get_data()
    browse = dict(data.get("clients_browse") or {})
    mode = browse.get("mode")
    if mode == "list":
        sort = browse.get("sort") or "join_desc"
        offset = int(browse.get("offset") or 0)
        await _render_clients_list(callback, state, sort=sort, offset=offset)
        await callback.answer()
        return
    if mode == "search":
        from database_functions.client_db import search_clients
        from database_functions.clients_admin_db import enrich_clients_list_metrics

        query = (browse.get("query") or "").strip()
        found = (
            await asyncio.to_thread(
                lambda: enrich_clients_list_metrics(search_clients(query, limit=40))
            )
            if query
            else []
        )
        ids = [int(u["user_id"]) for u in found]
        await _set_browse(
            state, mode="search", query=query, ids=ids, pos=0, offset=0, total=len(ids)
        )
        if not found:
            await callback.message.edit_text(
                "Результати пошуку застаріли — зроби новий пошук.",
                reply_markup=get_clients_hub_keyboard(),
            )
            await callback.answer()
            return
        text = (
            f"🔎 Запит: <b>{_esc(query)}</b>\n"
            f"Знайдено: <b>{len(found)}</b>"
        )
        kb = get_client_search_results_keyboard(found, back="clients_hub")
        try:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)
        await callback.answer()
        return
    if mode == "recent":
        await clients_recent(callback, state)
        return
    if mode == "blocked":
        await clients_blocked_list(callback, state)
        return
    if mode == "refs":
        offset = int(browse.get("offset") or 0)
        # Reuse refs handler by temporarily setting callback data path
        callback.data = f"clients_refs:{offset}"
        await clients_refs_browse(callback, state)
        return
    await clients_hub_cb(callback, state)


@router.callback_query(IsAdmin(), F.data.startswith("client_nav:"))
async def client_nav(callback: types.CallbackQuery, state: FSMContext):
    from database_functions.clients_admin_db import PAGE_SIZE, list_clients_sorted

    action = (callback.data or "").split(":")[-1]
    if action == "noop":
        await callback.answer()
        return

    data = await state.get_data()
    browse = dict(data.get("clients_browse") or {})
    ids = [int(x) for x in (browse.get("ids") or [])]
    if not ids:
        await callback.answer("Немає списку для гортання — повернись у список", show_alert=True)
        return
    try:
        pos = int(browse.get("pos") or 0)
    except (TypeError, ValueError):
        pos = 0
    pos = max(0, min(pos, len(ids) - 1))
    mode = browse.get("mode") or ""
    offset = int(browse.get("offset") or 0)
    total = int(browse.get("total") or len(ids))

    if action == "prev":
        if pos > 0:
            pos -= 1
        elif mode == "list" and offset > 0:
            spots, products = _filters_from_data(data)
            sort = browse.get("sort") or "join_desc"
            new_offset = max(0, offset - PAGE_SIZE)
            rows, total = await asyncio.to_thread(
                list_clients_sorted,
                sort,
                offset=new_offset,
                limit=PAGE_SIZE,
                spot_names=spots,
                product_qs=products,
            )
            ids = [int(r["user_id"]) for r in rows]
            if not ids:
                await callback.answer("Це перший клієнт", show_alert=True)
                return
            offset = new_offset
            pos = len(ids) - 1
            browse.update(
                ids=ids,
                offset=offset,
                total=total,
                pos=pos,
                spots=spots,
                products=products,
            )
            await state.update_data(clients_browse=browse)
            await _show_client_by_id(callback, state, ids[pos])
            return
        else:
            await callback.answer("Це перший у списку")
            return
    elif action == "next":
        if pos < len(ids) - 1:
            pos += 1
        elif mode == "list" and (offset + len(ids)) < total:
            spots, products = _filters_from_data(data)
            sort = browse.get("sort") or "join_desc"
            new_offset = offset + PAGE_SIZE
            rows, total = await asyncio.to_thread(
                list_clients_sorted,
                sort,
                offset=new_offset,
                limit=PAGE_SIZE,
                spot_names=spots,
                product_qs=products,
            )
            ids = [int(r["user_id"]) for r in rows]
            if not ids:
                await callback.answer("Це останній клієнт", show_alert=True)
                return
            offset = new_offset
            pos = 0
            browse.update(
                ids=ids,
                offset=offset,
                total=total,
                pos=pos,
                spots=spots,
                products=products,
            )
            await state.update_data(clients_browse=browse)
            await _show_client_by_id(callback, state, ids[pos])
            return
        else:
            await callback.answer("Це останній у списку")
            return
    else:
        await callback.answer()
        return

    browse["pos"] = pos
    await state.update_data(clients_browse=browse)
    await _show_client_by_id(callback, state, ids[pos])


def _format_local_history(uid: int, header: str) -> str | None:
    """Build history text from local processed_transactions. None if empty."""
    import json as _json

    from database_functions.settings_db import list_purchases_for_user
    from utils.kyiv_time import format_dt_ua

    local = list_purchases_for_user(uid, limit=25)
    if not local:
        return None
    lines = [header + "<i>З чеків у боті (швидко). Живе з Poster — кнопка нижче.</i>\n"]
    for row in local:
        date = format_dt_ua(row.get("date_close") or row.get("processed_at"))
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
    return text


def _history_kb(uid: int, user: dict, browse: dict | None, *, live: bool = False):
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    nav_label, has_prev, has_next = _browse_nav_meta(browse)
    base = get_client_card_keyboard(
        uid,
        blocked=bool(int(user.get("bonuses_blocked") or 0)),
        nav_label=nav_label,
        has_prev=has_prev,
        has_next=has_next,
        back_label=_back_label_for_browse(browse),
    )
    rows = list(base.inline_keyboard)
    if not live and user.get("poster_client_id"):
        rows.insert(
            0,
            [
                InlineKeyboardButton(
                    text="📡 Історія з Poster (повільно)",
                    callback_data=f"client_hist_live:{uid}",
                )
            ],
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(
    IsAdmin(),
    F.data.startswith("client_hist:") | F.data.startswith("client_hist_live:"),
)
async def client_history(callback: types.CallbackQuery, state: FSMContext):
    from database_functions.client_db import get_user

    raw_data = callback.data or ""
    live = raw_data.startswith("client_hist_live:")
    uid = int(raw_data.split(":", 1)[-1])
    user = get_user(uid)
    if not user:
        await callback.answer("Клієнта не знайдено", show_alert=True)
        return

    from database_functions.anomalies_db import user_name_link

    name = user.get("display_name") or user.get("user_first_name") or str(uid)
    browse = (await state.get_data()).get("clients_browse")
    header = (
        f"📜 <b>Історія · {user_name_link(uid, name, user.get('user_name'))}</b>\n"
        f"<code>{uid}</code>\n"
    )
    kb = _history_kb(uid, user, browse, live=live)

    if not live:
        await callback.answer()
        text = await asyncio.to_thread(_format_local_history, uid, header)
        if not text:
            if user.get("poster_client_id"):
                await callback.message.answer(
                    header
                    + "\nЛокальних чеків немає. Можна підвантажити з Poster:",
                    parse_mode="HTML",
                    reply_markup=kb,
                )
            else:
                await callback.message.answer(
                    header + "\nПокупок ще немає",
                    parse_mode="HTML",
                    reply_markup=kb,
                )
            return
        await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)
        return

    if not user.get("poster_client_id"):
        await callback.answer("Немає Poster-клієнта", show_alert=True)
        return

    await callback.answer("Завантажую з Poster…")
    wait = await callback.message.answer("⏳ Історія з Poster (до ~40 с)…")
    from database_functions.settings_db import list_bonus_accruals_for_user
    from services import poster
    from utils.kyiv_time import format_dt_ua

    client_id = user["poster_client_id"]
    accruals: dict[str, float] = {}
    try:
        for acc in list_bonus_accruals_for_user(uid):
            tid = str(acc.get("transaction_id") or "")
            if tid:
                accruals[tid] = float(acc.get("bonus_uah") or 0)
    except Exception:
        pass

    def _load() -> tuple[list[dict], dict[int, str]]:
        txs = poster.get_transactions_for_client(
            client_id, days=90, include_products=True
        )
        spots = {
            int(s["spot_id"]): s.get("spot_name") or ""
            for s in poster.get_spots()
            if s.get("spot_id") is not None
        }
        # Resolve product lines inside the worker (no extra loop on event loop)
        enriched = []
        for t in sorted(txs, key=lambda x: x.get("date_close_date") or "", reverse=True)[
            :25
        ]:
            tid = str(t.get("transaction_id") or poster.transaction_id_from_row(t) or "")
            items = poster.tx_product_lines(t)
            if not items and tid:
                try:
                    items = poster.tx_product_lines(poster.get_transaction(tid) or {})
                except Exception:
                    items = []
            row = dict(t)
            row["_items"] = items
            row["_tid"] = tid
            enriched.append(row)
        return enriched, spots

    try:
        txs, spots = await asyncio.wait_for(asyncio.to_thread(_load), timeout=40)
    except asyncio.TimeoutError:
        log.warning("admin history timeout user=%s", uid)
        await callback.message.answer(
            header + "\nТаймаут Poster. Показано можна локальну історію.",
            parse_mode="HTML",
            reply_markup=_history_kb(uid, user, browse, live=False),
        )
        try:
            await wait.delete()
        except Exception:
            pass
        return
    except Exception as exc:
        log.warning("admin history user=%s: %s", uid, exc)
        await callback.message.answer(
            header + f"\nПомилка Poster: {_esc(exc)}",
            parse_mode="HTML",
            reply_markup=kb,
        )
        try:
            await wait.delete()
        except Exception:
            pass
        return

    try:
        await wait.delete()
    except Exception:
        pass

    if not txs:
        await callback.message.answer(
            header + "\nУ Poster покупок за 90 днів немає",
            parse_mode="HTML",
            reply_markup=kb,
        )
        return

    lines = [header + "<i>Живі дані Poster (90 днів)</i>\n"]
    for t in txs:
        tid = t.get("_tid") or ""
        date = format_dt_ua(t.get("date_close_date"))
        payed = poster.from_minor(t.get("payed_sum"))
        spent = poster.from_minor(t.get("payed_bonus") or 0)
        try:
            spot = spots.get(int(t.get("spot_id") or 0), "")
        except (TypeError, ValueError):
            spot = ""
        cashback = accruals.get(str(tid), 0.0)
        extra = []
        if cashback > 0:
            extra.append(f"+{_uah(cashback)} кешбек")
        if spent > 0:
            extra.append(f"−{_uah(spent)} списано")
        tail = f" · {', '.join(extra)}" if extra else ""
        spot_s = f" · {_esc(spot)}" if spot else ""
        lines.append(f"• {_esc(date)}{spot_s}: <b>{_uah(payed)}</b> грн{tail}")
        for it in (t.get("_items") or [])[:8]:
            qty = float(it.get("count") or 1)
            qty_s = f"{qty:g}× " if qty > 1 else ""
            lines.append(f"    ◦ {_esc(qty_s)}{_esc(it.get('name') or 'Товар')}")

    text = "\n".join(lines)
    if len(text) > 3900:
        text = text[:3900] + "\n…"
    await callback.message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(IsAdmin(), F.data.startswith("client_block:"))
async def client_block(callback: types.CallbackQuery, state: FSMContext):
    from database_functions.client_db import get_user, set_bonuses_blocked

    uid = int((callback.data or "").split(":", 1)[-1])
    user = get_user(uid)
    if not user:
        await callback.answer("Не знайдено", show_alert=True)
        return
    set_bonuses_blocked(uid, True)
    user = get_user(uid) or user
    browse = (await state.get_data()).get("clients_browse")
    text, kb = await _build_client_card(user, browse=browse, refresh_balance=False)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await callback.answer("Крафтики заблоковано")


@router.callback_query(IsAdmin(), F.data.startswith("client_unblock:"))
async def client_unblock(callback: types.CallbackQuery, state: FSMContext):
    from database_functions.client_db import get_user, set_bonuses_blocked

    uid = int((callback.data or "").split(":", 1)[-1])
    user = get_user(uid)
    if not user:
        await callback.answer("Не знайдено", show_alert=True)
        return
    set_bonuses_blocked(uid, False)
    user = get_user(uid) or user
    browse = (await state.get_data()).get("clients_browse")
    text, kb = await _build_client_card(user, browse=browse, refresh_balance=False)
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

    raw = (message.text or "").strip().replace(",", ".")
    data = await state.get_data()
    browse = data.get("clients_browse")
    if raw.lower() in {"скасувати", "cancel", "/cancel"}:
        await state.set_state(None)
        await message.answer("Скасовано.")
        return

    uid = int(data.get("gift_user_id") or 0)
    user = get_user(uid)
    if not user or not user.get("poster_client_id"):
        await state.set_state(None)
        await message.answer("Клієнта не знайдено.", reply_markup=get_clients_hub_keyboard())
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
    wait = await message.answer("⏳ Нараховую в Poster…")

    def _do_gift() -> dict:
        from database_functions import bonus_ledger_db as ldb
        from database_functions.client_db import touch_bonus_accrual
        from services.bonus_ops import apply_bonus_delta
        from utils.kyiv_time import kyiv_now_str

        result = apply_bonus_delta(
            op_key=f"admin_gift:user:{uid}:{kyiv_now_str()}",
            amount_uah=amount,
            reason=ldb.REASON_ADMIN_GIFT,
            user_id=int(uid),
            poster_client_id=cid,
            title=ldb.REASON_TITLES_UK[ldb.REASON_ADMIN_GIFT],
            admin_user_id=int(message.from_user.id),
            create_lot=True,
        )
        if result.get("status") != "ok":
            return result
        touch_bonus_accrual(uid)
        new_bal = result.get("balance_after")
        if new_bal is None:
            try:
                new_bal = poster.get_client_bonus_uah(cid, timeout=6.0)
                result["balance_after"] = new_bal
            except Exception:
                pass
        try:
            from services.wallet_sync import sync_wallets_for_user

            sync_wallets_for_user(int(uid), bonus=result.get("balance_after"))
        except Exception:
            pass
        return result

    try:
        result = await asyncio.to_thread(_do_gift)
        if result.get("status") != "ok":
            await message.answer(
                f"Не вдалося нарахувати: {_esc(result.get('error') or 'помилка')}"
            )
            return
        new_bal = result.get("balance_after")
    except Exception as exc:
        log.exception("admin gift user=%s", uid)
        await message.answer(f"Не вдалося нарахувати в Poster: {_esc(exc)}")
        return
    finally:
        try:
            await wait.delete()
        except Exception:
            pass

    await state.set_state(None)
    if browse is not None:
        await state.update_data(clients_browse=browse)
    from database_functions.anomalies_db import user_name_link

    name = user.get("display_name") or user.get("user_first_name") or str(uid)
    await message.answer(
        f"✅ Нараховано <b>+{_uah(amount)}</b> Крафтиків клієнту "
        f"{user_name_link(uid, name, user.get('user_name'))} "
        f"(<code>{uid}</code>).\n"
        f"Новий баланс: <b>{_uah(new_bal)}</b>",
        parse_mode="HTML",
    )
    text, kb = await _build_client_card(
        get_user(uid) or user, browse=browse, refresh_balance=False
    )
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


@router.callback_query(IsAdmin(), F.data.startswith("client_cashback:"))
async def client_cashback_start(callback: types.CallbackQuery, state: FSMContext):
    from database_functions.client_db import get_user

    uid = int((callback.data or "").split(":", 1)[-1])
    user = get_user(uid)
    if not user:
        await callback.answer("Клієнта не знайдено", show_alert=True)
        return
    current = user.get("personal_cashback_percent")
    cur = f"{float(current):g}%" if current is not None else "не задано"
    await state.set_state(ClientAdmin.cashback_percent)
    await state.update_data(cashback_user_id=uid)
    await callback.message.answer(
        f"📈 Персональний кешбек для <code>{uid}</code>\n"
        f"Зараз: <b>{cur}</b>\n\n"
        "Введи відсоток (наприклад <code>5</code> або <code>7.5</code>).\n"
        "Ефективний кешбек = max(персональний, Заряд).\n"
        "«0» або «скинути» — прибрати персональний %.\n"
        "Або «Скасувати».",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(IsAdmin(), ClientAdmin.cashback_percent, F.text)
async def client_cashback_set(message: types.Message, state: FSMContext):
    from database_functions.client_db import get_user, set_personal_cashback_percent
    from database_functions import bonus_ledger_db as ldb
    from utils.kyiv_time import kyiv_now_str

    raw = (message.text or "").strip().replace(",", ".")
    data = await state.get_data()
    browse = data.get("clients_browse")
    if raw.lower() in {"скасувати", "cancel", "/cancel"}:
        await state.set_state(None)
        await message.answer("Скасовано.")
        return

    uid = int(data.get("cashback_user_id") or 0)
    user = get_user(uid)
    if not user:
        await state.set_state(None)
        await message.answer("Клієнта не знайдено.", reply_markup=get_clients_hub_keyboard())
        return

    if raw.lower() in {"скинути", "reset", "0", "0.0"}:
        set_personal_cashback_percent(uid, None)
        note = "скинуто"
        pct_val = 0.0
    else:
        try:
            pct_val = float(raw)
        except ValueError:
            await message.answer("Некоректне число. Приклад: <code>5</code>", parse_mode="HTML")
            return
        if pct_val < 0 or pct_val > 50:
            await message.answer("Відсоток має бути від 0 до 50.")
            return
        if pct_val == 0:
            set_personal_cashback_percent(uid, None)
            note = "скинуто"
        else:
            set_personal_cashback_percent(uid, pct_val)
            note = f"встановлено {pct_val:g}%"

    # Audit in ledger (zero amount, factual admin action)
    row = ldb.create_pending(
        op_key=f"admin_cashback:user:{uid}:{kyiv_now_str()}",
        user_id=uid,
        poster_client_id=user.get("poster_client_id"),
        amount_uah=0,
        reason="admin_cashback",
        title=f"Перс. кешбек: {note}",
        admin_user_id=int(message.from_user.id),
        meta={"personal_cashback_percent": None if note == "скинуто" else pct_val},
    )
    ldb.mark_posted(int(row["id"]))

    await state.set_state(None)
    if browse is not None:
        await state.update_data(clients_browse=browse)
    await message.answer(
        f"✅ Персональний кешбек {note} для <code>{uid}</code>.",
        parse_mode="HTML",
    )
    text, kb = await _build_client_card(
        get_user(uid) or user, browse=browse, refresh_balance=False
    )
    await message.answer(text, parse_mode="HTML", reply_markup=kb)
