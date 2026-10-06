from aiogram import Router, types, F
from aiogram.exceptions import TelegramBadRequest
from utils.filters import IsAdmin
from aiogram.fsm.context import FSMContext
from keyboards.admin_keyboards import get_links_keyboard, cancel_button, admin_keyboard, get_link_stats_keyboard, get_delete_link_confirm_keyboard
from database_functions.links_db import get_link_by_id, update_link_name, delete_link, add_link, get_link_detailed_stats
from main import bot
from states.admin_states import LinkStates


router = Router()


@router.message(IsAdmin(), F.text == "Посилання")
async def manage_links(message: types.Message):
    await message.answer("Оберіть посилання для перегляду статистики або додайте нове:", 
                        reply_markup=get_links_keyboard())


@router.callback_query(IsAdmin(), F.data.startswith("link_stats_"))
async def show_link_stats(callback: types.CallbackQuery):
    link_id = int(callback.data.split("_")[2])
    link_data = get_link_by_id(link_id)
    me = await bot.get_me()
    if link_data:
        link_name, link_url = link_data
        bot_link = f"https://t.me/{me.username}?start=linktowatch_{link_id}"

        detailed_stats = get_link_detailed_stats()
        visits_count = 0
        
        for stat in detailed_stats:
            if stat[0] == link_id:  # stat[0] is id
                visits_count = stat[2]  # stat[2] is link_count (clicks)
                break
        
        try:
            await callback.message.edit_text(
                f"<b>📊 Статистика посилання:</b>\n"
                f"Назва: {link_name}\n"
                f"Посилання: <code>{bot_link}</code>\n\n"
                f"<b>📈 Метрики:</b>\n"
                f"• Переходів в бот: {visits_count}\n\n"
                f"Скопіюйте це посилання для розповсюдження",
                parse_mode="HTML",
                reply_markup=get_link_stats_keyboard(link_id)
            )
        except TelegramBadRequest:
            await callback.answer("✅ Статистика оновлена", show_alert=False)
            return
    await callback.answer()


@router.callback_query(IsAdmin(), F.data.startswith("edit_link_"))
async def edit_link_start(callback: types.CallbackQuery, state: FSMContext):
    link_id = int(callback.data.split("_")[2])
    await state.update_data(edit_link_id=link_id)
    await callback.message.answer("Введіть нову назву для посилання:", reply_markup=cancel_button())
    await state.set_state(LinkStates.waiting_for_edit_name)
    await callback.answer()


@router.message(IsAdmin(), LinkStates.waiting_for_edit_name)
async def process_edit_link(message: types.Message, state: FSMContext):
    if message.text == "Скасувати":
        await state.clear()
        await message.answer("Відміна", reply_markup=admin_keyboard())
        await manage_links(message)
        return
    
    data = await state.get_data()
    link_id = data['edit_link_id']
    new_name = message.text
    
    update_link_name(link_id, new_name)

    await message.answer(
        "✅ Назву посилання успішно змінено!\n\n",
        reply_markup=admin_keyboard()
    )

    await message.answer(
        "Оберіть посилання для перегляду статистики або додайте нове:",
        reply_markup=get_links_keyboard()
    )
    await state.clear()


@router.callback_query(IsAdmin(), F.data.startswith("delete_link_"))
async def delete_link_confirm(callback: types.CallbackQuery):
    link_id = int(callback.data.split("_")[2])
    await callback.message.edit_text(
        "❗️ Ви впевнені, що хочете видалити це посилання?\n"
        "Цю дію неможливо відмінити.",
        reply_markup=get_delete_link_confirm_keyboard(link_id)
    )
    await callback.answer()


@router.callback_query(IsAdmin(), F.data.startswith("confirm_delete_"))
async def delete_link_process(callback: types.CallbackQuery):
    link_id = int(callback.data.split("_")[2])
    delete_link(link_id)
    
    await callback.message.edit_text(
        "✅ Посилання успішно видалено!\n\n"
        "Оберіть посилання для перегляду статистики або додайте нове:",
        reply_markup=get_links_keyboard()
    )
    await callback.answer()


@router.callback_query(IsAdmin(), F.data == "back_to_links")
async def back_to_links(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "Оберіть посилання для перегляду статистики або додайте нове:",
        reply_markup=get_links_keyboard()
    )
    await callback.answer()


@router.callback_query(IsAdmin(), F.data == "add_link")
async def start_add_link(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Введіть назву для нового посилання:", reply_markup=cancel_button())
    await state.set_state(LinkStates.waiting_for_name)
    await callback.answer()


@router.message(IsAdmin(), LinkStates.waiting_for_name)
async def process_link_name(message: types.Message, state: FSMContext):
    if message.text == "Скасувати":
        await state.clear()
        await message.answer("Відміна", reply_markup=admin_keyboard())
        await manage_links(message)
        return
    
    link_name = message.text
    me = await bot.get_me()

    
    link_id = add_link(link_name)
    bot_link = f"https://t.me/{me.username}?start=linktowatch_{link_id}"

    await message.answer(
        f"✅ Посилання успішно створено!\n\n",
        reply_markup=admin_keyboard()
    )
    
    await message.answer(
        f"Назва: {link_name}\n"
        f"Посилання: {bot_link}\n\n"
        f"Скопіюйте це посилання для розповсюдження\n\n"
        f"Оберіть посилання для перегляду статистики або додайте нове:",
        reply_markup=get_links_keyboard()
    )
    await state.clear()