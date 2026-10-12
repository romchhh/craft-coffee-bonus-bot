from database_functions.settings_db import get_welcome_bonus_uah, get_cashback_percent


def get_need_card_first() -> str:
    return (
        "🪪 <b>Спочатку оформи картку лояльності</b>\n\n"
        "Без неї не працюють гривні на балансі, мініап і історія покупок.\n"
        "Натисни /start — займе близько хвилини."
    )


def get_registration_welcome(name: str | None = None) -> str:
    hello = f", {name}" if name else ""
    return (
        f"☕ <b>Вітаємо в Craft Coffee{hello}!</b>\n\n"
        "Ми — кав’ярня <b>Craft Coffee</b>. "
        "Зараз оформимо цифрову картку — гривні на балансі, мініап і історія покупок."
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
        f"🎉 <b>{name}, твоя картка Craft Coffee готова!</b>",
        "",
    ]
    if bonus and bonus > 0:
        lines.append(
            f"На балансі <b>{bonus:g} грн</b> вітальних — "
            "можна списати вже при наступній покупці."
        )
        lines.append("")
    lines.extend(
        [
            f"Номер картки: <code>{card_number}</code>",
            "",
            "Покажи <b>штрихкод на фото</b> на касі — бариста нарахує або спише гривні.",
            "",
            "У мініапі — дата народження, реферал і твій баланс.",
        ]
    )
    return "\n".join(lines)


def get_referral_bonus_notification(friend_name: str, amount: float) -> str:
    name = (friend_name or "Друг").strip() or "Друг"
    return (
        "🎉 <b>Гривні за друга!</b>\n\n"
        f"<b>{name}</b> зробив покупку за твоїм запрошенням.\n"
        f"На баланс нараховано <b>{amount:g} грн</b> "
        "(доступні з сьогодні 00:00 за Києвом).\n\n"
        "Дякуємо, що ділишся Craft Coffee ☕"
    )


def get_already_registered(name: str | None = None) -> str:
    who = name or "друже"
    return (
        f"☕ Знову раді тебе бачити, <b>{who}</b>!\n\n"
        "Твоя картка Craft Coffee завжди під рукою в мінізастосунку."
    )


def get_about_text() -> str:
    from Content.locations import locations_text_html

    return (
        "<b>Крафт · Craft Coffee</b>\n\n"
        "Крафтова кава в Броварах, затишна атмосфера та гривні на баланс за кожну покупку.\n\n"
        f"{locations_text_html()}"
    )


def get_faq_text() -> str:
    welcome = get_welcome_bonus_uah()
    cashback = get_cashback_percent()
    return (
        "<b>Як працюють гривні на балансі?</b>\n\n"
        f"• За реєстрацію — {welcome:g} грн одразу\n"
        "• За дату народження в мініапі\n"
        "• За друга: поділись посиланням → друг реєструється → "
        "робить покупку від 50 грн → тобі +10 грн наступного дня о 00:00\n"
        f"• Кешбек з покупок — {cashback:g}%\n"
        "• 1 грн на балансі = 1 грн на касі\n"
        "• Покажи штрихкод на касі, щоб нарахувати або списати\n"
        "• Від рекламної розсилки можна відписатися в меню «🔔 Розсилка»"
    )


def get_manager_text() -> str:
    return (
        "<b>Підтримка Craft Coffee</b>\n\n"
        "Напиши нам, якщо є питання щодо картки чи балансу."
    )


def get_mailing_prefs_text(*, opted_out: bool) -> str:
    if opted_out:
        return (
            "🔕 <b>Розсилка вимкнена</b>\n\n"
            "Ти не отримуєш рекламні повідомлення від Craft Coffee.\n"
            "Службові сповіщення (кешбек, нарахування) як і раніше можуть приходити.\n\n"
            "Натисни кнопку нижче, щоб знову підписатися."
        )
    return (
        "🔔 <b>Розсилка увімкнена</b>\n\n"
        "Ти отримуєш новини та акції Craft Coffee в боті.\n"
        "Можеш відписатися будь-коли — у меню «🔔 Розсилка» або кнопкою під рекламним повідомленням.\n\n"
        "Службові сповіщення (кешбек, нарахування) не залежать від цього налаштування."
    )


mailing_text = (
    "<b>СТВОРЕННЯ ПОСТУ:</b>\n\n"
    "Ця функція дозволяє створити пост і розіслати його користувачам бота,\n"
    "які не відписалися від рекламної розсилки."
)
