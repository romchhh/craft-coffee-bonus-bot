"""Admin: coffee shop spots CRUD (name, address, maps, photo)."""
from __future__ import annotations

import html
import logging

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup

from database_functions import spots_db as spots
from keyboards.admin_keyboards import admin_keyboard
from main import bot
from states.admin_states import SpotsAdmin
from utils.filters import IsAdmin

log = logging.getLogger(__name__)
router = Router()


def _items_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for item in spots.list_spots(active_only=False):
        mark = "✅" if item.get("active") else "⏸"
        name = str(item.get("name") or "Без назви")
        if len(name) > 40:
            name = name[:37] + "…"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{mark} {name}",
                    callback_data=f"spot_item:{item['id']}",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="➕ Додати точку", callback_data="spot_add")]
    )
    rows.append(
        [InlineKeyboardButton(text="🔄 Оновити", callback_data="spot_list")]
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
                callback_data=f"spot_edit_photo:{item_id}",
            )
        ]
    ]
    if has_photo:
        photo_rows.append(
            [
                InlineKeyboardButton(
                    text="🗑 Прибрати фото",
                    callback_data=f"spot_clear_photo:{item_id}",
                )
            ]
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ Назва",
                    callback_data=f"spot_edit_name:{item_id}",
                ),
                InlineKeyboardButton(
                    text="🏠 Адреса",
                    callback_data=f"spot_edit_address:{item_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🗺 Карти",
                    callback_data=f"spot_edit_maps:{item_id}",
                ),
                InlineKeyboardButton(
                    text="↕️ Порядок",
                    callback_data=f"spot_edit_sort:{item_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=toggle,
                    callback_data=f"spot_toggle:{item_id}",
                )
            ],
            *photo_rows,
            [
                InlineKeyboardButton(
                    text="🗑 Видалити",
                    callback_data=f"spot_del:{item_id}",
                )
            ],
            [InlineKeyboardButton(text="◀️ До списку", callback_data="spot_list")],
        ]
    )


def _list_text() -> str:
    items = spots.list_spots(active_only=False)
    return (
        "📍 <b>Точки</b>\n\n"
        "Ці заклади показуються в Mini App → «Точки».\n"
        f"Зараз у списку: <b>{len(items)}</b>."
    )


def _item_detail_text(item: dict) -> str:
    status = "✅ активна" if item.get("active") else "⏸ вимкнена"
    photo = item.get("photo_path")
    photo_line = "є" if photo else "немає"
    if photo:
        photo_line += f" (<code>{html.escape(str(photo))}</code>)"
    maps = item.get("maps_url") or "—"
    maps_esc = html.escape(str(maps))
    if maps != "—" and len(maps_esc) > 80:
        maps_esc = maps_esc[:77] + "…"
    return (
        f"📍 <b>{html.escape(str(item.get('name') or ''))}</b>\n\n"
        f"ID: <code>{int(item['id'])}</code>\n"
        f"Назва: <b>{html.escape(str(item.get('name') or ''))}</b>\n"
        f"Адреса: <b>{html.escape(str(item.get('address') or ''))}</b>\n"
        f"Карти: <code>{maps_esc}</code>\n"
        f"Порядок: <b>{int(item.get('sort_order') or 0)}</b>\n"
        f"Фото: {photo_line}\n"
        f"Статус: {status}\n\n"
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
    photo_file = spots.local_photo_path(item.get("photo_path"))
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


@router.message(IsAdmin(), F.text == "📍 Точки")
async def spots_entry(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        _list_text(),
        parse_mode="HTML",
        reply_markup=_items_keyboard(),
    )


@router.callback_query(IsAdmin(), F.data == "spot_list")
async def spot_list(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await _show_list(callback.message, replace=bool(callback.message.photo))
    await callback.answer()


@router.callback_query(IsAdmin(), F.data == "spot_add")
async def spot_add_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(SpotsAdmin.name)
    await callback.message.answer(
        "Введи <b>назву</b> точки.\nНаприклад: <code>Крафт 1 · Героїв України 20Б</code>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(IsAdmin(), SpotsAdmin.name)
async def spot_add_name(message: types.Message, state: FSMContext):
    name = (message.text or "").strip()
    if len(name) < 2 or len(name) > 120:
        await message.answer("Назва: від 2 до 120 символів.")
        return
    await state.update_data(name=name)
    await state.set_state(SpotsAdmin.address)
    await message.answer(
        "Введи <b>адресу</b>.\nНаприклад: <code>вул. Героїв України, 20Б</code>",
        parse_mode="HTML",
    )


@router.message(IsAdmin(), SpotsAdmin.address)
async def spot_add_address(message: types.Message, state: FSMContext):
    address = (message.text or "").strip()
    if len(address) < 2 or len(address) > 200:
        await message.answer("Адреса: від 2 до 200 символів.")
        return
    await state.update_data(address=address)
    await state.set_state(SpotsAdmin.maps_url)
    await message.answer(
        "Надішли <b>посилання на Google Maps</b>.\n"
        "Або напиши <code>—</code>, щоб пропустити.",
        parse_mode="HTML",
    )


@router.message(IsAdmin(), SpotsAdmin.maps_url)
async def spot_add_maps(message: types.Message, state: FSMContext):
    raw = (message.text or "").strip()
    maps_url = None
    if raw not in ("—", "-", "ні", "skip"):
        if not (raw.startswith("http://") or raw.startswith("https://")):
            await message.answer(
                "Потрібне посилання http(s)://… або «—» щоб пропустити."
            )
            return
        if len(raw) > 500:
            await message.answer("Посилання занадто довге (макс. 500).")
            return
        maps_url = raw
    await state.update_data(maps_url=maps_url)
    await state.set_state(SpotsAdmin.photo)
    await message.answer(
        "Надішли <b>фото</b> точки одним зображенням.\n"
        "Або напиши <code>—</code>, щоб додати без фото.",
        parse_mode="HTML",
    )


async def _save_photo_file(spot_id: int, photo: types.PhotoSize) -> str | None:
    try:
        file = await bot.get_file(photo.file_id)
        dest = spots.UPLOAD_DIR / f"{spot_id}.jpg"
        await bot.download_file(file.file_path, destination=dest)
        rel = f"uploads/spots/{spot_id}.jpg"
        spots.set_photo(spot_id, rel)
        return rel
    except Exception:
        log.exception("spot photo download failed id=%s", spot_id)
        return None


@router.message(IsAdmin(), SpotsAdmin.photo, F.photo)
async def spot_add_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    name = data.get("name")
    address = data.get("address")
    maps_url = data.get("maps_url")
    if not name or not address:
        await state.clear()
        await message.answer("Сесію скинуто. Відкрий «📍 Точки» знову.")
        return

    spot_id = spots.add_spot(name=name, address=address, maps_url=maps_url)
    ok = await _save_photo_file(spot_id, message.photo[-1])
    await state.clear()
    if not ok:
        await message.answer(
            "Точку створено, але фото не збереглося. Можна змінити фото в картці."
        )
    else:
        await message.answer(
            f"✅ Додано: <b>{html.escape(str(name))}</b>",
            parse_mode="HTML",
            reply_markup=admin_keyboard(),
        )
    item = spots.get_spot(spot_id)
    if item:
        await _show_item(message, item, replace=False)
    else:
        await message.answer(_list_text(), parse_mode="HTML", reply_markup=_items_keyboard())


@router.message(IsAdmin(), SpotsAdmin.photo)
async def spot_add_photo_skip(message: types.Message, state: FSMContext):
    raw = (message.text or "").strip()
    if raw not in ("—", "-", "ні", "без фото", "skip"):
        await message.answer("Надішли фото або напиши «—».")
        return
    data = await state.get_data()
    name = data.get("name")
    address = data.get("address")
    maps_url = data.get("maps_url")
    if not name or not address:
        await state.clear()
        await message.answer("Сесію скинуто. Відкрий «📍 Точки» знову.")
        return
    spot_id = spots.add_spot(name=name, address=address, maps_url=maps_url)
    await state.clear()
    await message.answer(
        f"✅ Додано без фото: <b>{html.escape(str(name))}</b>",
        parse_mode="HTML",
        reply_markup=admin_keyboard(),
    )
    item = spots.get_spot(spot_id)
    if item:
        await _show_item(message, item, replace=False)


@router.callback_query(IsAdmin(), F.data.startswith("spot_item:"))
async def spot_item_view(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    item_id = int(callback.data.split(":")[-1])
    item = spots.get_spot(item_id)
    if not item:
        await callback.answer("Не знайдено", show_alert=True)
        return
    await _show_item(callback.message, item)
    await callback.answer()


@router.callback_query(IsAdmin(), F.data.startswith("spot_edit_name:"))
async def spot_edit_name_start(callback: types.CallbackQuery, state: FSMContext):
    item_id = int(callback.data.split(":")[-1])
    item = spots.get_spot(item_id)
    if not item:
        await callback.answer("Не знайдено", show_alert=True)
        return
    await state.set_state(SpotsAdmin.edit_name)
    await state.update_data(edit_item_id=item_id)
    await callback.message.answer(
        f"Поточна назва: <b>{html.escape(str(item['name']))}</b>\n\n"
        "Введи <b>нову назву</b> (2–120 символів).\n"
        "Або /cancel щоб скасувати.",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(IsAdmin(), SpotsAdmin.edit_name, F.text == "/cancel")
@router.message(IsAdmin(), SpotsAdmin.edit_address, F.text == "/cancel")
@router.message(IsAdmin(), SpotsAdmin.edit_maps, F.text == "/cancel")
@router.message(IsAdmin(), SpotsAdmin.edit_photo, F.text == "/cancel")
@router.message(IsAdmin(), SpotsAdmin.edit_sort, F.text == "/cancel")
async def spot_edit_cancel(message: types.Message, state: FSMContext):
    data = await state.get_data()
    item_id = data.get("edit_item_id")
    await state.clear()
    item = spots.get_spot(int(item_id)) if item_id else None
    await message.answer("Скасовано.")
    if item:
        await _show_item(message, item, replace=False)


@router.message(IsAdmin(), SpotsAdmin.edit_name)
async def spot_edit_name_save(message: types.Message, state: FSMContext):
    data = await state.get_data()
    item_id = data.get("edit_item_id")
    name = (message.text or "").strip()
    if not item_id:
        await state.clear()
        await message.answer("Сесію скинуто.")
        return
    if len(name) < 2 or len(name) > 120:
        await message.answer("Назва: від 2 до 120 символів.")
        return
    spots.set_name(int(item_id), name)
    await state.clear()
    item = spots.get_spot(int(item_id))
    await message.answer("✅ Назву оновлено.")
    if item:
        await _show_item(message, item, replace=False)


@router.callback_query(IsAdmin(), F.data.startswith("spot_edit_address:"))
async def spot_edit_address_start(callback: types.CallbackQuery, state: FSMContext):
    item_id = int(callback.data.split(":")[-1])
    item = spots.get_spot(item_id)
    if not item:
        await callback.answer("Не знайдено", show_alert=True)
        return
    await state.set_state(SpotsAdmin.edit_address)
    await state.update_data(edit_item_id=item_id)
    await callback.message.answer(
        f"Поточна адреса: <b>{html.escape(str(item.get('address') or ''))}</b>\n\n"
        "Введи <b>нову адресу</b> (2–200 символів).\n"
        "Або /cancel щоб скасувати.",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(IsAdmin(), SpotsAdmin.edit_address)
async def spot_edit_address_save(message: types.Message, state: FSMContext):
    data = await state.get_data()
    item_id = data.get("edit_item_id")
    address = (message.text or "").strip()
    if not item_id:
        await state.clear()
        await message.answer("Сесію скинуто.")
        return
    if len(address) < 2 or len(address) > 200:
        await message.answer("Адреса: від 2 до 200 символів.")
        return
    spots.set_address(int(item_id), address)
    await state.clear()
    item = spots.get_spot(int(item_id))
    await message.answer("✅ Адресу оновлено.")
    if item:
        await _show_item(message, item, replace=False)


@router.callback_query(IsAdmin(), F.data.startswith("spot_edit_maps:"))
async def spot_edit_maps_start(callback: types.CallbackQuery, state: FSMContext):
    item_id = int(callback.data.split(":")[-1])
    item = spots.get_spot(item_id)
    if not item:
        await callback.answer("Не знайдено", show_alert=True)
        return
    await state.set_state(SpotsAdmin.edit_maps)
    await state.update_data(edit_item_id=item_id)
    current = item.get("maps_url") or "—"
    await callback.message.answer(
        f"Поточне посилання:\n<code>{html.escape(str(current))}</code>\n\n"
        "Надішли нове <b>посилання на Google Maps</b>.\n"
        "Або <code>—</code>, щоб прибрати.\n"
        "Або /cancel щоб скасувати.",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(IsAdmin(), SpotsAdmin.edit_maps)
async def spot_edit_maps_save(message: types.Message, state: FSMContext):
    data = await state.get_data()
    item_id = data.get("edit_item_id")
    if not item_id:
        await state.clear()
        await message.answer("Сесію скинуто.")
        return
    raw = (message.text or "").strip()
    if raw in ("—", "-", "ні", "skip"):
        maps_url = None
    elif raw.startswith("http://") or raw.startswith("https://"):
        if len(raw) > 500:
            await message.answer("Посилання занадто довге (макс. 500).")
            return
        maps_url = raw
    else:
        await message.answer(
            "Потрібне посилання http(s)://… або «—» щоб прибрати."
        )
        return
    spots.set_maps_url(int(item_id), maps_url)
    await state.clear()
    item = spots.get_spot(int(item_id))
    await message.answer("✅ Посилання оновлено.")
    if item:
        await _show_item(message, item, replace=False)


@router.callback_query(IsAdmin(), F.data.startswith("spot_edit_sort:"))
async def spot_edit_sort_start(callback: types.CallbackQuery, state: FSMContext):
    item_id = int(callback.data.split(":")[-1])
    item = spots.get_spot(item_id)
    if not item:
        await callback.answer("Не знайдено", show_alert=True)
        return
    await state.set_state(SpotsAdmin.edit_sort)
    await state.update_data(edit_item_id=item_id)
    await callback.message.answer(
        f"Поточний порядок: <b>{int(item.get('sort_order') or 0)}</b>\n\n"
        "Введи ціле число (менше = вище в списку).\n"
        "Або /cancel щоб скасувати.",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(IsAdmin(), SpotsAdmin.edit_sort)
async def spot_edit_sort_save(message: types.Message, state: FSMContext):
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
    spots.set_sort_order(int(item_id), sort_order)
    await state.clear()
    item = spots.get_spot(int(item_id))
    await message.answer("✅ Порядок оновлено.")
    if item:
        await _show_item(message, item, replace=False)


@router.callback_query(IsAdmin(), F.data.startswith("spot_edit_photo:"))
async def spot_edit_photo_start(callback: types.CallbackQuery, state: FSMContext):
    item_id = int(callback.data.split(":")[-1])
    item = spots.get_spot(item_id)
    if not item:
        await callback.answer("Не знайдено", show_alert=True)
        return
    await state.set_state(SpotsAdmin.edit_photo)
    await state.update_data(edit_item_id=item_id)
    await callback.message.answer(
        "Надішли <b>нове фото</b> одним зображенням.\n"
        "Або /cancel щоб скасувати.",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(IsAdmin(), SpotsAdmin.edit_photo, F.photo)
async def spot_edit_photo_save(message: types.Message, state: FSMContext):
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
    item = spots.get_spot(int(item_id))
    await message.answer("✅ Фото оновлено.")
    if item:
        await _show_item(message, item, replace=False)


@router.message(IsAdmin(), SpotsAdmin.edit_photo)
async def spot_edit_photo_need_image(message: types.Message):
    await message.answer("Надішли фото зображенням, або /cancel.")


@router.callback_query(IsAdmin(), F.data.startswith("spot_clear_photo:"))
async def spot_clear_photo(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    item_id = int(callback.data.split(":")[-1])
    item = spots.get_spot(item_id)
    if not item:
        await callback.answer("Не знайдено", show_alert=True)
        return
    spots.clear_photo(item_id)
    item = spots.get_spot(item_id)
    await callback.answer("Фото прибрано")
    if item:
        await _show_item(callback.message, item, replace=True)


@router.callback_query(IsAdmin(), F.data.startswith("spot_toggle:"))
async def spot_toggle(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    item_id = int(callback.data.split(":")[-1])
    item = spots.get_spot(item_id)
    if not item:
        await callback.answer("Не знайдено", show_alert=True)
        return
    spots.set_active(item_id, not bool(item.get("active")))
    item = spots.get_spot(item_id)
    await callback.answer("Оновлено")
    if item:
        await _show_item(callback.message, item, replace=bool(callback.message.photo))


@router.callback_query(IsAdmin(), F.data.startswith("spot_del:"))
async def spot_delete(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    item_id = int(callback.data.split(":")[-1])
    spots.delete_spot(item_id)
    await callback.answer("Видалено")
    await _show_list(callback.message, replace=bool(callback.message.photo))
