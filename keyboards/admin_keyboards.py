from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, KeyboardButton, ReplyKeyboardMarkup
from database_functions.admin_db import get_all_admins
from database_functions.links_db import get_all_links


# MAIN KEYBOARD
def admin_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="Розсилка"), KeyboardButton(text="Статистика")],
        [KeyboardButton(text="👤 Клієнти"), KeyboardButton(text="📒 Журнал Крафтиків")],
        [KeyboardButton(text="👥 Реферали"), KeyboardButton(text="Адміністратори")],
        [KeyboardButton(text="Посилання"), KeyboardButton(text="🎁 Лояльність")],
        [KeyboardButton(text="💬 Контакт підтримки"), KeyboardButton(text="🍽 Меню")],
        [KeyboardButton(text="📍 Точки"), KeyboardButton(text="Головне меню")],
    ]

    keyboard = ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
    return keyboard


def get_ledger_hub_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Останні операції", callback_data="ledger_list:0")],
            [InlineKeyboardButton(text="🎁 Лише ручні (адмін)", callback_data="ledger_admin:0")],
            [InlineKeyboardButton(text="⚠️ Незавершені / помилки", callback_data="ledger_bad:0")],
            [InlineKeyboardButton(text="🏷 Фільтр за типом", callback_data="ledger_reasons")],
            [InlineKeyboardButton(text="📊 Excel журналу", callback_data="ledger_export")],
            [InlineKeyboardButton(text="👤 До клієнтів", callback_data="clients_hub")],
        ]
    )


def get_ledger_list_keyboard(
    *,
    offset: int,
    total: int,
    page_size: int,
    prefix: str = "ledger_list",
    back_cb: str | None = None,
    back_label: str = "◀️ Назад",
) -> InlineKeyboardMarkup:
    """prefix examples: ledger_list | ledger_admin | ledger_bad | ledger_reason:cashback | ledger_user:UID"""
    rows: list[list[InlineKeyboardButton]] = []
    nav: list[InlineKeyboardButton] = []
    if offset > 0:
        prev_off = max(0, offset - page_size)
        nav.append(
            InlineKeyboardButton(
                text="⬅️",
                callback_data=f"{prefix}:{prev_off}",
            )
        )
    page = (offset // page_size) + 1
    pages = max(1, (total + page_size - 1) // page_size)
    nav.append(
        InlineKeyboardButton(text=f"{page}/{pages}", callback_data="ledger_noop")
    )
    if offset + page_size < total:
        nav.append(
            InlineKeyboardButton(
                text="➡️",
                callback_data=f"{prefix}:{offset + page_size}",
            )
        )
    if nav:
        rows.append(nav)
    if back_cb:
        rows.append([InlineKeyboardButton(text=back_label, callback_data=back_cb)])
    rows.append(
        [InlineKeyboardButton(text="🏠 Журнал", callback_data="ledger_hub")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_ledger_reasons_keyboard() -> InlineKeyboardMarkup:
    from database_functions.bonus_ledger_db import ADMIN_FILTER_REASONS, REASON_TITLES_UK

    rows: list[list[InlineKeyboardButton]] = []
    for reason in ADMIN_FILTER_REASONS:
        title = REASON_TITLES_UK.get(reason, reason)
        if len(title) > 40:
            title = title[:39] + "…"
        rows.append(
            [
                InlineKeyboardButton(
                    text=title,
                    callback_data=f"ledger_reason:{reason}:0",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="ledger_hub")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_ledger_op_keyboard(
    op_id: int,
    user_id: int | None,
    *,
    from_client: bool = False,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if user_id:
        rows.append(
            [
                InlineKeyboardButton(
                    text="◀️ До операцій клієнта",
                    callback_data=f"ledger_user:{user_id}:0",
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text="👤 Картка клієнта",
                    callback_data=f"client_view:{user_id}",
                )
            ]
        )
    if from_client:
        rows.append(
            [InlineKeyboardButton(text="🏠 Меню клієнтів", callback_data="clients_hub")]
        )
    else:
        rows.append(
            [InlineKeyboardButton(text="◀️ До списку журналу", callback_data="ledger_list:0")]
        )
        rows.append(
            [InlineKeyboardButton(text="🏠 Журнал", callback_data="ledger_hub")]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_clients_hub_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Усі клієнти", callback_data="clients_list:join_desc:0")],
            [InlineKeyboardButton(text="📊 Excel зі статистикою", callback_data="clients_export_xlsx")],
            [InlineKeyboardButton(text="↕️ Сортування / фільтри", callback_data="clients_sort_menu")],
            [InlineKeyboardButton(text="👥 Хто кого привів", callback_data="clients_refs:0")],
            [InlineKeyboardButton(text="🔎 Пошук клієнта", callback_data="clients_search")],
            [InlineKeyboardButton(text="🆕 Останні зареєстровані", callback_data="clients_recent")],
            [InlineKeyboardButton(text="🚫 З блокуванням Крафтиків", callback_data="clients_blocked")],
            [InlineKeyboardButton(text="⚠️ Аномалії", callback_data="clients_anomalies")],
            [InlineKeyboardButton(text="📒 Журнал Крафтиків", callback_data="ledger_hub")],
        ]
    )


def get_client_card_keyboard(
    user_id: int,
    *,
    blocked: bool,
    nav_label: str | None = None,
    has_prev: bool = False,
    has_next: bool = False,
    back_label: str = "◀️ До списку",
) -> InlineKeyboardMarkup:
    block_btn = (
        InlineKeyboardButton(text="✅ Розблокувати Крафтики", callback_data=f"client_unblock:{user_id}")
        if blocked
        else InlineKeyboardButton(text="🚫 Заблокувати Крафтики", callback_data=f"client_block:{user_id}")
    )
    rows: list[list[InlineKeyboardButton]] = []
    if has_prev or has_next or nav_label:
        nav: list[InlineKeyboardButton] = []
        if has_prev:
            nav.append(InlineKeyboardButton(text="⬅️", callback_data="client_nav:prev"))
        if nav_label:
            nav.append(InlineKeyboardButton(text=nav_label, callback_data="client_nav:noop"))
        if has_next:
            nav.append(InlineKeyboardButton(text="➡️", callback_data="client_nav:next"))
        rows.append(nav)
    rows.extend(
        [
            [
                InlineKeyboardButton(text="📜 Чеки", callback_data=f"client_hist:{user_id}"),
                InlineKeyboardButton(text="📒 Операції", callback_data=f"ledger_user:{user_id}:0"),
            ],
            [
                InlineKeyboardButton(text="♻️ Баланс Poster", callback_data=f"client_bal:{user_id}"),
                InlineKeyboardButton(text="🔄 Оновити", callback_data=f"client_view:{user_id}"),
            ],
            [InlineKeyboardButton(text="👥 Реферали", callback_data=f"client_refs:{user_id}")],
            [
                InlineKeyboardButton(text="🎁 Подарувати", callback_data=f"client_gift:{user_id}"),
                InlineKeyboardButton(text="📈 Кешбек %", callback_data=f"client_cashback:{user_id}"),
            ],
            [block_btn],
            [InlineKeyboardButton(text=back_label, callback_data="clients_back")],
            [InlineKeyboardButton(text="🏠 Меню клієнтів", callback_data="clients_hub")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _client_row_label(u: dict) -> str:
    uid = int(u["user_id"])
    first = (u.get("user_first_name") or "").strip()
    last = (u.get("user_last_name") or "").strip()
    display = (u.get("display_name") or "").strip()
    # Показуємо імʼя+прізвище, щоб було видно чому спрацював пошук
    if first and last:
        name = f"{first} {last}"
    else:
        name = display or first or last or "Клієнт"
    phone = (u.get("user_phone") or "").strip()
    flag = "🚫 " if int(u.get("bonuses_blocked") or 0) else ""
    bits: list[str] = []
    if phone:
        bits.append(phone[-4:] if len(phone) >= 4 else phone)
    try:
        spent = float(u.get("spent_uah") or 0)
        if spent:
            bits.append(f"{spent:g}₴")
    except (TypeError, ValueError):
        pass
    try:
        be = float(u.get("bonus_earned_uah") or 0)
        if be:
            bits.append(f"+{be:g}К")
    except (TypeError, ValueError):
        pass
    if u.get("age") is not None:
        try:
            bits.append(f"{int(u['age'])}р")
        except (TypeError, ValueError):
            pass
    spot_s = (u.get("top_spot") or "").strip()
    if spot_s:
        bits.append(spot_s[:14])
    label = f"{flag}{name}"
    if bits:
        label += " · " + " · ".join(bits)
    if len(label) > 64:
        label = label[:63] + "…"
    return label or str(uid)


def get_client_search_results_keyboard(
    users: list[dict],
    *,
    back: str = "clients_back",
    title_btn: str | None = None,
) -> InlineKeyboardMarkup:
    rows = []
    if title_btn:
        rows.append([InlineKeyboardButton(text=title_btn, callback_data="client_nav:noop")])
    for u in users[:25]:
        uid = int(u["user_id"])
        rows.append(
            [InlineKeyboardButton(text=_client_row_label(u), callback_data=f"client_view:{uid}")]
        )
    rows.append([InlineKeyboardButton(text="🔎 Новий пошук", callback_data="clients_search")])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data=back)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_clients_sort_keyboard(
    *,
    spots: list[str] | None = None,
    products: list[str] | None = None,
) -> InlineKeyboardMarkup:
    from database_functions.clients_admin_db import SORT_LABELS

    spots = [s for s in (spots or []) if s]
    products = [p for p in (products or []) if p]
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"clients_list:{key}:0")]
        for key, label in SORT_LABELS.items()
    ]
    spot_label = "📍 Кавʼярні"
    if spots:
        spot_label += f" · {len(spots)}✓"
    prod_label = "☕ Продукти"
    if products:
        prod_label += f" · {len(products)}✓"
    rows.append(
        [
            InlineKeyboardButton(text=spot_label, callback_data="clients_filter_spot"),
            InlineKeyboardButton(text=prod_label, callback_data="clients_filter_product"),
        ]
    )
    if spots or products:
        rows.append(
            [
                InlineKeyboardButton(
                    text="✅ Показати з фільтрами",
                    callback_data="clients_apply_filters",
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text="🧹 Скинути фільтри",
                    callback_data="clients_clear_filters",
                )
            ]
        )
        for i, name in enumerate(spots[:8]):
            label = (name[:28] + "…") if len(name) > 29 else name
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"✕ 📍 {label}",
                        callback_data=f"clients_rm_spot:{i}",
                    )
                ]
            )
        for i, name in enumerate(products[:8]):
            label = (name[:28] + "…") if len(name) > 29 else name
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"✕ ☕ {label}",
                        callback_data=f"clients_rm_product:{i}",
                    )
                ]
            )
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="clients_hub")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_clients_list_keyboard(
    users: list[dict],
    *,
    sort: str,
    offset: int,
    total: int,
    page_size: int = 10,
) -> InlineKeyboardMarkup:
    rows = []
    page = (offset // page_size) + 1
    pages = max(1, (total + page_size - 1) // page_size)
    rows.append(
        [
            InlineKeyboardButton(
                text=f"Стор. {page}/{pages} · {total}",
                callback_data="client_nav:noop",
            )
        ]
    )
    for u in users:
        uid = int(u["user_id"])
        rows.append(
            [InlineKeyboardButton(text=_client_row_label(u), callback_data=f"client_view:{uid}")]
        )

    nav = []
    if offset > 0:
        prev_off = max(0, offset - page_size)
        nav.append(
            InlineKeyboardButton(text="⬅️", callback_data=f"clients_list:{sort}:{prev_off}")
        )
    if offset + page_size < total:
        nav.append(
            InlineKeyboardButton(
                text="➡️", callback_data=f"clients_list:{sort}:{offset + page_size}"
            )
        )
    if nav:
        rows.append(nav)
    rows.append(
        [
            InlineKeyboardButton(text="↕️ Сортування", callback_data="clients_sort_menu"),
            InlineKeyboardButton(text="🔎 Пошук", callback_data="clients_search"),
        ]
    )
    rows.append(
        [InlineKeyboardButton(text="🧹 Скинути фільтри", callback_data="clients_clear_filters")]
    )
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="clients_hub")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_clients_spot_filter_keyboard(
    spots: list[str],
    *,
    selected: list[str] | None = None,
) -> InlineKeyboardMarkup:
    selected_set = {s for s in (selected or []) if s}
    rows = []
    for i, name in enumerate(spots[:12]):
        mark = "✅ " if name in selected_set else ""
        label = (name[:36] + "…") if len(name) > 37 else name
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{mark}📍 {label}",
                    callback_data=f"clients_spot:{i}",
                )
            ]
        )
    n = len(selected_set)
    rows.append(
        [
            InlineKeyboardButton(
                text=f"✅ Готово" + (f" · {n}" if n else ""),
                callback_data="clients_apply_filters",
            )
        ]
    )
    if n:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🧹 Скинути кавʼярні",
                    callback_data="clients_clear_spots",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="◀️ До фільтрів", callback_data="clients_sort_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_referrals_browse_keyboard(items: list[dict], *, offset: int, has_more: bool) -> InlineKeyboardMarkup:
    rows = []
    for ref in items:
        friend = int(ref.get("friend_user_id") or 0)
        referrer = int(ref.get("referrer_user_id") or 0)
        fname = (ref.get("friend_name") or ref.get("friend_first") or str(friend)).strip()
        rname = (ref.get("referrer_name") or ref.get("referrer_first") or str(referrer)).strip()
        status = (ref.get("status") or "").strip()
        label = f"{rname} → {fname}"
        if status:
            label += f" · {status}"
        label = (label[:58] + "…") if len(label) > 59 else label
        rows.append(
            [
                InlineKeyboardButton(text=label[:28] or "друг", callback_data=f"client_view:{friend}"),
                InlineKeyboardButton(text="← хто", callback_data=f"client_view:{referrer}"),
            ]
        )
    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"clients_refs:{max(0, offset - 10)}"))
    if has_more:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"clients_refs:{offset + 10}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="⏳ На перевірці", callback_data="referral_review_list")])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="clients_hub")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_loyalty_settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Вітальний бонус", callback_data="loyalty_edit:welcome_bonus_uah")],
            [InlineKeyboardButton(text="✏️ Бонус за ДН (профіль)", callback_data="loyalty_edit:birthday_bonus_uah")],
            [InlineKeyboardButton(text="✏️ Щорічний подарунок ДН", callback_data="loyalty_edit:annual_birthday_bonus_uah")],
            [InlineKeyboardButton(text="✏️ Реферал (за друга)", callback_data="loyalty_edit:referral_bonus_uah")],
            [InlineKeyboardButton(text="✏️ Кешбек %", callback_data="loyalty_edit_cashback")],
            [InlineKeyboardButton(text="✏️ Квест: 3 візити", callback_data="loyalty_edit:quest_visits_reward_uah")],
            [InlineKeyboardButton(text="✏️ Квест: напій+їжа", callback_data="loyalty_edit:quest_combo_reward_uah")],
            [InlineKeyboardButton(text="✏️ Квест: 2 напої", callback_data="loyalty_edit:quest_drinks_reward_uah")],
            [InlineKeyboardButton(text="✏️ Досягнення 5 днів", callback_data="loyalty_edit:ach_days_5_reward_uah")],
            [InlineKeyboardButton(text="✏️ Досягнення 15 днів", callback_data="loyalty_edit:ach_days_15_reward_uah")],
            [InlineKeyboardButton(text="✏️ Досягнення 30 днів", callback_data="loyalty_edit:ach_days_30_reward_uah")],
            [InlineKeyboardButton(text="🔄 Оновити", callback_data="loyalty_refresh")],
            [InlineKeyboardButton(text="👥 Реферали на перевірці", callback_data="referral_review_list")],
            [InlineKeyboardButton(text="👤 До клієнтів", callback_data="clients_hub")],
        ]
    )


def get_support_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Змінити контакт", callback_data="loyalty_edit_support")],
        ]
    )


def get_referral_review_keyboard(items: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for ref in items[:20]:
        rid = ref.get("id")
        friend = ref.get("friend_user_id")
        referrer = ref.get("referrer_user_id")
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"✅ #{rid} друг {friend} ← {referrer}",
                    callback_data=f"referral_approve:{rid}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="🔄 Оновити", callback_data="referral_review_list")])
    rows.append([InlineKeyboardButton(text="◀️ Хто кого привів", callback_data="clients_refs:0")])
    rows.append([InlineKeyboardButton(text="🏠 Меню клієнтів", callback_data="clients_hub")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_export_database_keyboard() -> InlineKeyboardMarkup:
    inline_kb_list = [
        [InlineKeyboardButton(text="🔍 Вигрузити Excel", callback_data="export_database")],
        [InlineKeyboardButton(text="♻️ Оновити баланси з Poster", callback_data="stats_refresh_poster")],
        [InlineKeyboardButton(text="⚠️ Аномалії лояльності", callback_data="clients_anomalies")],
        [InlineKeyboardButton(text="💾 Бекап БД зараз", callback_data="backup_db_now")],
        [InlineKeyboardButton(text="👤 До клієнтів", callback_data="clients_hub")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=inline_kb_list)


# BROADCAST KEYBOARD
def get_broadcast_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="Зробити розсилку", callback_data="create_post")],
        [InlineKeyboardButton(text="📊 Історія розсилок", callback_data="mailing_history")],
        [InlineKeyboardButton(text="🎯 Квести / акції", callback_data="quests_admin")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def create_post(user_data: dict, user_id: str, url_buttons: list = None) -> InlineKeyboardMarkup:
    inline_kb_list = []
    data = user_data.get(user_id, {}) if isinstance(user_data, dict) else {}
    url_buttons = url_buttons if url_buttons is not None else data.get("url_buttons")
    track_rows = data.get("track_buttons") or []

    if url_buttons:
        for row in url_buttons:
            inline_kb_list.append([
                InlineKeyboardButton(text=button_text, url=button_url) for button_text, button_url in row
            ])
    if track_rows:
        for row in track_rows:
            inline_kb_list.append(
                [
                    InlineKeyboardButton(
                        text=f"📊 {b.get('label') or b.get('key')}",
                        callback_data="mailing_noop",
                    )
                    for b in row
                ]
            )

    inline_kb_list.append([
        InlineKeyboardButton(text="Медіа", callback_data=f"media_"),
        InlineKeyboardButton(text="Додати опис", callback_data=f"description_")
    ])

    inline_kb_list.append([
        InlineKeyboardButton(text="🔔" if data.get('bell', 0) == 1 else "🔕", callback_data=f"bell_"),
        InlineKeyboardButton(text="URL-кнопки", callback_data=f"url_buttons_")
    ])
    inline_kb_list.append([
        InlineKeyboardButton(text="📊 Кнопки-опитування", callback_data="track_buttons_")
    ])

    inline_kb_list.append([
        InlineKeyboardButton(text="← Відміна", callback_data=f"back_to"),
        InlineKeyboardButton(text="Далі →", callback_data=f"nextmailing_")
    ])

    return InlineKeyboardMarkup(inline_keyboard=inline_kb_list)


def get_mailing_audience_keyboard(data: dict | None = None) -> InlineKeyboardMarkup:
    data = data or {}
    audience = data.get("audience") or "all"
    spots = data.get("audience_spots") or []
    products = data.get("audience_products") or []
    days_min = data.get("audience_days_min")
    days_max = data.get("audience_days_max")

    def mark(key: str) -> str:
        return "✅ " if audience == key else ""

    spot_label = "📍 Кавʼярні"
    if spots:
        spot_label += f" · {len(spots)}"
    prod_label = "☕ Напої / десерти"
    if products:
        prod_label += f" · {len(products)}"
    days_label = "⏱ Час у програмі"
    if days_min is not None or days_max is not None:
        lo = days_min if days_min is not None else "…"
        hi = days_max if days_max is not None else "…"
        days_label += f" · {lo}–{hi} дн."

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"{mark('all')}Усім підписаним", callback_data="mail_aud:all")],
            [InlineKeyboardButton(text=f"{mark('test')}🧪 Тест (адміни)", callback_data="mail_aud:test")],
            [InlineKeyboardButton(text=f"{mark('segment')}🎯 Сегмент (фільтри)", callback_data="mail_aud:segment")],
            [
                InlineKeyboardButton(text=spot_label, callback_data="mail_aud_spots"),
                InlineKeyboardButton(text=prod_label, callback_data="mail_aud_products"),
            ],
            [InlineKeyboardButton(text=days_label, callback_data="mail_aud_days")],
            [InlineKeyboardButton(text="🧹 Скинути фільтри", callback_data="mail_aud_clear")],
            [InlineKeyboardButton(text="→ До підтвердження", callback_data="mail_aud_done")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to")],
        ]
    )


def publish_post() -> InlineKeyboardMarkup:
    inline_kb_list = [
        [InlineKeyboardButton(text="💈 Опублікувати", callback_data=f"publish_")],
        [InlineKeyboardButton(text="← Назад", callback_data=f"back_to")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=inline_kb_list)


def confirm_mailing() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="✓ Так", callback_data=f"confirm_publish_")],
        [InlineKeyboardButton(text="❌ Ні", callback_data="cancel_publish")]  
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def back_mailing_keyboard() -> InlineKeyboardMarkup:
    inline_kb_list = [
        [InlineKeyboardButton(text="Назад", callback_data="back_to_my_post")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=inline_kb_list)

def post_keyboard(
    user_data: dict,
    user_id: str,
    url_buttons: list = None,
    *,
    track_buttons: list | None = None,
    job_id: int | None = None,
) -> InlineKeyboardMarkup | None:
    """Buttons under a broadcast post. Unsubscribe is only in client «ℹ️ Інфо»."""
    inline_kb_list = []
    data = user_data.get(user_id, {}) if isinstance(user_data, dict) else {}
    url_buttons = url_buttons if url_buttons is not None else data.get("url_buttons")
    track_buttons = (
        track_buttons if track_buttons is not None else data.get("track_buttons")
    )
    if url_buttons:
        for row in url_buttons:
            inline_kb_list.append(
                [
                    InlineKeyboardButton(text=button_text, url=button_url)
                    for button_text, button_url in row
                ]
            )
    if track_buttons and job_id is not None:
        for row in track_buttons:
            inline_kb_list.append(
                [
                    InlineKeyboardButton(
                        text=b.get("label") or b.get("key") or "·",
                        callback_data=f"mb:{int(job_id)}:{b.get('key')}",
                    )
                    for b in row
                    if b.get("key")
                ]
            )
    elif track_buttons:
        # Preview during compose (non-clickable look-alike)
        for row in track_buttons:
            inline_kb_list.append(
                [
                    InlineKeyboardButton(
                        text=f"📊 {b.get('label') or b.get('key')}",
                        callback_data="mailing_noop",
                    )
                    for b in row
                ]
            )
    return InlineKeyboardMarkup(inline_keyboard=inline_kb_list) if inline_kb_list else None


def mailing_job_history_keyboard(jobs: list[dict]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for job in jobs[:12]:
        jid = int(job["id"])
        status = job.get("status") or "?"
        sent = int(job.get("sent") or 0)
        total = int(job.get("total") or 0)
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"#{jid} · {sent}/{total} · {status}",
                    callback_data=f"mailing_job:{jid}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_posts")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def quests_admin_keyboard(campaigns: list[dict]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for c in campaigns[:15]:
        cid = int(c["id"])
        status = c.get("status") or "?"
        title = (c.get("title") or c.get("key") or f"#{cid}")[:40]
        mark = {"active": "🟢", "draft": "⚪", "ended": "⚫"}.get(status, "·")
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{mark} {title}",
                    callback_data=f"quest_camp:{cid}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_posts")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def quest_campaign_actions_keyboard(campaign: dict) -> InlineKeyboardMarkup:
    cid = int(campaign["id"])
    status = campaign.get("status") or ""
    rows: list[list[InlineKeyboardButton]] = []
    if status != "active":
        rows.append(
            [InlineKeyboardButton(text="▶️ Запустити", callback_data=f"quest_camp_on:{cid}")]
        )
    if status == "active":
        rows.append(
            [InlineKeyboardButton(text="⏹ Зупинити", callback_data=f"quest_camp_off:{cid}")]
        )
    rows.append(
        [InlineKeyboardButton(text="📊 Статистика", callback_data=f"quest_camp_stats:{cid}")]
    )
    rows.append([InlineKeyboardButton(text="◀️ До списку", callback_data="quests_admin")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# LINKS KEYBOARD
def get_links_keyboard() -> InlineKeyboardMarkup:
    keyboard = []
    links = get_all_links()
    
    for link in links:
        keyboard.append([
            InlineKeyboardButton(
                text=f"{link[1]} ({link[3]} переходів)",
                callback_data=f"link_stats_{link[0]}"
            )
        ])
    
    keyboard.append([
        InlineKeyboardButton(
            text="➕ Додати посилання",
            callback_data="add_link"
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)



def cancel_button() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="Скасувати")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def get_link_stats_keyboard(link_id: int) -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton(text="✏️ Редагувати", callback_data=f"edit_link_{link_id}"),
            InlineKeyboardButton(text="🗑 Видалити", callback_data=f"delete_link_{link_id}")
        ],
        [InlineKeyboardButton(text="🔄 Оновити", callback_data=f"link_stats_{link_id}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_links")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_delete_link_confirm_keyboard(link_id: int) -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton(text="✅ Так", callback_data=f"confirm_delete_{link_id}"),
            InlineKeyboardButton(text="❌ Ні", callback_data="back_to_links")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


# ADMINISTRATORS KEYBOARD
def get_admin_list_keyboard(admins: list = None, is_super: bool = False) -> InlineKeyboardMarkup:
    if admins is None:
        admins = get_all_admins()
    
    keyboard = []
    
    for admin in admins:
        user_id = admin[0]
        username = admin[1]
        is_superadmin = admin[3]
        admin_user_name = admin[5] if len(admin) > 5 else None

        display_username = username or admin_user_name or f"ID: {user_id}"
        
        display_name = f"👑 {display_username}" if is_superadmin else f"👤 {display_username}"
        
        # Superadmin can transfer rights and remove regular admins
        if not is_superadmin and is_super:
            keyboard.append([
                InlineKeyboardButton(text=display_name, callback_data=f"admin_info_{user_id}"),
                InlineKeyboardButton(text="👑", callback_data=f"admin_transfer_super_ask_{user_id}"),
                InlineKeyboardButton(text="❌", callback_data=f"admin_remove_id_{user_id}"),
            ])
        else:
            keyboard.append([
                InlineKeyboardButton(text=display_name, callback_data=f"admin_info_{user_id}")
            ])
    

    keyboard.append([
        InlineKeyboardButton(text="➕ Додати адміна", callback_data="admin_add_new")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_cancel_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="❌ Скасувати", callback_data="admin_cancel")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_transfer_super_confirm_keyboard(target_user_id: int) -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton(
                text="✅ Так, передати",
                callback_data=f"admin_transfer_super_yes_{target_user_id}",
            ),
            InlineKeyboardButton(text="❌ Ні", callback_data="admin_transfer_super_no"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
