from __future__ import annotations

import logging
import re
from aiogram import Router, types, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, ReplyKeyboardRemove

from main import bot
from config import WEBAPP_URL
from database_functions.settings_db import get_welcome_bonus_uah
from keyboards.client_keyboards import (
    get_start_keyboard,
    get_phone_keyboard,
    get_open_card_inline,
    get_manager_keyboard,
    get_about_keyboard,
    set_webapp_menu,
)
from Content.texts import (
    get_registration_welcome,
    get_need_card_first,
    get_ask_name,
    get_ask_phone,
    get_registration_done,
    get_referral_bonus_notification,
    get_already_registered,
    get_about_text,
    get_faq_text,
    get_manager_text,
)
from database_functions.client_db import (
    check_user,
    add_user,
    update_user_activity,
    is_registered,
    get_user,
    save_registration,
    next_card_seq,
)
from database_functions.create_dbs import create_dbs
from database_functions.links_db import increment_link_count
from states.client_states import Registration
from services import poster
from utils.filters import IsAdmin, NotRegistered
from services.barcode_image import render_card_barcode_png

log = logging.getLogger(__name__)
router = Router()


async def _ensure_user(message: types.Message) -> None:
    user = message.from_user
    if not check_user(user.id):
        add_user(user.id, user.username, user.first_name, user.last_name, user.language_code)
    update_user_activity(user.id)


@router.message(CommandStart())
async def start_command(message: types.Message, state: FSMContext):
    await state.clear()
    user = message.from_user
    args = message.text.split()

    ref_link = None
    referred_by: int | None = None
    if len(args) > 1:
        payload = args[1]
        if payload.startswith("linktowatch_"):
            try:
                ref_link = int(payload.split("_")[1])
                if not check_user(user.id):
                    increment_link_count(ref_link)
            except (ValueError, IndexError):
                pass
        elif payload.startswith("ref_"):
            try:
                rid = int(payload[4:])
                if rid != user.id:
                    referred_by = rid
            except ValueError:
                pass

    if not check_user(user.id):
        add_user(user.id, user.username, user.first_name, user.last_name, user.language_code, ref_link)
    update_user_activity(user.id)
    if referred_by and not is_registered(user.id):
        from services.referrals import remember_referral_click

        remember_referral_click(user.id, referred_by)
        # sticky: у FSM лише якщо в БД закріпився цей запрошувач
        db_u = get_user(user.id)
        if db_u and db_u.get("referred_by_user_id"):
            await state.update_data(referred_by=int(db_u["referred_by_user_id"]))
        else:
            await state.update_data(referred_by=referred_by)

    if is_registered(user.id):
        db_user = get_user(user.id)
        name = (db_user or {}).get("display_name") or user.first_name
        await message.answer(
            get_already_registered(name),
            parse_mode="HTML",
            reply_markup=get_start_keyboard(user.id, registered=True),
        )
        inline = get_open_card_inline()
        if inline:
            await message.answer("Твоя цифрова картка 👇", reply_markup=inline)
        return

    await message.answer(
        get_registration_welcome(user.first_name),
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer(get_ask_name(), parse_mode="HTML")
    await state.set_state(Registration.name)


async def _prompt_need_card(message: types.Message) -> None:
    await message.answer(
        get_need_card_first(),
        parse_mode="HTML",
        reply_markup=get_start_keyboard(message.from_user.id, registered=False),
    )


@router.message(F.text == "✅ Оформити картку")
async def register_card_button(message: types.Message, state: FSMContext):
    prev = await state.get_data()
    referred_by = prev.get("referred_by")
    await state.clear()
    if referred_by:
        await state.update_data(referred_by=referred_by)
    await _ensure_user(message)
    if is_registered(message.from_user.id):
        db_user = get_user(message.from_user.id)
        name = (db_user or {}).get("display_name") or message.from_user.first_name
        await message.answer(
            get_already_registered(name),
            parse_mode="HTML",
            reply_markup=get_start_keyboard(message.from_user.id, registered=True),
        )
        return
    await message.answer(
        get_ask_name(),
        parse_mode="HTML",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.set_state(Registration.name)


@router.message(Registration.name)
async def reg_name(message: types.Message, state: FSMContext):
    name = (message.text or "").strip()
    if len(name) < 2 or len(name) > 60:
        await message.answer("Вкажи ім’я від 2 до 60 символів.")
        return
    await state.update_data(display_name=name)
    await message.answer(get_ask_phone(), parse_mode="HTML", reply_markup=get_phone_keyboard())
    await state.set_state(Registration.phone)


@router.message(Registration.phone, F.contact)
async def reg_phone_contact(message: types.Message, state: FSMContext):
    contact = message.contact
    if contact.user_id and contact.user_id != message.from_user.id:
        await message.answer("Надішли саме свій контакт кнопкою нижче.")
        return
    await _save_phone_and_finish(message, state, contact.phone_number)


@router.message(Registration.phone)
async def reg_phone_text(message: types.Message, state: FSMContext):
    raw = (message.text or "").strip()
    try:
        phone = poster.normalize_phone(raw)
    except ValueError:
        await message.answer(
            "Не схоже на український номер. Натисни кнопку «Поділитися номером» або введи як 0501234567.",
            reply_markup=get_phone_keyboard(),
        )
        return
    await _save_phone_and_finish(message, state, phone)


async def _save_phone_and_finish(message: types.Message, state: FSMContext, raw_phone: str):
    try:
        phone = poster.normalize_phone(raw_phone)
    except ValueError:
        await message.answer("Некоректний номер. Спробуй ще раз.", reply_markup=get_phone_keyboard())
        return
    await state.update_data(phone=phone)
    await _finish_registration(message, state)


async def _finish_registration(
    message: types.Message,
    state: FSMContext,
) -> None:
    data = await state.get_data()
    if not data.get("display_name") or not data.get("phone"):
        await state.clear()
        await message.answer("Щось пішло не так. Почни знову: /start")
        return

    await state.clear()
    await message.answer("⏳ Створюємо картку в Craft Coffee…")

    try:
        client_id, card_number, bonus_given = await _create_loyalty_card(
            telegram_id=message.from_user.id,
            display_name=data["display_name"],
            phone=data["phone"],
            birthday=None,
        )
    except Exception as exc:
        log.exception("Registration failed for %s", message.from_user.id)
        await message.answer(
            "Не вдалося створити картку. Спробуй /start трохи пізніше.\n"
            f"<code>{exc}</code>",
            parse_mode="HTML",
            reply_markup=get_start_keyboard(message.from_user.id, registered=False),
        )
        return

    save_registration(
        message.from_user.id,
        display_name=data["display_name"],
        phone=data["phone"],
        birthday=None,
        poster_client_id=client_id,
        card_number=card_number,
        welcome_bonus_given=bonus_given,
    )
    from database_functions.charge_db import init_loyalty_for_user
    from services.referrals import bind_referrer_on_registration
    from services.quests import build_quests_ui

    init_loyalty_for_user(message.from_user.id)
    referred_by = data.get("referred_by")
    db_after = get_user(message.from_user.id)
    if not referred_by and db_after and db_after.get("referred_by_user_id"):
        referred_by = int(db_after["referred_by_user_id"])
    if referred_by:
        bind_referrer_on_registration(message.from_user.id, int(referred_by))
    try:
        build_quests_ui(message.from_user.id)
    except Exception:
        log.exception("init quests for %s", message.from_user.id)

    bonus_text = get_welcome_bonus_uah() if bonus_given else 0
    await _send_registration_success(
        message,
        display_name=data["display_name"],
        bonus=bonus_text,
        card_number=card_number,
    )


async def _notify_referrer_referral_bonus(
    *,
    referrer_user_id: int,
    friend_name: str,
    amount: float,
) -> None:
    text = get_referral_bonus_notification(friend_name, amount)
    inline = get_open_card_inline()
    try:
        await bot.send_message(
            referrer_user_id,
            text,
            parse_mode="HTML",
            reply_markup=inline,
        )
    except TelegramBadRequest as exc:
        log.info("referral notify failed referrer=%s: %s", referrer_user_id, exc)
    except Exception as exc:
        log.warning("referral notify failed referrer=%s: %s", referrer_user_id, exc)


async def _send_registration_success(
    message: types.Message,
    *,
    display_name: str,
    bonus: float,
    card_number: str,
) -> None:
    caption = get_registration_done(display_name, bonus, card_number)
    inline = get_open_card_inline()
    if inline:
        caption += "\n\nВідкрий цифрову картку в мінізастосунку 👇"
    elif not WEBAPP_URL:
        caption += (
            "\n\n<i>Мінізастосунок ще не підключено — покажи штрихкод на касі.</i>"
        )

    pinned_id = None
    try:
        png = render_card_barcode_png(card_number)
        photo = BufferedInputFile(png.read(), filename="craft-card-barcode.png")
        sent = await message.answer_photo(
            photo=photo,
            caption=caption,
            parse_mode="HTML",
            reply_markup=inline,
        )
        pinned_id = sent.message_id
    except Exception as exc:
        log.warning("barcode photo failed: %s", exc)
        sent = await message.answer(
            caption,
            parse_mode="HTML",
            reply_markup=inline,
        )
        pinned_id = sent.message_id

    if pinned_id:
        try:
            await bot.pin_chat_message(
                chat_id=message.chat.id,
                message_id=pinned_id,
                disable_notification=True,
            )
        except TelegramBadRequest as exc:
            log.info("could not pin registration message: %s", exc)

    await message.answer(
        "Меню бота знизу — картка, бонуси та підтримка.",
        reply_markup=get_start_keyboard(message.from_user.id, registered=True),
    )


async def _create_loyalty_card(
    *,
    telegram_id: int,
    display_name: str,
    phone: str,
    birthday: str | None,
) -> tuple[int, str, bool]:
    """Повертає (poster_client_id, card_number, welcome_bonus_given)."""
    card_number = poster.ean13_from_seq(next_card_seq() * 1000 + (telegram_id % 1000))
    existing = poster.find_client_by_phone(phone)

    if existing:
        client_id = int(existing["client_id"])
        current_card = (existing.get("card_number") or "").strip()
        if not current_card:
            try:
                poster.update_client(client_id, card_number=card_number)
            except poster.PosterError:
                pass
        else:
            card_number = current_card

        fields = {
            "client_name": display_name,
            "client_groups_id_client": poster.client_group_id(),
        }
        if birthday:
            fields["birthday"] = birthday
        try:
            poster.update_client(client_id, **fields)
        except poster.PosterError:
            pass

        # Вітальний бонус лише якщо баланс порожній / майже нуль
        balance = poster.from_minor(existing.get("bonus"))
        bonus_given = False
        if balance < 1:
            poster.set_bonus(client_id, get_welcome_bonus_uah())
            bonus_given = True
        return client_id, card_number, bonus_given

    client_id = poster.create_client(
        name=display_name,
        phone=phone,
        card_number=card_number,
        birthday=birthday,
        bonus_uah=get_welcome_bonus_uah(),
    )
    return client_id, card_number, True


@router.message(F.text == "🪪 Моя картка")
async def open_card_fallback(message: types.Message):
    await _ensure_user(message)
    if not is_registered(message.from_user.id):
        await _prompt_need_card(message)
        return
    user = get_user(message.from_user.id)
    inline = get_open_card_inline()
    if inline:
        await message.answer(
            "Відкрий картку кнопкою нижче — так Telegram передасть дані для входу 👇",
            reply_markup=inline,
        )
        return
    await message.answer(
        f"Код картки: <code>{user.get('card_number')}</code>\n"
        "Мінізастосунок з’явиться після налаштування WEBAPP_URL.",
        parse_mode="HTML",
    )


@router.message(F.text == "☕ Про Craft Coffee")
async def about(message: types.Message):
    await _ensure_user(message)
    if not is_registered(message.from_user.id):
        await _prompt_need_card(message)
        return
    await message.answer(
        get_about_text(),
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=get_about_keyboard(),
    )


@router.message(F.text == "🎁 Бонуси")
async def bonuses_info(message: types.Message):
    await _ensure_user(message)
    if not is_registered(message.from_user.id):
        await _prompt_need_card(message)
        return
    user = get_user(message.from_user.id)
    lines = [get_faq_text()]
    if user and user.get("poster_client_id"):
        try:
            balance = poster.get_client_bonus_uah(user["poster_client_id"])
            lines.append(f"\n💳 <b>Твій баланс зараз:</b> {balance:g} грн")
        except Exception:
            pass
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(F.text.in_(["💬 Підтримка"]))
@router.message(Command("support"))
async def support(message: types.Message):
    await _ensure_user(message)
    if not is_registered(message.from_user.id):
        await _prompt_need_card(message)
        return
    await message.answer(
        text=get_manager_text(),
        parse_mode="HTML",
        reply_markup=get_manager_keyboard(),
    )


@router.message(F.web_app_data)
async def webapp_data_outside_flow(message: types.Message):
    """WebApp sendData поза реєстрацією — не залишати update без обробника."""
    from database_functions.client_db import is_registered

    if not is_registered(message.from_user.id):
        await _prompt_need_card(message)
        return
    await message.answer(
        "Якщо картка не відкрилась — натисни «🪪 Моя картка» або /start",
        reply_markup=get_start_keyboard(message.from_user.id, registered=True),
    )


@router.message(StateFilter(None), ~F.text.startswith("/"), NotRegistered(), ~IsAdmin())
async def guest_without_card(message: types.Message):
    """Користувач без картки пише щось поза реєстрацією (не перехоплює адмінку)."""
    if not message.from_user or not message.text:
        return
    await _ensure_user(message)
    await _prompt_need_card(message)


async def on_startup(router):
    import asyncio

    from config import POSTER_TOKEN
    from services.loyalty_cron import start_loyalty_cron

    me = await bot.get_me()
    create_dbs()
    if POSTER_TOKEN:
        try:
            await asyncio.to_thread(poster.init_client_group)
            await asyncio.to_thread(poster.migrate_registered_bot_clients_to_group)
        except Exception:
            log.exception("Poster client group sync on startup")
    await set_webapp_menu(bot)
    start_loyalty_cron(bot)
    print(f"Bot: @{me.username} запущений!")
    if WEBAPP_URL:
        print(f"Mini App: {WEBAPP_URL}")
        print(f"Poster webhook: {WEBAPP_URL}/webhook/poster")
    else:
        print("WEBAPP_URL не задано — кнопка Mini App і webhook URL вимкнені.")


async def on_shutdown(router):
    from services.loyalty_cron import stop_loyalty_cron

    await stop_loyalty_cron()
    me = await bot.get_me()
    print(f"Bot: @{me.username} зупинений!")
