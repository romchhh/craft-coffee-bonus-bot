from database_functions.settings_db import get_welcome_bonus_uah, get_cashback_percent


def get_greeting_message(name: str | None = None) -> str:
    hello = f", {name}" if name else ""
    return (
        f"☕ <b>Вітаємо в Craft Coffee{hello}!</b>\n\n"
        "Ми — кав’ярня <b>Craft Coffee</b>. "
        "Тут твоя цифрова картка лояльності, бонуси та історія улюблених напоїв.\n\n"
        "Давай швидко оформимо картку — це займе хвилину."
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
        ]
    )
    return "\n".join(lines)


def get_already_registered(name: str | None = None) -> str:
    who = name or "друже"
    return (
        f"☕ Знову раді тебе бачити, <b>{who}</b>!\n\n"
        "Твоя картка Craft Coffee завжди під рукою в мінізастосунку."
    )


def get_about_text() -> str:
    return (
        "<b>Craft Coffee</b>\n\n"
        "Крафтова кава, затишна атмосфера та програма лояльності з бонусами за кожну покупку."
    )


def get_faq_text() -> str:
    welcome = get_welcome_bonus_uah()
    cashback = get_cashback_percent()
    return (
        "<b>Як працюють бонуси?</b>\n\n"
        f"• За реєстрацію — {welcome:g} грн бонусів одразу\n"
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
