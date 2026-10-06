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
    get_referral_review_keyboard,
)
from Content.texts import get_greeting_message
from utils.admin_functions import generate_database_export, format_statistics_message
from database_functions.settings_db import (
    REWARD_SETTING_KEYS,
    get_cashback_percent,
    rewards_snapshot,
    set_cashback_percent,
    set_reward_uah,
    set_welcome_bonus_uah,
)
from states.admin_states import LoyaltySettings
from datetime import datetime
import os


router = Router()

_REWARD_LABELS = {
    "welcome_bonus_uah": "Вітальний бонус",
    "birthday_bonus_uah": "Бонус за дату народження",
    "annual_birthday_bonus_uah": "Щорічний подарунок на ДН",
    "referral_bonus_uah": "Реферал (за друга)",
    "quest_visits_reward_uah": "Квест: 3 візити",
    "quest_combo_reward_uah": "Квест: напій + їжа",
    "quest_drinks_reward_uah": "Квест: 2 різні напої",
    "ach_days_5_reward_uah": "Досягнення: 5 днів",
    "ach_days_15_reward_uah": "Досягнення: 15 днів",
    "ach_days_30_reward_uah": "Досягнення: 30 днів",
}


def _loyalty_text() -> str:
    s = rewards_snapshot()
    return (
        "🎁 <b>Налаштування лояльності</b>\n\n"
        f"☕ Вітальний бонус: <b>{s['welcome_bonus_uah']:g} грн</b>\n"
        f"🎂 За дату народження: <b>{s['birthday_bonus_uah']:g} грн</b>\n"
        f"🎁 Щорічно на ДН: <b>{s['annual_birthday_bonus_uah']:g} грн</b>\n"
        f"👥 Реферал: <b>{s['referral_bonus_uah']:g} грн</b>\n"
        f"📈 Кешбек (базовий / рівні): <b>{s['cashback_percent']:g}%</b>\n\n"
        "<b>Квести</b>\n"
        f"• 3 візити: <b>{s['quest_visits_reward_uah']:g} грн</b>\n"
        f"• Напій + їжа: <b>{s['quest_combo_reward_uah']:g} грн</b>\n"
        f"• 2 різні напої: <b>{s['quest_drinks_reward_uah']:g} грн</b>\n\n"
        "<b>Досягнення (дні)</b>\n"
        f"• 5 днів: <b>{s['ach_days_5_reward_uah']:g} грн</b>\n"
        f"• 15 днів: <b>{s['ach_days_15_reward_uah']:g} грн</b>\n"
        f"• 30 днів: <b>{s['ach_days_30_reward_uah']:g} грн</b>\n\n"
        f"Вікно квестів: <b>{int(s['quest_window_days'])} днів</b> від реєстрації.\n"
        "Кешбек і прогрес квестів — при закритті чека в Poster."
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


@router.callback_query(IsAdmin(), F.data.startswith("loyalty_edit:"))
async def loyalty_edit_reward(callback: types.CallbackQuery, state: FSMContext):
    key = (callback.data or "").split(":", 1)[-1]
    if key not in REWARD_SETTING_KEYS:
        await callback.answer("Невідоме поле", show_alert=True)
        return
    snap = rewards_snapshot()
    label = _REWARD_LABELS.get(key, key)
    await state.set_state(LoyaltySettings.edit_reward)
    await state.update_data(reward_key=key)
    await callback.message.answer(
        f"Введи нову суму для <b>{label}</b> у гривнях "
        f"(зараз <b>{snap.get(key, 0):g}</b>).\n"
        "Наприклад: <code>15</code>",
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


@router.message(IsAdmin(), LoyaltySettings.edit_reward)
async def loyalty_save_reward(message: types.Message, state: FSMContext):
    data = await state.get_data()
    key = data.get("reward_key")
    if key not in REWARD_SETTING_KEYS:
        await state.clear()
        await message.answer("Сесію скинуто. Відкрий «🎁 Лояльність» знову.")
        return
    raw = (message.text or "").replace(",", ".").strip()
    try:
        value = float(raw)
        if value < 0 or value > 10000:
            raise ValueError
    except ValueError:
        await message.answer("Введи число від 0 до 10000.")
        return
    if key == "welcome_bonus_uah":
        set_welcome_bonus_uah(value)
    else:
        set_reward_uah(key, value)
    label = _REWARD_LABELS.get(key, key)
    await state.clear()
    await message.answer(
        f"✅ {label}: <b>{value:g} грн</b>",
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


def _referral_review_text(items: list) -> str:
    if not items:
        return "👥 <b>Реферали на перевірці</b>\n\nЧерга порожня."
    lines = [
        "👥 <b>Реферали на перевірці</b>",
        "З 6-го успішного запрошення за день — ручне підтвердження адміністратором.",
        "",
    ]
    for ref in items[:20]:
        lines.append(
            f"• #{ref.get('id')}: друг <code>{ref.get('friend_user_id')}</code> ← "
            f"<code>{ref.get('referrer_user_id')}</code> · "
            f"{float(ref.get('amount_uah') or 0):g} грн · чек {ref.get('qualifying_tx_id') or '—'}"
        )
    return "\n".join(lines)


@router.message(IsAdmin(), F.text == "👥 Реферали")
async def referral_review_menu(message: types.Message):
    from database_functions.referrals_db import list_owner_review

    items = list_owner_review()
    await message.answer(
        _referral_review_text(items),
        parse_mode="HTML",
        reply_markup=get_referral_review_keyboard(items),
    )


@router.callback_query(IsAdmin(), F.data == "referral_review_list")
async def referral_review_list(callback: types.CallbackQuery):
    from database_functions.referrals_db import list_owner_review

    items = list_owner_review()
    await callback.message.edit_text(
        _referral_review_text(items),
        parse_mode="HTML",
        reply_markup=get_referral_review_keyboard(items),
    )
    await callback.answer()


@router.callback_query(IsAdmin(), F.data.startswith("referral_approve:"))
async def referral_approve(callback: types.CallbackQuery):
    from services.referrals import approve_owner_review
    from database_functions.referrals_db import list_owner_review

    try:
        rid = int((callback.data or "").split(":")[-1])
    except ValueError:
        await callback.answer("Невірний id", show_alert=True)
        return
    result = approve_owner_review(rid)
    if result.get("status") != "ok":
        await callback.answer("Вже оброблено або не знайдено", show_alert=True)
    else:
        await callback.answer(
            f"Ок · нарахування {result.get('available_at')}",
            show_alert=True,
        )
    items = list_owner_review()
    try:
        await callback.message.edit_text(
            _referral_review_text(items),
            parse_mode="HTML",
            reply_markup=get_referral_review_keyboard(items),
        )
    except Exception:
        pass


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
