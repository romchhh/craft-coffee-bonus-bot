"""Admin reply-keyboard labels — used to reset FSM when switching sections."""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, TelegramObject

# Exact texts from admin_keyboard() (+ aliases)
ADMIN_MENU_TEXTS: frozenset[str] = frozenset(
    {
        "Розсилка",
        "Статистика",
        "👤 Клієнти",
        "📒 Журнал Крафтиків",
        "👥 Реферали",
        "Адміністратори",
        "Посилання",
        "🎁 Лояльність",
        "💬 Контакт підтримки",
        "🍽 Меню",
        "📍 Точки",
        "Головне меню",
        "👨‍💻 Адмін панель",
        "Адмін панель 💻",
        "/admin",
    }
)


class ClearStateOnAdminMenuMiddleware(BaseMiddleware):
    """Leaving an FSM prompt (e.g. «Введи відсоток») when admin taps another menu item."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message):
            text = (event.text or "").strip()
            if text in ADMIN_MENU_TEXTS:
                state: FSMContext | None = data.get("state")
                if state is not None:
                    await state.clear()
        return await handler(event, data)
