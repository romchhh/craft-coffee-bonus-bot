from aiogram import Router, types, F
from main import bot
from utils.filters import IsAdmin
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from keyboards.admin_keyboards import get_broadcast_keyboard, create_post, publish_post, post_keyboard, back_mailing_keyboard, confirm_mailing
from utils.admin_functions import parse_url_buttons, format_message_text
from Content.texts import mailing_text
from database_functions.admin_db import get_all_user_ids
from states.admin_states import Mailing
import asyncio


router = Router()


user_data = {}


def initialize_user_data(user_id: str):
    if user_id not in user_data:
        user_data[user_id] = {}


      
@router.message(IsAdmin(), F.text == "Розсилка")
async def create_mailing(message: types.Message):
    user_id = message.from_user.id
    description = mailing_text
    await message.answer(description, parse_mode='HTML', reply_markup=get_broadcast_keyboard())
    
 

@router.callback_query(IsAdmin(), F.data =="create_post")
async def process_channel_selection(callback_query: CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    initialize_user_data(user_id)
    
    await state.set_state(Mailing.content)
    inline_kb_list = [
        [InlineKeyboardButton(text="Назад", callback_data="back_to_posts")]
    ]
    reply_markup = InlineKeyboardMarkup(inline_keyboard=inline_kb_list)

    await callback_query.message.edit_text(
        "Будь ласка, надішліть те, що ви хочете розіслати користувачам:",
        parse_mode='HTML',
        reply_markup=reply_markup
    )
    
@router.message(Mailing.content)
async def handle_content(message: types.Message, state: FSMContext):
    user_id = message.from_user.id

    content_type = message.content_type
    content_info = ""
    media_info = None
    media_type = None
    html_content = None 

    if content_type == 'text':
        html_content = format_message_text(message)
        print(html_content)
        await message.answer(html_content, parse_mode='HTML', reply_markup=create_post(user_data, user_id, user_data[user_id].get('url_buttons')))
        media_type = None
    elif content_type == 'photo':
        media_info = message.photo[-1].file_id
        html_content = format_message_text(message)
        await message.answer_photo(
            media_info,
            caption=html_content or None,
            parse_mode='HTML' if html_content else None,
            reply_markup=create_post(user_data, user_id, user_data[user_id].get('url_buttons'))
        )
        media_type = 'photo'
    elif content_type == 'video':
        media_info = message.video.file_id
        html_content = format_message_text(message)
        await message.answer_video(
            media_info,
            caption=html_content or None,
            parse_mode='HTML' if html_content else None,
            reply_markup=create_post(user_data, user_id, user_data[user_id].get('url_buttons'))
        )
        media_type = 'video'
    elif content_type == 'document':
        media_info = message.document.file_id
        html_content = format_message_text(message)
        await message.answer_document(
            media_info,
            caption=html_content or None,
            parse_mode='HTML' if html_content else None,
            reply_markup=create_post(user_data, user_id, user_data[user_id].get('url_buttons'))
        )
        media_type = 'document'
    else:
        await message.answer("Невідомий формат.")
    if html_content:
        user_data[user_id]['content'] = html_content
        await state.update_data(content=html_content)

    user_data[user_id]['media'] = media_info
    user_data[user_id]['media_type'] = media_type

    await state.clear()

    
@router.callback_query(F.data.startswith('media_'))
async def handle_media(callback_query: types.CallbackQuery, state: FSMContext):
    await state.set_state(Mailing.media)
    await callback_query.message.answer(
        "Будь ласка, надішліть медіа, яке ви хочете додати або змінити:",
        reply_markup=back_mailing_keyboard())

@router.message(Mailing.media)
async def handle_media_content(message: types.Message, state: FSMContext):
    user_id = message.from_user.id

    media_info = None
    media_type = None
    if message.content_type == 'photo':
        media_info = message.photo[-1].file_id
        media_type = 'photo'
    elif message.content_type == 'video':
        media_info = message.video.file_id
        media_type = 'video'
    elif message.content_type == 'document':
        media_info = message.document.file_id
        media_type = 'document'

    user_data[user_id]['media'] = media_info
    user_data[user_id]['media_type'] = media_type

    content_info = user_data[user_id].get('content')

    if media_info:
        if media_type == 'photo':
            await message.answer_photo(media_info, caption=f"{content_info}", parse_mode='HTML', reply_markup=create_post(user_data, user_id, user_data[user_id].get('url_buttons')))
        elif media_type == 'video':
            await message.answer_video(media_info, caption=f"{content_info}", parse_mode='HTML', reply_markup=create_post(user_data, user_id, user_data[user_id].get('url_buttons')))
        elif media_type == 'document':
            await message.answer_document(media_info, caption=f"{content_info}", parse_mode='HTML', reply_markup=create_post(user_data, user_id, user_data[user_id].get('url_buttons')))
    else:
        await message.answer(f"{content_info}", parse_mode='HTML', reply_markup=create_post(user_data, user_id, user_data[user_id].get('url_buttons')))

    await state.clear()


@router.callback_query(F.data.startswith('description_'))
async def handle_description(callback_query: types.CallbackQuery, state: FSMContext):
    await state.set_state(Mailing.description)
    await callback_query.message.answer(
        "Будь ласка, надішліть опис, який ви хочете додати або змінити:",
        reply_markup=back_mailing_keyboard())


@router.message(Mailing.description)
async def handle_description_content(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    media_info = user_data[user_id].get('media')
    media_type = user_data[user_id].get('media_type')
    
    formatted_content = format_message_text(message)

    user_data[user_id]['content'] = formatted_content

    if media_info:
        if media_type == 'photo':
            await message.answer_photo(media_info, caption=formatted_content, parse_mode='HTML', reply_markup=create_post(user_data, user_id, user_data[user_id].get('url_buttons')))
        elif media_type == 'video':
            await message.answer_video(media_info, caption=formatted_content, parse_mode='HTML', reply_markup=create_post(user_data, user_id, user_data[user_id].get('url_buttons')))
        elif media_type == 'document':
            await message.answer_document(media_info, caption=formatted_content, parse_mode='HTML', reply_markup=create_post(user_data, user_id, user_data[user_id].get('url_buttons')))
    else:
        await message.answer(formatted_content, parse_mode='HTML', reply_markup=create_post(user_data, user_id, user_data[user_id].get('url_buttons')))

    await state.clear()


@router.callback_query(F.data.startswith('url_buttons_'))
async def handle_url_buttons(callback_query: types.CallbackQuery, state: FSMContext):
    await state.set_state(Mailing.url_buttons)
    await callback_query.message.answer(
        "<b>URL-КНОПКИ</b>\n\n"
        "Будь ласка, надішліть список URL-кнопок у форматі:\n\n"
        "<code>Кнопка 1 - http://link.com\n"
        "Кнопка 2 - http://link.com</code>\n\n"
        "Використовуйте роздільник <code>' | '</code>, щоб додати до 8 кнопок в один ряд (допустимо 15 рядів):\n\n"
        "<code>Кнопка 1 - http://link.com | Кнопка 2 - http://link.com</code>\n\n",
        parse_mode='HTML',
        reply_markup=back_mailing_keyboard(),
        disable_web_page_preview=True)


@router.message(Mailing.url_buttons)
async def handle_url_buttons_content(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    media_info = user_data[user_id].get('media')
    media_type = user_data[user_id].get('media_type')
    content_info = user_data[user_id].get('content')

    url_buttons_text = message.text
    url_buttons = parse_url_buttons(url_buttons_text)

    user_data[user_id]['url_buttons'] = url_buttons

    if media_info:
        if media_type == 'photo':
            await message.answer_photo(media_info, caption=f"{content_info}", parse_mode='HTML', reply_markup=create_post(user_data, user_id, url_buttons))
        elif media_type == 'video':
            await message.answer_video(media_info, caption=f"{content_info}", parse_mode='HTML', reply_markup=create_post(user_data, user_id, url_buttons))
        elif media_type == 'document':
            await message.answer_document(media_info, caption=f"{content_info}", parse_mode='HTML', reply_markup=create_post(user_data, user_id, url_buttons))
    else:
        await message.answer(f"{content_info}", parse_mode='HTML', reply_markup=create_post(user_data, user_id, url_buttons))

    await state.clear()


@router.callback_query(F.data.startswith('bell_'))
async def handle_comments(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    if 'bell' not in user_data[user_id]:
        user_data[user_id]['bell'] = 0  
    user_data[user_id]['bell'] = 1 if user_data[user_id]['bell'] == 0 else 0
    await callback_query.message.edit_reply_markup(reply_markup=create_post(user_data, user_id, user_data[user_id].get('url_buttons')))

    
@router.callback_query(F.data.startswith('nextmailing_'))
async def handle_url_buttons(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    
    await callback_query.message.answer("<b>💼 НАЛАШТУВАННЯ ВІДПРАВКИ</b>\n\n"
                                           f"Пост готовий до розсилки.", parse_mode='HTML', reply_markup=publish_post())
    
    
@router.callback_query(F.data.startswith('publish_'))
async def confirm_publish(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.message.edit_text("Ви впевнені, що хочете зробити розсилку?", reply_markup=confirm_mailing())


@router.callback_query(F.data.startswith('confirm_publish_'))
async def handle_publish_confirmation(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    await callback_query.message.edit_text("Починаю розсилку...", reply_markup=None)
    initialize_user_data(user_id)

    media_info = user_data[user_id].get('media')
    media_type = user_data[user_id].get('media_type')
    content_info = user_data[user_id].get('content')
    url_buttons = user_data[user_id].get('url_buttons')

    bell = user_data[user_id].get('bell', 0) 
    disable_notification = (bell == 0)
    user_ids = get_all_user_ids()

    sent_count = 0
    for recipient_id in user_ids: 
        try:
            if media_info:
                if media_type == 'photo':
                    await bot.send_photo(recipient_id, media_info, caption=content_info, parse_mode='HTML', reply_markup=post_keyboard(user_data, user_id, url_buttons), disable_notification=disable_notification)
                elif media_type == 'video':
                    await bot.send_video(recipient_id, media_info, caption=content_info, parse_mode='HTML', reply_markup=post_keyboard(user_data, user_id, url_buttons), disable_notification=disable_notification)
                elif media_type == 'document':
                    await bot.send_document(recipient_id, media_info, caption=content_info, parse_mode='HTML', reply_markup=post_keyboard(user_data, user_id, url_buttons), disable_notification=disable_notification)
            else:
                await bot.send_message(recipient_id, content_info, parse_mode='HTML', reply_markup=post_keyboard(user_data, user_id, url_buttons), disable_notification=disable_notification)
            sent_count += 1
        except Exception as e:
            print(f"Failed to send message to user {recipient_id}: {e}")
        await asyncio.sleep(2)

    await callback_query.message.answer(f"Пост опубліковано для {sent_count} користувачів!")


@router.callback_query(F.data == "back_to",)
async def process_channel_info(callback_query: types.CallbackQuery):
    await callback_query.message.delete()
    
@router.callback_query(IsAdmin(), F.data == "back_to_my_post", StateFilter(Mailing.content, Mailing.media, Mailing.description, Mailing.url_buttons))
async def process_channel_info(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.message.delete()
    await state.clear()

@router.callback_query(IsAdmin(), F.data == "back_to_posts", Mailing.content)
async def process_channel_info(callback_query: types.CallbackQuery, state: FSMContext):
    await state.clear()
    description = mailing_text
    await callback_query.message.edit_text(description, parse_mode='HTML', reply_markup=get_broadcast_keyboard())

    
@router.callback_query(F.data == 'cancel_publish')
async def cancel_publish(callback_query: types.CallbackQuery):
    await callback_query.answer("Публікацію скасовано.", show_alert=True)