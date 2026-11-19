from aiogram import Router, types, F
from main import bot
from utils.filters import IsAdmin
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from keyboards.admin_keyboards import (
    get_broadcast_keyboard,
    create_post,
    publish_post,
    post_keyboard,
    back_mailing_keyboard,
    confirm_mailing,
    get_mailing_audience_keyboard,
    mailing_job_history_keyboard,
    quests_admin_keyboard,
    quest_campaign_actions_keyboard,
)
from utils.admin_functions import parse_url_buttons, parse_track_buttons, format_message_text
from Content.texts import mailing_text
from database_functions.client_db import count_mailing_opted_out, get_mailing_recipient_ids
from states.admin_states import Mailing
import asyncio


def _audience_from_user(uid) -> dict:
    data = user_data.get(uid) or {}
    return {
        "audience": data.get("audience") or "all",
        "audience_spots": list(data.get("audience_spots") or []),
        "audience_products": list(data.get("audience_products") or []),
        "audience_days_min": data.get("audience_days_min"),
        "audience_days_max": data.get("audience_days_max"),
    }


def _resolve_recipients(uid) -> tuple[list[int], str]:
    """Return (ids, human label for confirm screen)."""
    aud = _audience_from_user(uid)
    kind = aud["audience"]
    if kind == "test":
        ids = get_mailing_recipient_ids(audience="test")
        return ids, f"🧪 Тест (адміни) · {len(ids)}"
    if kind == "segment":
        ids = get_mailing_recipient_ids(
            audience="segment",
            spot_names=aud["audience_spots"] or None,
            product_qs=aud["audience_products"] or None,
            days_min=aud["audience_days_min"],
            days_max=aud["audience_days_max"],
        )
        bits = []
        if aud["audience_spots"]:
            bits.append("кавʼярні: " + ", ".join(aud["audience_spots"][:5]))
        if aud["audience_products"]:
            bits.append("товари: " + ", ".join(aud["audience_products"][:5]))
        if aud["audience_days_min"] is not None or aud["audience_days_max"] is not None:
            lo = aud["audience_days_min"] if aud["audience_days_min"] is not None else "…"
            hi = aud["audience_days_max"] if aud["audience_days_max"] is not None else "…"
            bits.append(f"у програмі {lo}–{hi} дн.")
        detail = " · ".join(bits) if bits else "без додаткових фільтрів"
        return ids, f"🎯 Сегмент · {len(ids)}\n{detail}"
    ids = get_mailing_recipient_ids(audience="all")
    return ids, f"Усім підписаним · {len(ids)}"


router = Router()
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


user_data = {}


def initialize_user_data(user_id: str):
    if user_id not in user_data:
        user_data[user_id] = {}


      
@router.message(IsAdmin(), F.text == "Розсилка")
async def create_mailing(message: types.Message, state: FSMContext):
    await state.clear()
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


@router.callback_query(F.data == "mailing_noop")
async def mailing_noop(callback_query: types.CallbackQuery):
    await callback_query.answer("Це превʼю кнопки — після відправки вона стане клікабельною")


@router.callback_query(F.data.startswith("track_buttons_"))
async def handle_track_buttons_start(callback_query: types.CallbackQuery, state: FSMContext):
    await state.set_state(Mailing.track_buttons)
    await callback_query.message.answer(
        "<b>📊 КНОПКИ-ОПИТУВАННЯ</b>\n\n"
        "Клієнти натискають варіант — ми рахуємо кліки (CTR розсилки).\n\n"
        "Формат — по одному варіанту в рядок, або кілька через <code> | </code>:\n\n"
        "<code>Лате | Американо | Капучино</code>\n\n"
        "Або з власним ключем:\n"
        "<code>Лате - latte\nАмерикано - americano</code>\n\n"
        "Надішли «−» щоб прибрати кнопки.",
        parse_mode="HTML",
        reply_markup=back_mailing_keyboard(),
    )
    await callback_query.answer()


@router.message(Mailing.track_buttons)
async def handle_track_buttons_content(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    initialize_user_data(user_id)
    raw = (message.text or "").strip()
    if raw in {"-", "−", "видалити", "очистити"}:
        user_data[user_id]["track_buttons"] = []
        track_rows = []
    else:
        track_rows = parse_track_buttons(raw)
        user_data[user_id]["track_buttons"] = track_rows

    media_info = user_data[user_id].get("media")
    media_type = user_data[user_id].get("media_type")
    content_info = user_data[user_id].get("content")
    kb = create_post(user_data, user_id, user_data[user_id].get("url_buttons"))
    if media_info:
        if media_type == "photo":
            await message.answer_photo(
                media_info, caption=content_info, parse_mode="HTML", reply_markup=kb
            )
        elif media_type == "video":
            await message.answer_video(
                media_info, caption=content_info, parse_mode="HTML", reply_markup=kb
            )
        elif media_type == "document":
            await message.answer_document(
                media_info, caption=content_info, parse_mode="HTML", reply_markup=kb
            )
    else:
        await message.answer(
            content_info or "Превʼю", parse_mode="HTML", reply_markup=kb
        )
    n = sum(len(r) for r in track_rows)
    await message.answer(f"Кнопок опитування: <b>{n}</b>", parse_mode="HTML")
    await state.clear()

    
@router.callback_query(F.data.startswith('nextmailing_'))
async def handle_next_mailing(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    initialize_user_data(user_id)
    if "audience" not in user_data[user_id]:
        user_data[user_id]["audience"] = "all"
    await state.set_state(Mailing.audience)
    aud = _audience_from_user(user_id)
    ids, label = _resolve_recipients(user_id)
    await callback_query.message.answer(
        "<b>👥 АУДИТОРІЯ РОЗСИЛКИ</b>\n\n"
        f"Зараз: {label}\n\n"
        "Обери кому слати — усім, тестовій групі (адміни) або сегменту "
        "(кавʼярня / напої / час у програмі).",
        parse_mode="HTML",
        reply_markup=get_mailing_audience_keyboard(aud),
    )
    await callback_query.answer()


@router.callback_query(F.data.startswith("mail_aud:"))
async def mail_aud_set(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    initialize_user_data(user_id)
    kind = (callback_query.data or "").split(":", 1)[-1]
    if kind not in {"all", "test", "segment"}:
        await callback_query.answer("Невідомо", show_alert=True)
        return
    user_data[user_id]["audience"] = kind
    ids, label = _resolve_recipients(user_id)
    await callback_query.message.edit_text(
        f"<b>👥 АУДИТОРІЯ</b>\n\nЗараз: {label}",
        parse_mode="HTML",
        reply_markup=get_mailing_audience_keyboard(_audience_from_user(user_id)),
    )
    await callback_query.answer(f"{len(ids)} отримувачів")


@router.callback_query(F.data == "mail_aud_clear")
async def mail_aud_clear(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    initialize_user_data(user_id)
    user_data[user_id]["audience_spots"] = []
    user_data[user_id]["audience_products"] = []
    user_data[user_id]["audience_days_min"] = None
    user_data[user_id]["audience_days_max"] = None
    user_data[user_id]["audience"] = "all"
    await callback_query.message.edit_reply_markup(
        reply_markup=get_mailing_audience_keyboard(_audience_from_user(user_id))
    )
    await callback_query.answer("Скинуто")


@router.callback_query(F.data == "mail_aud_spots")
async def mail_aud_spots(callback_query: types.CallbackQuery):
    from database_functions.clients_admin_db import list_visit_spots

    user_id = callback_query.from_user.id
    initialize_user_data(user_id)
    user_data[user_id]["audience"] = "segment"
    spots = list_visit_spots(limit=12)
    selected = set(user_data[user_id].get("audience_spots") or [])
    rows = []
    for i, name in enumerate(spots):
        mark = "✅ " if name in selected else ""
        label = (name[:36] + "…") if len(name) > 37 else name
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{mark}📍 {label}",
                    callback_data=f"mail_spot:{i}",
                )
            ]
        )
    user_data[user_id]["_mail_spot_choices"] = spots
    rows.append(
        [InlineKeyboardButton(text="✅ Готово", callback_data="mail_aud_back")]
    )
    await callback_query.message.edit_text(
        "📍 Обери кавʼярні (можна кілька — OR):\n"
        "<i>Клієнт купував хоча б в одній з обраних</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback_query.answer()


@router.callback_query(F.data.startswith("mail_spot:"))
async def mail_spot_toggle(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    initialize_user_data(user_id)
    choices = user_data[user_id].get("_mail_spot_choices") or []
    try:
        idx = int((callback_query.data or "").split(":")[-1])
        name = choices[idx]
    except (ValueError, IndexError):
        await callback_query.answer("Застаріло", show_alert=True)
        return
    selected = list(user_data[user_id].get("audience_spots") or [])
    if name in selected:
        selected = [s for s in selected if s != name]
    else:
        selected.append(name)
    user_data[user_id]["audience_spots"] = selected
    user_data[user_id]["audience"] = "segment"
    # refresh
    callback_query.data = "mail_aud_spots"
    await mail_aud_spots(callback_query)


@router.callback_query(F.data == "mail_aud_products")
async def mail_aud_products(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    initialize_user_data(user_id)
    user_data[user_id]["audience"] = "segment"
    await state.set_state(Mailing.audience_products)
    cur = user_data[user_id].get("audience_products") or []
    cur_s = ", ".join(cur) if cur else "—"
    await callback_query.message.answer(
        "☕ Надішли назви напоїв / десертів через кому або з нового рядка.\n"
        "Клієнт мав <b>кожен</b> із товарів хоча б раз.\n\n"
        f"Зараз: <code>{cur_s}</code>\n\n"
        "Приклад: <code>Лате, Тірамісу</code>\n"
        "«−» — очистити.",
        parse_mode="HTML",
        reply_markup=back_mailing_keyboard(),
    )
    await callback_query.answer()


@router.message(Mailing.audience_products)
async def mail_aud_products_set(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    initialize_user_data(user_id)
    raw = (message.text or "").strip()
    if raw in {"-", "−", "очистити"}:
        products = []
    else:
        parts = []
        for chunk in raw.replace("\n", ",").split(","):
            s = chunk.strip()
            if s and s not in parts:
                parts.append(s)
        products = parts[:12]
    user_data[user_id]["audience_products"] = products
    user_data[user_id]["audience"] = "segment"
    await state.set_state(Mailing.audience)
    ids, label = _resolve_recipients(user_id)
    await message.answer(
        f"Товари збережено.\n\nЗараз: {label}",
        parse_mode="HTML",
        reply_markup=get_mailing_audience_keyboard(_audience_from_user(user_id)),
    )


@router.callback_query(F.data == "mail_aud_days")
async def mail_aud_days(callback_query: types.CallbackQuery, state: FSMContext):
    await state.set_state(Mailing.audience_days)
    user_id = callback_query.from_user.id
    initialize_user_data(user_id)
    user_data[user_id]["audience"] = "segment"
    await callback_query.message.answer(
        "⏱ Час у програмі (днів з реєстрації).\n\n"
        "Формат: <code>мін-макс</code> або одне число (мінімум).\n"
        "Приклади: <code>30-90</code>, <code>7</code>, <code>0-14</code>\n"
        "«−» — без обмеження.",
        parse_mode="HTML",
        reply_markup=back_mailing_keyboard(),
    )
    await callback_query.answer()


@router.message(Mailing.audience_days)
async def mail_aud_days_set(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    initialize_user_data(user_id)
    raw = (message.text or "").strip().replace(" ", "")
    days_min = days_max = None
    if raw not in {"-", "−", "очистити"}:
        try:
            if "-" in raw:
                a, b = raw.split("-", 1)
                days_min = int(a) if a != "" else None
                days_max = int(b) if b != "" else None
            else:
                days_min = int(raw)
        except ValueError:
            await message.answer("Не зрозумів. Приклад: <code>30-90</code>", parse_mode="HTML")
            return
    user_data[user_id]["audience_days_min"] = days_min
    user_data[user_id]["audience_days_max"] = days_max
    user_data[user_id]["audience"] = "segment"
    await state.set_state(Mailing.audience)
    ids, label = _resolve_recipients(user_id)
    await message.answer(
        f"Збережено.\n\nЗараз: {label}",
        parse_mode="HTML",
        reply_markup=get_mailing_audience_keyboard(_audience_from_user(user_id)),
    )


@router.callback_query(F.data == "mail_aud_back")
async def mail_aud_back(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    await state.set_state(Mailing.audience)
    ids, label = _resolve_recipients(user_id)
    await callback_query.message.edit_text(
        f"<b>👥 АУДИТОРІЯ</b>\n\nЗараз: {label}",
        parse_mode="HTML",
        reply_markup=get_mailing_audience_keyboard(_audience_from_user(user_id)),
    )
    await callback_query.answer()


@router.callback_query(F.data == "mail_aud_done")
async def mail_aud_done(callback_query: types.CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback_query.from_user.id
    ids, label = _resolve_recipients(user_id)
    await callback_query.message.edit_text(
        "<b>💼 НАЛАШТУВАННЯ ВІДПРАВКИ</b>\n\n"
        f"Аудиторія: {label}\n\n"
        "Пост готовий до розсилки.",
        parse_mode="HTML",
        reply_markup=publish_post(),
    )
    await callback_query.answer()
    
    
@router.callback_query(F.data.startswith('publish_'))
async def confirm_publish(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    initialize_user_data(user_id)
    ids, label = _resolve_recipients(user_id)
    opted_out = count_mailing_opted_out()
    await callback_query.message.edit_text(
        "Ви впевнені, що хочете зробити розсилку?\n\n"
        f"Аудиторія: {label}\n"
        f"Отримають: <b>{len(ids)}</b>\n"
        f"Відписані загалом у базі: <b>{opted_out}</b>",
        parse_mode="HTML",
        reply_markup=confirm_mailing(),
    )


async def _send_mailing_to(
    recipient_id: int,
    *,
    media_info,
    media_type,
    content_info,
    reply_markup,
    disable_notification: bool,
) -> None:
    if media_info:
        if media_type == "photo":
            await bot.send_photo(
                recipient_id,
                media_info,
                caption=content_info,
                parse_mode="HTML",
                reply_markup=reply_markup,
                disable_notification=disable_notification,
            )
        elif media_type == "video":
            await bot.send_video(
                recipient_id,
                media_info,
                caption=content_info,
                parse_mode="HTML",
                reply_markup=reply_markup,
                disable_notification=disable_notification,
            )
        elif media_type == "document":
            await bot.send_document(
                recipient_id,
                media_info,
                caption=content_info,
                parse_mode="HTML",
                reply_markup=reply_markup,
                disable_notification=disable_notification,
            )
        else:
            await bot.send_message(
                recipient_id,
                content_info,
                parse_mode="HTML",
                reply_markup=reply_markup,
                disable_notification=disable_notification,
            )
    else:
        await bot.send_message(
            recipient_id,
            content_info,
            parse_mode="HTML",
            reply_markup=reply_markup,
            disable_notification=disable_notification,
        )


async def run_mailing_job(job_id: int, *, progress_chat_id: int | None = None) -> dict:
    """Process pending recipients for a persisted job (also used after restart)."""
    from database_functions import mailing_jobs_db as mdb
    import json

    job = mdb.get_job(job_id)
    if not job or job.get("status") != mdb.STATUS_RUNNING:
        return mdb.job_stats(job_id)
    payload = json.loads(job["payload_json"])
    media_info = payload.get("media")
    media_type = payload.get("media_type")
    content_info = payload.get("content")
    url_buttons = payload.get("url_buttons")
    track_buttons = payload.get("track_buttons")
    disable_notification = bool(payload.get("disable_notification"))
    admin_uid = int(job.get("admin_user_id") or 0)
    markup = None
    try:
        if url_buttons or track_buttons:
            markup = post_keyboard(
                {
                    admin_uid: {
                        "url_buttons": url_buttons,
                        "track_buttons": track_buttons,
                    }
                },
                admin_uid,
                url_buttons,
                track_buttons=track_buttons,
                job_id=job_id,
            )
    except Exception:
        markup = None

    while True:
        batch = mdb.list_pending_recipients(job_id, limit=30)
        if not batch:
            break
        for recipient_id in batch:
            try:
                await _send_mailing_to(
                    recipient_id,
                    media_info=media_info,
                    media_type=media_type,
                    content_info=content_info,
                    reply_markup=markup,
                    disable_notification=disable_notification,
                )
                mdb.mark_recipient(job_id, recipient_id, mdb.RECIPIENT_SENT)
            except Exception as exc:
                err = str(exc)
                mdb.mark_recipient(job_id, recipient_id, mdb.RECIPIENT_FAILED, err)
                low = err.lower()
                if "blocked" in low or "deactivated" in low or "forbidden" in low:
                    try:
                        from database_functions.client_db import (
                            OPT_OUT_BOT_BLOCKED,
                            set_mailing_opt_out,
                        )

                        set_mailing_opt_out(
                            recipient_id, True, reason=OPT_OUT_BOT_BLOCKED
                        )
                    except Exception:
                        pass
            await asyncio.sleep(2)
        if progress_chat_id:
            st = mdb.job_stats(job_id)
            if st["sent"] and st["sent"] % 50 == 0:
                try:
                    await bot.send_message(
                        progress_chat_id,
                        f"Розсилка #{job_id}: надіслано {st['sent']}/{st['total']}…",
                    )
                except Exception:
                    pass
    return mdb.job_stats(job_id)


@router.callback_query(F.data.startswith('confirm_publish_'))
async def handle_publish_confirmation(callback_query: types.CallbackQuery, state: FSMContext):
    from database_functions import mailing_jobs_db as mdb

    user_id = callback_query.from_user.id
    initialize_user_data(user_id)
    opted_out = count_mailing_opted_out()
    user_ids, aud_label = _resolve_recipients(user_id)
    if not user_ids:
        await callback_query.answer("Немає отримувачів у цій аудиторії", show_alert=True)
        return
    await callback_query.message.edit_text(
        "Починаю розсилку"
        + (f" (відписаних у базі: {opted_out})…" if opted_out else "…"),
        reply_markup=None,
    )

    media_info = user_data[user_id].get('media')
    media_type = user_data[user_id].get('media_type')
    content_info = user_data[user_id].get('content')
    url_buttons = user_data[user_id].get('url_buttons')
    track_buttons = user_data[user_id].get('track_buttons')
    bell = user_data[user_id].get('bell', 0)
    disable_notification = (bell == 0)
    aud_meta = _audience_from_user(user_id)

    job_id = mdb.create_job(
        admin_user_id=user_id,
        payload={
            "media": media_info,
            "media_type": media_type,
            "content": content_info,
            "url_buttons": url_buttons,
            "track_buttons": track_buttons,
            "disable_notification": disable_notification,
            "audience": aud_meta,
            "audience_label": aud_label,
        },
        recipient_ids=list(user_ids),
    )
    progress_chat_id = callback_query.message.chat.id

    async def _run_and_report() -> None:
        try:
            stats = await run_mailing_job(job_id, progress_chat_id=progress_chat_id)
            clicks = mdb.button_click_stats(job_id)
            click_lines = ""
            if clicks:
                click_lines = "\n\n📊 Кліки:\n" + "\n".join(
                    f"· {c.get('btn_label') or c['btn_key']}: "
                    f"<b>{c['unique_users']}</b> унік. / {c['clicks']} кліків"
                    for c in clicks
                )
            await bot.send_message(
                progress_chat_id,
                f"Розсилка #{job_id} завершена.\n"
                f"Аудиторія: {aud_label}\n"
                f"✅ Надіслано: <b>{stats['sent']}</b>\n"
                f"❌ Помилок: <b>{stats['failed']}</b>\n"
                f"Усього в черзі: <b>{stats['total']}</b>"
                f"{click_lines}",
                parse_mode="HTML",
            )
        except Exception as exc:
            await bot.send_message(
                progress_chat_id,
                f"Розсилка #{job_id} перервалась: {exc}",
            )

    asyncio.create_task(_run_and_report())
    await callback_query.message.answer(
        f"🚀 Розсилка #{job_id} пішла у фон ({len(user_ids)} отримувачів).\n"
        f"{aud_label}\n"
        "Можеш користуватись адмінкою — прогрес і підсумок прийдуть сюди.",
        parse_mode="HTML",
    )


@router.callback_query(F.data == "back_to",)
async def process_channel_info(callback_query: types.CallbackQuery):
    await callback_query.message.delete()
    
@router.callback_query(IsAdmin(), F.data == "back_to_my_post", StateFilter(Mailing.content, Mailing.media, Mailing.description, Mailing.url_buttons))
async def process_channel_info(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.message.delete()
    await state.clear()

@router.callback_query(IsAdmin(), F.data == "back_to_posts")
async def back_to_mailing_hub(callback_query: types.CallbackQuery, state: FSMContext):
    await state.clear()
    description = mailing_text
    try:
        await callback_query.message.edit_text(
            description, parse_mode="HTML", reply_markup=get_broadcast_keyboard()
        )
    except Exception:
        await callback_query.message.answer(
            description, parse_mode="HTML", reply_markup=get_broadcast_keyboard()
        )
    await callback_query.answer()

    
@router.callback_query(F.data == 'cancel_publish')
async def cancel_publish(callback_query: types.CallbackQuery):
    await callback_query.answer("Публікацію скасовано.", show_alert=True)


@router.callback_query(IsAdmin(), F.data == "mailing_history")
async def mailing_history(callback_query: types.CallbackQuery):
    from database_functions import mailing_jobs_db as mdb

    jobs = mdb.list_recent_jobs(limit=12)
    if not jobs:
        await callback_query.answer("Ще не було розсилок", show_alert=True)
        return
    await callback_query.message.edit_text(
        "📊 <b>Історія розсилок</b>\nОбери номер — sent / кліки / аудиторія.",
        parse_mode="HTML",
        reply_markup=mailing_job_history_keyboard(jobs),
    )
    await callback_query.answer()


@router.callback_query(IsAdmin(), F.data.startswith("mailing_job:"))
async def mailing_job_detail(callback_query: types.CallbackQuery):
    from database_functions import mailing_jobs_db as mdb
    import json

    try:
        job_id = int((callback_query.data or "").split(":")[-1])
    except ValueError:
        await callback_query.answer("Невірний id", show_alert=True)
        return
    job = mdb.get_job(job_id)
    if not job:
        await callback_query.answer("Не знайдено", show_alert=True)
        return
    stats = mdb.job_stats(job_id)
    clicks = mdb.button_click_stats(job_id)
    uniq = mdb.total_unique_clickers(job_id)
    try:
        payload = json.loads(job.get("payload_json") or "{}")
    except json.JSONDecodeError:
        payload = {}
    aud = payload.get("audience_label") or "—"
    sent = int(stats.get("sent") or 0)
    ctr = (100.0 * uniq / sent) if sent else 0.0
    lines = [
        f"📬 <b>Розсилка #{job_id}</b>",
        f"Статус: <b>{job.get('status')}</b>",
        f"Створено: {_esc_mail(job.get('created_at'))}",
        f"Аудиторія: {aud}",
        f"✅ {stats['sent']} · ❌ {stats['failed']} · усього {stats['total']}",
        f"Унікальних кліків: <b>{uniq}</b> · CTR ≈ <b>{ctr:.1f}%</b>",
    ]
    if clicks:
        lines.append("")
        lines.append("<b>Кнопки:</b>")
        for c in clicks:
            lines.append(
                f"· {_esc_mail(c.get('btn_label') or c['btn_key'])}: "
                f"{c['unique_users']} унік. / {c['clicks']}"
            )
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ До історії", callback_data="mailing_history")],
            [InlineKeyboardButton(text="🏠 Розсилка", callback_data="back_to_posts")],
        ]
    )
    await callback_query.message.edit_text(
        "\n".join(lines), parse_mode="HTML", reply_markup=kb
    )
    await callback_query.answer()


def _esc_mail(s) -> str:
    return (
        str(s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


@router.callback_query(IsAdmin(), F.data == "quests_admin")
async def quests_admin(callback_query: types.CallbackQuery):
    from database_functions import quest_campaigns_db as qcdb

    camps = qcdb.list_campaigns()
    await callback_query.message.edit_text(
        "🎯 <b>Квести / акції</b>\n\n"
        "Тут запускаємо заморожені й сезонні акції.\n"
        "Почни з тестової «3 візити» — зʼявиться в клієнтському меню «🎯 Квести».",
        parse_mode="HTML",
        reply_markup=quests_admin_keyboard(camps),
    )
    await callback_query.answer()


@router.callback_query(IsAdmin(), F.data.startswith("quest_camp:"))
async def quest_camp_view(callback_query: types.CallbackQuery):
    from database_functions import quest_campaigns_db as qcdb

    try:
        cid = int((callback_query.data or "").split(":")[-1])
    except ValueError:
        await callback_query.answer("Невірний id", show_alert=True)
        return
    camp = qcdb.get_campaign(cid)
    if not camp:
        await callback_query.answer("Не знайдено", show_alert=True)
        return
    st = qcdb.campaign_stats(cid)
    text = (
        f"🎯 <b>{_esc_mail(camp.get('title'))}</b>\n"
        f"Ключ: <code>{_esc_mail(camp.get('key'))}</code>\n"
        f"Статус: <b>{_esc_mail(camp.get('status'))}</b>\n"
        f"Квести: {_esc_mail(', '.join(camp.get('quest_keys') or []) or '—')}\n"
        f"Старт: {_esc_mail(camp.get('starts_at') or '—')}\n"
        f"Кінець: {_esc_mail(camp.get('ends_at') or 'без ліміту')}\n\n"
        f"{_esc_mail(camp.get('description') or '')}\n\n"
        f"📊 Переглядів: {st['views']} · завершень: {st['completes']} · "
        f"унік. {st['unique_users']}"
    )
    await callback_query.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=quest_campaign_actions_keyboard(camp),
    )
    await callback_query.answer()


@router.callback_query(IsAdmin(), F.data.startswith("quest_camp_on:"))
async def quest_camp_on(callback_query: types.CallbackQuery):
    from database_functions import quest_campaigns_db as qcdb

    cid = int((callback_query.data or "").split(":")[-1])
    qcdb.activate_campaign(cid)
    callback_query.data = f"quest_camp:{cid}"
    await quest_camp_view(callback_query)


@router.callback_query(IsAdmin(), F.data.startswith("quest_camp_off:"))
async def quest_camp_off(callback_query: types.CallbackQuery):
    from database_functions import quest_campaigns_db as qcdb

    cid = int((callback_query.data or "").split(":")[-1])
    qcdb.end_campaign(cid)
    callback_query.data = f"quest_camp:{cid}"
    await quest_camp_view(callback_query)


@router.callback_query(IsAdmin(), F.data.startswith("quest_camp_stats:"))
async def quest_camp_stats(callback_query: types.CallbackQuery):
    from database_functions import quest_campaigns_db as qcdb

    cid = int((callback_query.data or "").split(":")[-1])
    camp = qcdb.get_campaign(cid)
    st = qcdb.campaign_stats(cid)
    await callback_query.answer(
        f"{camp.get('title') if camp else cid}: "
        f"views {st['views']}, done {st['completes']}, uniq {st['unique_users']}",
        show_alert=True,
    )