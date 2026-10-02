from aiogram import F, Router, types
from aiogram.types import FSInputFile
from main import bot
from utils.filters import IsAdmin
from aiogram.fsm.context import FSMContext
from keyboards.client_keyboards import get_start_keyboard
from keyboards.admin_keyboards import (
    admin_keyboard,
    get_export_database_keyboard,
    get_loyalty_settings_keyboard,
)
from Content.texts import get_greeting_message
from utils.admin_functions import generate_database_export, format_statistics_message
from database_functions.settings_db import (
    get_welcome_bonus_uah,
    get_cashback_percent,
    set_welcome_bonus_uah,
    set_cashback_percent,
)
from states.admin_states import LoyaltySettings
from datetime import datetime
import os


router = Router()


def _loyalty_text() -> str:
    welcome = get_welcome_bonus_uah()
    cashback = get_cashback_percent()
    return (
        "🎁 <b>Налаштування лояльності</b>\n\n"
        f"☕ Вітальний бонус: <b>{welcome:g} грн</b>\n"
        f"📈 Кешбек з покупки: <b>{cashback:g}%</b>\n\n"
        "Кешбек нараховується автоматично при закритті чека з клієнтом у Poster."
    )


@router.message(IsAdmin(), F.text.in_(["👨‍💻 Адмін панель", "Адмін панель 💻", "/admin"]))
async def admin_panel(message: types.Message):
    await message.answer("Вітаю в адмін панелі. Ось ваші доступні опції.", reply_markup=admin_keyboard())


@router.message(IsAdmin(), F.text.in_(["Головне меню"]))
async def my_parcel(message: types.Message, state: FSMContext):
    user = message.from_user
    user_id = message.from_user.id
    from database_functions.client_db import is_registered
    keyboard = get_start_keyboard(user_id, registered=is_registered(user_id))
    greeting_message = get_greeting_message(user.first_name)
    await message.answer(greeting_message, reply_markup=keyboard, parse_mode="HTML")


@router.message(IsAdmin(), F.text.in_(["Статистика"]))
async def statistic_handler(message: types.Message):
    response_message = format_statistics_message()
    await message.answer(response_message, parse_mode="HTML", reply_markup=get_export_database_keyboard())


@router.message(IsAdmin(), F.text == "🎁 Лояльність")
async def loyalty_settings(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        _loyalty_text(),
        parse_mode="HTML",
        reply_markup=get_loyalty_settings_keyboard(),
    )


@router.callback_query(IsAdmin(), F.data == "loyalty_refresh")
async def loyalty_refresh(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        _loyalty_text(),
        parse_mode="HTML",
        reply_markup=get_loyalty_settings_keyboard(),
    )
    await callback.answer()


@router.callback_query(IsAdmin(), F.data == "loyalty_edit_welcome")
async def loyalty_edit_welcome(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(LoyaltySettings.welcome_bonus)
    await callback.message.answer(
        f"Введи новий вітальний бонус у гривнях (зараз {get_welcome_bonus_uah():g}).\n"
        "Наприклад: <code>50</code>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(IsAdmin(), F.data == "loyalty_edit_cashback")
async def loyalty_edit_cashback(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(LoyaltySettings.cashback_percent)
    await callback.message.answer(
        f"Введи відсоток кешбеку (зараз {get_cashback_percent():g}%).\n"
        "Наприклад: <code>5</code> або <code>7.5</code>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(IsAdmin(), LoyaltySettings.welcome_bonus)
async def loyalty_save_welcome(message: types.Message, state: FSMContext):
    raw = (message.text or "").replace(",", ".").strip()
    try:
        value = float(raw)
        if value < 0 or value > 10000:
            raise ValueError
    except ValueError:
        await message.answer("Введи число від 0 до 10000.")
        return
    set_welcome_bonus_uah(value)
    await state.clear()
    await message.answer(
        f"✅ Вітальний бонус збережено: <b>{value:g} грн</b>",
        parse_mode="HTML",
        reply_markup=admin_keyboard(),
    )
    await message.answer(_loyalty_text(), parse_mode="HTML", reply_markup=get_loyalty_settings_keyboard())


@router.message(IsAdmin(), LoyaltySettings.cashback_percent)
async def loyalty_save_cashback(message: types.Message, state: FSMContext):
    raw = (message.text or "").replace(",", ".").strip()
    try:
        value = float(raw)
        if value < 0 or value > 100:
            raise ValueError
    except ValueError:
        await message.answer("Введи відсоток від 0 до 100.")
        return
    set_cashback_percent(value)
    await state.clear()
    await message.answer(
        f"✅ Кешбек збережено: <b>{value:g}%</b>",
        parse_mode="HTML",
        reply_markup=admin_keyboard(),
    )
    await message.answer(_loyalty_text(), parse_mode="HTML", reply_markup=get_loyalty_settings_keyboard())


@router.callback_query(IsAdmin(), F.data == "export_database")
async def export_database(callback: types.CallbackQuery):
    response_message = (
        "<b>ВИГРУЗКА БАЗИ ДАНИХ</b>\n\n"
        "Зачекайте поки ми сформуємо ексель файл з базою даних"
    )
    await callback.message.answer(response_message, parse_mode="HTML")

    filename, users_count, links_count = generate_database_export()

    file = FSInputFile(filename)
    await bot.send_document(
        callback.message.chat.id,
        document=file,
        caption=(
            f"📊 База даних експортована\n\n"
            f"👥 Користувачів: {users_count}\n"
            f"🔗 Посилань: {links_count}\n"
            f"📅 Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        ),
    )

    if os.path.exists(filename):
        os.remove(filename)
