from database_functions.settings_db import get_welcome_bonus_uah, get_cashback_percent


def get_need_card_first() -> str:
    return (
        "🪪 <b>Спочатку оформи картку лояльності</b>\n\n"
        "Без неї не працюють бонуси, мініап і історія покупок.\n"
        "Натисни <b>«Оформити картку»</b> або /start — займе близько хвилини."
    )


def get_greeting_message(name: str | None = None) -> str:
    hello = f", {name}" if name else ""
    return (
        f"☕ <b>Вітаємо в Craft Coffee{hello}!</b>\n\n"
        "Ми — кав’ярня <b>Craft Coffee</b>. "
        "Тут цифрова картка, бонуси та історія покупок.\n\n"
        f"{get_need_card_first()}"
    )


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
            f"На балансі <b>{bonus:g} грн</b> вітальних бонусів "
            f"(1 бонус = 1 грн) — можна списати вже при наступній покупці."
        )
        lines.append("")
    lines.extend(
        [
            f"Номер картки: <code>{card_number}</code>",
            "",
            "Покажи <b>штрихкод на фото</b> на касі — бариста нарахує або спише бонуси.",
            "",
            "У мініапі в розділі <b>«Квести»</b> можна додати день народження (+10 грн) і запросити друга (+10 грн).",
        ]
    )
    return "\n".join(lines)


def get_referral_bonus_notification(friend_name: str, amount: float) -> str:
    name = (friend_name or "Друг").strip() or "Друг"
    return (
        "🎉 <b>Бонус за друга!</b>\n\n"
        f"<b>{name}</b> оформив картку Craft Coffee за твоїм посиланням.\n"
        f"На баланс нараховано <b>{amount:g} грн</b> бонусів.\n\n"
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
        "Крафтова кава в Броварах, затишна атмосфера та бонуси за кожну покупку.\n\n"
        f"{locations_text_html()}"
    )


def get_faq_text() -> str:
    welcome = get_welcome_bonus_uah()
    cashback = get_cashback_percent()
    return (
        "<b>Як працюють бонуси?</b>\n\n"
        f"• За реєстрацію — {welcome:g} грн бонусів одразу\n"
        "• +10 грн за день народження в мініапі (квести)\n"
        "• +10 грн за кожного друга за реферальним посиланням\n"
        f"• Кешбек з покупок — {cashback:g}%\n"
        "• 1 бонус = 1 грн\n"
        "• Покажи штрихкод на касі, щоб нарахувати або списати бонуси"
    )


def get_manager_text() -> str:
    return (
        "<b>Підтримка Craft Coffee</b>\n\n"
        "Напиши нам, якщо є питання щодо картки чи бонусів."
    )


mailing_text = (
    "<b>СТВОРЕННЯ ПОСТУ:</b>\n\n"
    "Ця функція дозволяє створити пост і розіслати його всім користувачам бота."
)
