from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
    MenuButtonWebApp,
    MenuButtonCommands,
)
from database_functions.admin_db import get_all_administrators
from config import WEBAPP_URL


def get_phone_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Поділитися номером", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def get_birthday_keyboard():
    rows = []
    if WEBAPP_URL:
        rows.append([
            KeyboardButton(
                text="📅 Обрати дату",
                web_app=WebAppInfo(url=f"{WEBAPP_URL}/birthday"),
            )
        ])
    rows.append([KeyboardButton(text="Пропустити")])
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def get_start_keyboard(user_id: int, registered: bool | None = None):
    if registered is None:
        try:
            from database_functions.client_db import is_registered
            registered = is_registered(user_id)
        except Exception:
            registered = False

    all_admins = get_all_administrators()

    if not registered:
        keyboard = [[KeyboardButton(text="✅ Оформити картку")]]
        if user_id in all_admins:
            keyboard.append([KeyboardButton(text="👨‍💻 Адмін панель")])
        return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

    keyboard = [
        [KeyboardButton(text="🪪 Моя картка")],
        [KeyboardButton(text="☕ Про Craft Coffee"), KeyboardButton(text="🎁 Бонуси")],
        [KeyboardButton(text="💬 Підтримка")],
    ]
    if user_id in all_admins:
        keyboard.append([KeyboardButton(text="👨‍💻 Адмін панель")])

    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_open_card_inline():
    if not WEBAPP_URL:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🪪 Відкрити картку", web_app=WebAppInfo(url=WEBAPP_URL))]
        ]
    )


def get_manager_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Написати", url="https://t.me/manager")]]
    )


def get_about_keyboard():
    from Content.locations import INSTAGRAM_URL

    rows = []
    if INSTAGRAM_URL:
        rows.append([InlineKeyboardButton(text="📸 Instagram", url=INSTAGRAM_URL)])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def get_socials_keyboard():
    return get_about_keyboard() or InlineKeyboardMarkup(inline_keyboard=[])


async def set_webapp_menu(bot):
    """Кнопка меню зліва в чаті відкриває Mini App."""
    if WEBAPP_URL:
        url = WEBAPP_URL.rstrip("/")
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(text="Картка", web_app=WebAppInfo(url=url))
        )
    else:
        await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
