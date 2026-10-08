"""Admin: seasonal / promo menu CRUD."""
from __future__ import annotations

import html
import logging
from pathlib import Path

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup

from database_functions import promo_menu_db as promo
from keyboards.admin_keyboards import admin_keyboard
from main import bot
from states.admin_states import PromoMenu
from utils.filters import IsAdmin

log = logging.getLogger(__name__)
router = Router()


def _items_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for item in promo.list_items(active_only=False):
        mark = "✅" if item.get("active") else "⏸"
        price = float(item.get("price_uah") or 0)
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{mark} {item['title']} — {price:g} грн",
                    callback_data=f"promo_item:{item['id']}",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="➕ Додати напій", callback_data="promo_add")]
    )
    rows.append(
        [InlineKeyboardButton(text="🔄 Оновити", callback_data="promo_list")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _item_actions(item: dict) -> InlineKeyboardMarkup:
    item_id = int(item["id"])
    active = bool(item.get("active"))
    has_photo = bool(item.get("photo_path"))
    toggle = "⏸ Вимкнути" if active else "✅ Увімкнути"
    photo_rows = [
        [
            InlineKeyboardButton(
                text="🖼 Змінити фото",
                callback_data=f"promo_edit_photo:{item_id}",
            )
        ]
    ]
    if has_photo:
        photo_rows.append(
            [
                InlineKeyboardButton(
                    text="🗑 Прибрати фото",
                    callback_data=f"promo_clear_photo:{item_id}",
                )
            ]
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ Назва",
                    callback_data=f"promo_edit_title:{item_id}",
                ),
                InlineKeyboardButton(
                    text="💰 Ціна",
                    callback_data=f"promo_edit_price:{item_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="↕️ Порядок",
                    callback_data=f"promo_edit_sort:{item_id}",
                ),
                InlineKeyboardButton(
                    text=toggle,
                    callback_data=f"promo_toggle:{item_id}",
                ),
            ],
            *photo_rows,
            [
                InlineKeyboardButton(
                    text="🗑 Видалити",
                    callback_data=f"promo_del:{item_id}",
                )
            ],
            [InlineKeyboardButton(text="◀️ До списку", callback_data="promo_list")],
        ]
    )


def _list_text() -> str:
    items = promo.list_items(active_only=False)
    return (
        "🍽 <b>Сезонне / акційне меню</b>\n\n"
        "Ці позиції показуються в Mini App → «Меню».\n"
        f"Зараз у списку: <b>{len(items)}</b>."
    )


def _item_detail_text(item: dict) -> str:
    status = "✅ активна" if item.get("active") else "⏸ вимкнена"
    photo = item.get("photo_path")
    photo_line = "є" if photo else "немає"
    if photo:
        photo_line += f" (<code>{html.escape(str(photo))}</code>)"
    return (
        f"🍽 <b>{html.escape(str(item.get('title') or ''))}</b>\n\n"
        f"ID: <code>{int(item['id'])}</code>\n"
        f"Назва: <b>{html.escape(str(item.get('title') or ''))}</b>\n"
        f"Ціна: <b>{float(item.get('price_uah') or 0):g} грн</b>\n"
        f"Порядок: <b>{int(item.get('sort_order') or 0)}</b>\n"
        f"Фото: {photo_line}\n"
        f"Статус: {status}\n"
        f"Створено: <code>{html.escape(str(item.get('created_at') or '—'))}</code>\n"
        f"Оновлено: <code>{html.escape(str(item.get('updated_at') or '—'))}</code>\n\n"
        "Обери, що змінити:"
    )


async def _safe_delete(message: types.Message) -> None:
    try:
        await message.delete()
    except Exception:
        pass


async def _show_list(target: types.Message, *, replace: bool = False) -> None:
    text = _list_text()
    kb = _items_keyboard()
    if replace:
        await _safe_delete(target)
        await target.answer(text, parse_mode="HTML", reply_markup=kb)
        return
    try:
        await target.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await target.answer(text, parse_mode="HTML", reply_markup=kb)


async def _show_item(
    target: types.Message,
    item: dict,
    *,
    replace: bool = False,
) -> None:
    text = _item_detail_text(item)
    kb = _item_actions(item)
    photo_file = promo.local_photo_path(item.get("photo_path"))
    # Photo cards and type switches need a fresh message.
    need_new = replace or bool(target.photo) or bool(photo_file)

    if need_new:
        await _safe_delete(target)
        if photo_file:
            await target.answer_photo(
                FSInputFile(photo_file),
                caption=text,
                parse_mode="HTML",
                reply_markup=kb,
            )
        else:
            await target.answer(text, parse_mode="HTML", reply_markup=kb)
        return

    try:
        await target.edit_text(text, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await target.answer(text, parse_mode="HTML", reply_markup=kb)


@router.message(IsAdmin(), F.text == "🍽 Меню")
async def promo_menu_entry(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        _list_text(),
        parse_mode="HTML",
        reply_markup=_items_keyboard(),
    )


@router.callback_query(IsAdmin(), F.data == "promo_list")
async def promo_list(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await _show_list(callback.message, replace=bool(callback.message.photo))
    await callback.answer()


@router.callback_query(IsAdmin(), F.data == "promo_add")
async def promo_add_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(PromoMenu.title)
    await callback.message.answer(
        "Введи <b>назву</b> напою.\nНаприклад: <code>Раф солона карамель</code>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(IsAdmin(), PromoMenu.title)
async def promo_add_title(message: types.Message, state: FSMContext):
    title = (message.text or "").strip()
    if len(title) < 2 or len(title) > 80:
        await message.answer("Назва: від 2 до 80 символів.")
        return
    await state.update_data(title=title)
    await state.set_state(PromoMenu.price)
    await message.answer(
        "Введи <b>ціну в гривнях</b>.\nНаприклад: <code>85</code> або <code>89.5</code>",
        parse_mode="HTML",
    )


@router.message(IsAdmin(), PromoMenu.price)
async def promo_add_price(message: types.Message, state: FSMContext):
    raw = (message.text or "").replace(",", ".").strip()
    try:
        price = float(raw)
        if price < 0 or price > 100000:
            raise ValueError
    except ValueError:
        await message.answer("Введи коректну ціну, наприклад 85.")
        return
    await state.update_data(price=price)
    await state.set_state(PromoMenu.photo)
    await message.answer(
        "Надішли <b>фото</b> напою одним зображенням.\n"
        "Або напиши <code>—</code>, щоб додати без фото.",
        parse_mode="HTML",
    )


async def _save_photo_file(item_id: int, photo: types.PhotoSize) -> str | None:
    try:
        file = await bot.get_file(photo.file_id)
        dest = promo.UPLOAD_DIR / f"{item_id}.jpg"
        await bot.download_file(file.file_path, destination=dest)
        rel = f"uploads/menu/{item_id}.jpg"
        promo.set_photo(item_id, rel)
        return rel
    except Exception:
        log.exception("promo photo download failed id=%s", item_id)
        return None


@router.message(IsAdmin(), PromoMenu.photo, F.photo)
async def promo_add_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    title = data.get("title")
    price = data.get("price")
    if not title or price is None:
        await state.clear()
        await message.answer("Сесію скинуто. Відкрий «🍽 Меню» знову.")
        return

    item_id = promo.add_item(title=title, price_uah=float(price), photo_path=None)
    ok = await _save_photo_file(item_id, message.photo[-1])
    await state.clear()
    if not ok:
        await message.answer(
            "Позицію створено, але фото не збереглося. Можна змінити фото в картці."
        )
    else:
        await message.answer(
            f"✅ Додано: <b>{html.escape(str(title))}</b> — {float(price):g} грн",
            parse_mode="HTML",
            reply_markup=admin_keyboard(),
        )
    item = promo.get_item(item_id)
    if item:
        await _show_item(message, item, replace=False)
    else:
        await message.answer(_list_text(), parse_mode="HTML", reply_markup=_items_keyboard())


@router.message(IsAdmin(), PromoMenu.photo)
async def promo_add_photo_skip(message: types.Message, state: FSMContext):
    raw = (message.text or "").strip()
    if raw not in ("—", "-", "ні", "без фото", "skip"):
        await message.answer("Надішли фото або напиши «—».")
        return
    data = await state.get_data()
    title = data.get("title")
    price = data.get("price")
    if not title or price is None:
        await state.clear()
        await message.answer("Сесію скинуто. Відкрий «🍽 Меню» знову.")
        return
    item_id = promo.add_item(title=title, price_uah=float(price), photo_path=None)
    await state.clear()
    await message.answer(
        f"✅ Додано без фото: <b>{html.escape(str(title))}</b> — {float(price):g} грн",
        parse_mode="HTML",
        reply_markup=admin_keyboard(),
    )
    item = promo.get_item(item_id)
    if item:
        await _show_item(message, item, replace=False)


@router.callback_query(IsAdmin(), F.data.startswith("promo_item:"))
async def promo_item_view(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    item_id = int(callback.data.split(":")[-1])
    item = promo.get_item(item_id)
    if not item:
        await callback.answer("Не знайдено", show_alert=True)
        return
    await _show_item(callback.message, item)
    await callback.answer()


@router.callback_query(IsAdmin(), F.data.startswith("promo_edit_title:"))
async def promo_edit_title_start(callback: types.CallbackQuery, state: FSMContext):
    item_id = int(callback.data.split(":")[-1])
    item = promo.get_item(item_id)
    if not item:
        await callback.answer("Не знайдено", show_alert=True)
        return
    await state.set_state(PromoMenu.edit_title)
    await state.update_data(edit_item_id=item_id)
    await callback.message.answer(
        f"Поточна назва: <b>{html.escape(str(item['title']))}</b>\n\n"
        "Введи <b>нову назву</b> (2–80 символів).\n"
        "Або /cancel щоб скасувати.",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(IsAdmin(), PromoMenu.edit_title, F.text == "/cancel")
@router.message(IsAdmin(), PromoMenu.edit_price, F.text == "/cancel")
@router.message(IsAdmin(), PromoMenu.edit_photo, F.text == "/cancel")
@router.message(IsAdmin(), PromoMenu.edit_sort, F.text == "/cancel")
async def promo_edit_cancel(message: types.Message, state: FSMContext):
    data = await state.get_data()
    item_id = data.get("edit_item_id")
    await state.clear()
    item = promo.get_item(int(item_id)) if item_id else None
    await message.answer("Скасовано.")
    if item:
        await _show_item(message, item, replace=False)


@router.message(IsAdmin(), PromoMenu.edit_title)
async def promo_edit_title_save(message: types.Message, state: FSMContext):
    data = await state.get_data()
    item_id = data.get("edit_item_id")
    title = (message.text or "").strip()
    if not item_id:
        await state.clear()
        await message.answer("Сесію скинуто.")
        return
    if len(title) < 2 or len(title) > 80:
        await message.answer("Назва: від 2 до 80 символів.")
        return
    promo.set_title(int(item_id), title)
    await state.clear()
    item = promo.get_item(int(item_id))
    await message.answer("✅ Назву оновлено.")
    if item:
        await _show_item(message, item, replace=False)


@router.callback_query(IsAdmin(), F.data.startswith("promo_edit_price:"))
async def promo_edit_price_start(callback: types.CallbackQuery, state: FSMContext):
    item_id = int(callback.data.split(":")[-1])
    item = promo.get_item(item_id)
    if not item:
        await callback.answer("Не знайдено", show_alert=True)
        return
    await state.set_state(PromoMenu.edit_price)
    await state.update_data(edit_item_id=item_id)
    await callback.message.answer(
        f"Поточна ціна: <b>{float(item.get('price_uah') or 0):g} грн</b>\n\n"
        "Введи <b>нову ціну</b>, наприклад <code>89.5</code>.\n"
        "Або /cancel щоб скасувати.",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(IsAdmin(), PromoMenu.edit_price)
async def promo_edit_price_save(message: types.Message, state: FSMContext):
    data = await state.get_data()
    item_id = data.get("edit_item_id")
    if not item_id:
        await state.clear()
        await message.answer("Сесію скинуто.")
        return
    raw = (message.text or "").replace(",", ".").strip()
    try:
        price = float(raw)
        if price < 0 or price > 100000:
            raise ValueError
    except ValueError:
        await message.answer("Введи коректну ціну, наприклад 85.")
        return
    promo.set_price(int(item_id), price)
    await state.clear()
    item = promo.get_item(int(item_id))
    await message.answer("✅ Ціну оновлено.")
    if item:
        await _show_item(message, item, replace=False)


@router.callback_query(IsAdmin(), F.data.startswith("promo_edit_sort:"))
async def promo_edit_sort_start(callback: types.CallbackQuery, state: FSMContext):
    item_id = int(callback.data.split(":")[-1])
    item = promo.get_item(item_id)
    if not item:
        await callback.answer("Не знайдено", show_alert=True)
        return
    await state.set_state(PromoMenu.edit_sort)
    await state.update_data(edit_item_id=item_id)
    await callback.message.answer(
        f"Поточний порядок: <b>{int(item.get('sort_order') or 0)}</b>\n\n"
        "Введи ціле число (менше = вище в меню).\n"
        "Або /cancel щоб скасувати.",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(IsAdmin(), PromoMenu.edit_sort)
async def promo_edit_sort_save(message: types.Message, state: FSMContext):
    data = await state.get_data()
    item_id = data.get("edit_item_id")
    if not item_id:
        await state.clear()
        await message.answer("Сесію скинуто.")
        return
    raw = (message.text or "").strip()
    try:
        sort_order = int(raw)
        if sort_order < 0 or sort_order > 100000:
            raise ValueError
    except ValueError:
        await message.answer("Введи ціле число, наприклад 1.")
        return
    promo.set_sort_order(int(item_id), sort_order)
    await state.clear()
    item = promo.get_item(int(item_id))
    await message.answer("✅ Порядок оновлено.")
    if item:
        await _show_item(message, item, replace=False)


@router.callback_query(IsAdmin(), F.data.startswith("promo_edit_photo:"))
async def promo_edit_photo_start(callback: types.CallbackQuery, state: FSMContext):
    item_id = int(callback.data.split(":")[-1])
    item = promo.get_item(item_id)
    if not item:
        await callback.answer("Не знайдено", show_alert=True)
        return
    await state.set_state(PromoMenu.edit_photo)
    await state.update_data(edit_item_id=item_id)
    await callback.message.answer(
        "Надішли <b>нове фото</b> одним зображенням.\n"
        "Або /cancel щоб скасувати.",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(IsAdmin(), PromoMenu.edit_photo, F.photo)
async def promo_edit_photo_save(message: types.Message, state: FSMContext):
    data = await state.get_data()
    item_id = data.get("edit_item_id")
    if not item_id:
        await state.clear()
        await message.answer("Сесію скинуто.")
        return
    ok = await _save_photo_file(int(item_id), message.photo[-1])
    await state.clear()
    if not ok:
        await message.answer("Не вдалося зберегти фото. Спробуй ще раз.")
        return
    item = promo.get_item(int(item_id))
    await message.answer("✅ Фото оновлено.")
    if item:
        await _show_item(message, item, replace=False)


@router.message(IsAdmin(), PromoMenu.edit_photo)
async def promo_edit_photo_need_image(message: types.Message):
    await message.answer("Надішли фото зображенням, або /cancel.")


@router.callback_query(IsAdmin(), F.data.startswith("promo_clear_photo:"))
async def promo_clear_photo(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    item_id = int(callback.data.split(":")[-1])
    item = promo.get_item(item_id)
    if not item:
        await callback.answer("Не знайдено", show_alert=True)
        return
    promo.clear_photo(item_id)
    item = promo.get_item(item_id)
    await callback.answer("Фото прибрано")
    if item:
        await _show_item(callback.message, item, replace=True)


@router.callback_query(IsAdmin(), F.data.startswith("promo_toggle:"))
async def promo_toggle(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    item_id = int(callback.data.split(":")[-1])
    item = promo.get_item(item_id)
    if not item:
        await callback.answer("Не знайдено", show_alert=True)
        return
    promo.set_active(item_id, not bool(item.get("active")))
    item = promo.get_item(item_id)
    await callback.answer("Оновлено")
    if item:
        await _show_item(callback.message, item, replace=bool(callback.message.photo))


@router.callback_query(IsAdmin(), F.data.startswith("promo_del:"))
async def promo_delete(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    item_id = int(callback.data.split(":")[-1])
    promo.delete_item(item_id)
    await callback.answer("Видалено")
    await _show_list(callback.message, replace=bool(callback.message.photo))
