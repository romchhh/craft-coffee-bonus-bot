from aiogram.filters import Filter
from aiogram.types import Message, CallbackQuery
from aiogram.enums.chat_type import ChatType
from database_functions.admin_db import get_all_admin_ids, is_superadmin


class IsPrivate(Filter):
    async def __call__(self, message: Message) -> bool:
        return message.chat.type == ChatType.PRIVATE


class IsAdmin(Filter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user_id = event.from_user.id
        return user_id in get_all_admin_ids()


class IsSuperAdmin(Filter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user_id = event.from_user.id
        return is_superadmin(user_id)

