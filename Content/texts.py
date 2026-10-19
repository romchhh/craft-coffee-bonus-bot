from database_functions.settings_db import (
    get_birthday_bonus_uah,
    get_cashback_percent,
    get_referral_bonus_uah,
    get_welcome_bonus_uah,
)


def get_need_card_first() -> str:
    return (
        "🪪 <b>Спочатку оформи картку лояльності</b>\n\n"
        "Без неї не працюють Крафтики на балансі, мініап і історія покупок.\n"
        "Натисни /start — займе близько хвилини."
    )


def get_registration_welcome(name: str | None = None) -> str:
    hello = f", {name}" if name else ""
    return (
        f"☕ <b>Вітаємо в Крафт Кава{hello}!</b>\n\n"
        "Ми — кав’ярня <b>Крафт Кава</b>. "
        "Зараз оформимо цифрову картку — Крафтики на балансі, мініап і історія покупок."
    )


def get_greeting_message(name: str | None = None) -> str:
    """Generic greeting (e.g. admin / parcel)."""
    return get_registration_welcome(name)


def get_ask_name() -> str:
    return "Як до тебе звертатися?\nНадішли ім’я одним повідомленням."


def get_ask_phone() -> str:
    return (
        "Поділися номером телефону — він потрібен для картки в касі.\n"
        "Натисни кнопку нижче 👇"
    )


def get_ask_birthday() -> str:
    return (
        "Дата народження <i>(за бажанням)</i>\n\n"
        "Натисни <b>«Обрати дату»</b> — відкриється зручний вибір дня, місяця і року.\n"
        "Або натисни «Пропустити»."
    )


def get_registration_done(name: str, bonus: float, card_number: str) -> str:
    lines = [
        f"🎉 <b>{name}, твоя картка Крафт Кава готова!</b>",
        "",
    ]
    if bonus and bonus > 0:
        lines.append(
            f"На балансі <b>{bonus:g}</b> вітальних Крафтиків — "
            "можна списати вже при наступній покупці."
        )
        lines.append("")
    lines.extend(
        [
            f"Номер картки: <code>{card_number}</code>",
            "",
            "Покажи <b>штрихкод на фото</b> на касі — бариста нарахує або спише Крафтики.",
            "",
            "У мініапі — дата народження, реферал і твій баланс.",
        ]
    )
    return "\n".join(lines)


def get_referral_bonus_notification(friend_name: str, amount: float) -> str:
    name = (friend_name or "Друг").strip() or "Друг"
    return (
        "🎉 <b>Крафтики за друга!</b>\n\n"
        f"<b>{name}</b> зробив покупку за твоїм запрошенням.\n"
        f"На баланс нараховано <b>+{amount:g}</b> "
        "(доступні з сьогодні 00:00 за Києвом).\n\n"
        "Дякуємо, що ділишся Крафт Кава ☕"
    )


def get_already_registered(name: str | None = None) -> str:
    who = name or "друже"
    return (
        f"☕ Знову раді тебе бачити, <b>{who}</b>!\n\n"
        "Твоя картка Крафт Кава завжди під рукою в мінізастосунку."
    )


def get_about_text() -> str:
    from Content.locations import locations_text_html

    return (
        "<b>Крафт Кава</b>\n\n"
        "Крафт кава в Броварах, затишна атмосфера та Крафтики на баланс за кожну покупку.\n\n"
        f"{locations_text_html()}"
    )


def get_faq_text() -> str:
    welcome = get_welcome_bonus_uah()
    birthday = get_birthday_bonus_uah()
    referral = get_referral_bonus_uah()
    return (
        "<b>Як працюють Крафтики на балансі?</b>\n\n"
        f"• За реєстрацію — <b>{welcome:g}</b> одразу\n"
        f"• За дату народження в мініапі — <b>+{birthday:g}</b>\n"
        f"• За друга: поділись посиланням → друг реєструється й отримує "
        f"<b>{welcome:g}</b> вітальних → друг робить покупку від 50 грн → "
        f"тобі <b>+{referral:g}</b> наступного дня о 00:00\n"
        "• Кешбек з покупок — <b>прогресивний</b> (старт 1%, далі зростає за Зарядом у мініапі)\n"
        "• 1 Крафтик = 1 грн знижки\n"
        "• Покажи штрихкод на касі, щоб нарахувати або списати Крафтики\n"
        "• Правила програми й політика конфіденційності — у меню «ℹ️ Інфо»"
    )


def get_manager_text() -> str:
    from database_functions.settings_db import get_support_username

    username = get_support_username()
    return (
        "<b>Підтримка Крафт Кава</b>\n\n"
        "Напиши нам, якщо є питання щодо картки чи балансу.\n"
        f"Контакт: <b>@{username}</b>"
    )


def get_info_text(*, opted_out: bool) -> str:
    if opted_out:
        mailing = (
            "🔕 <b>Рекламна розсилка вимкнена</b>\n"
            "Ти не отримуєш рекламні повідомлення від Крафт Кава.\n"
            "Службові сповіщення (кешбек, нарахування) як і раніше можуть приходити."
        )
    else:
        mailing = (
            "🔔 <b>Рекламна розсилка увімкнена</b>\n"
            "Ти отримуєш новини та акції Крафт Кава в боті.\n"
            "Службові сповіщення (кешбек, нарахування) не залежать від цього налаштування."
        )
    return (
        "ℹ️ <b>Інфо</b>\n\n"
        f"{mailing}\n\n"
        "Нижче — правила програми, політика конфіденційності та керування розсилкою."
    )


def get_mailing_prefs_text(*, opted_out: bool) -> str:
    """Backward-compatible alias for info screen mailing block."""
    return get_info_text(opted_out=opted_out)


mailing_text = (
    "<b>СТВОРЕННЯ ПОСТУ:</b>\n\n"
    "Ця функція дозволяє створити пост і розіслати його користувачам бота,\n"
    "які не відписалися від рекламної розсилки."
)
