from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, KeyboardButton, ReplyKeyboardMarkup
from database_functions.admin_db import get_all_admins
from database_functions.links_db import get_all_links


# MAIN KEYBOARD
def admin_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="Розсилка"), KeyboardButton(text="Статистика")],
        [KeyboardButton(text="👤 Клієнти"), KeyboardButton(text="👥 Реферали")],
        [KeyboardButton(text="Адміністратори"), KeyboardButton(text="Посилання")],
        [KeyboardButton(text="🎁 Лояльність"), KeyboardButton(text="💬 Контакт підтримки")],
        [KeyboardButton(text="🍽 Меню"), KeyboardButton(text="📍 Точки")],
        [KeyboardButton(text="Головне меню")],
    ]

    keyboard = ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
    return keyboard


def get_clients_hub_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Усі клієнти", callback_data="clients_list:join_desc:0")],
            [InlineKeyboardButton(text="↕️ Сортування / фільтри", callback_data="clients_sort_menu")],
            [InlineKeyboardButton(text="👥 Хто кого привів", callback_data="clients_refs:0")],
            [InlineKeyboardButton(text="🔎 Пошук клієнта", callback_data="clients_search")],
            [InlineKeyboardButton(text="🆕 Останні зареєстровані", callback_data="clients_recent")],
            [InlineKeyboardButton(text="🚫 З блокуванням Крафтиків", callback_data="clients_blocked")],
            [InlineKeyboardButton(text="⚠️ Аномалії", callback_data="clients_anomalies")],
        ]
    )


def get_client_card_keyboard(user_id: int, *, blocked: bool) -> InlineKeyboardMarkup:
    block_btn = (
        InlineKeyboardButton(text="✅ Розблокувати Крафтики", callback_data=f"client_unblock:{user_id}")
        if blocked
        else InlineKeyboardButton(text="🚫 Заблокувати Крафтики", callback_data=f"client_block:{user_id}")
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📜 Історія покупок", callback_data=f"client_hist:{user_id}"),
                InlineKeyboardButton(text="🔄 Оновити", callback_data=f"client_view:{user_id}"),
            ],
            [InlineKeyboardButton(text="👥 Реферали клієнта", callback_data=f"client_refs:{user_id}")],
            [InlineKeyboardButton(text="🎁 Подарувати Крафтики", callback_data=f"client_gift:{user_id}")],
            [block_btn],
            [InlineKeyboardButton(text="◀️ До клієнтів", callback_data="clients_hub")],
        ]
    )


def get_client_search_results_keyboard(users: list[dict], *, back: str = "clients_hub") -> InlineKeyboardMarkup:
    rows = []
    for u in users[:12]:
        uid = int(u["user_id"])
        name = (u.get("display_name") or u.get("user_first_name") or "Клієнт").strip()
        phone = (u.get("user_phone") or "").strip()
        flag = "🚫 " if int(u.get("bonuses_blocked") or 0) else ""
        extra_bits = []
        if u.get("spent_uah") is not None:
            try:
                spent = float(u.get("spent_uah") or 0)
                if spent > 0:
                    extra_bits.append(f"{spent:g}₴")
            except (TypeError, ValueError):
                pass
        if u.get("bonus_earned_uah") is not None:
            try:
                be = float(u.get("bonus_earned_uah") or 0)
                if be > 0:
                    extra_bits.append(f"+{be:g}К")
            except (TypeError, ValueError):
                pass
        if u.get("age") is not None:
            extra_bits.append(f"{int(u['age'])}р")
        label = f"{flag}{name}"
        if phone:
            label += f" · {phone[-4:]}"
        if extra_bits:
            label += " · " + " · ".join(extra_bits)
        label = (label[:60] + "…") if len(label) > 61 else label
        rows.append([InlineKeyboardButton(text=label, callback_data=f"client_view:{uid}")])
    rows.append([InlineKeyboardButton(text="🔎 Новий пошук", callback_data="clients_search")])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data=back)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_clients_sort_keyboard() -> InlineKeyboardMarkup:
    from database_functions.clients_admin_db import SORT_LABELS

    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"clients_list:{key}:0")]
        for key, label in SORT_LABELS.items()
    ]
    rows.append([InlineKeyboardButton(text="📍 Фільтр: кавʼярня", callback_data="clients_filter_spot")])
    rows.append([InlineKeyboardButton(text="☕ Фільтр: продукт", callback_data="clients_filter_product")])
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
    for u in users:
        uid = int(u["user_id"])
        name = (u.get("display_name") or u.get("user_first_name") or "Клієнт").strip()
        flag = "🚫 " if int(u.get("bonuses_blocked") or 0) else ""
        bits = []
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
            bits.append(f"{int(u['age'])}р")
        spot_s = (u.get("top_spot") or "").strip()
        if spot_s:
            bits.append(spot_s[:18])
        label = f"{flag}{name}"
        if bits:
            label += " · " + " · ".join(bits)
        label = (label[:60] + "…") if len(label) > 61 else label
        rows.append([InlineKeyboardButton(text=label, callback_data=f"client_view:{uid}")])

    nav = []
    if offset > 0:
        prev_off = max(0, offset - page_size)
        nav.append(
            InlineKeyboardButton(text="◀️", callback_data=f"clients_list:{sort}:{prev_off}")
        )
    if offset + page_size < total:
        nav.append(
            InlineKeyboardButton(
                text="▶️", callback_data=f"clients_list:{sort}:{offset + page_size}"
            )
        )
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="↕️ Сортування", callback_data="clients_sort_menu")])
    rows.append(
        [InlineKeyboardButton(text="🧹 Скинути фільтри", callback_data="clients_clear_filters")]
    )
    rows.append([InlineKeyboardButton(text="◀️ До клієнтів", callback_data="clients_hub")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_clients_spot_filter_keyboard(spots: list[str]) -> InlineKeyboardMarkup:
    rows = []
    for i, name in enumerate(spots[:12]):
        label = (name[:40] + "…") if len(name) > 41 else name
        rows.append(
            [InlineKeyboardButton(text=f"📍 {label}", callback_data=f"clients_spot:{i}")]
        )
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="clients_sort_menu")])
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
    rows.append([InlineKeyboardButton(text="◀️ До клієнтів", callback_data="clients_hub")])
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
    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_export_database_keyboard() -> InlineKeyboardMarkup:
    inline_kb_list = [
        [InlineKeyboardButton(text="🔍 Вигрузити Excel", callback_data="export_database")],
        [InlineKeyboardButton(text="⚠️ Аномалії лояльності", callback_data="clients_anomalies")],
        [InlineKeyboardButton(text="💾 Бекап БД зараз", callback_data="backup_db_now")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=inline_kb_list)


# BROADCAST KEYBOARD
def get_broadcast_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="Зробити розсилку", callback_data="create_post")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def create_post(user_data: dict, user_id: str, url_buttons: list = None) -> InlineKeyboardMarkup:
    inline_kb_list = []
    
    if url_buttons:
        for row in url_buttons:
            inline_kb_list.append([
                InlineKeyboardButton(text=button_text, url=button_url) for button_text, button_url in row
            ])

    inline_kb_list.append([
        InlineKeyboardButton(text="Медіа", callback_data=f"media_"),
        InlineKeyboardButton(text="Додати опис", callback_data=f"description_")
    ])

    inline_kb_list.append([
        InlineKeyboardButton(text="🔔" if user_data.get(user_id, {}).get('bell', 0) == 1 else "🔕", callback_data=f"bell_"),
        InlineKeyboardButton(text="URL-кнопки", callback_data=f"url_buttons_")
    ])

    

    inline_kb_list.append([
        InlineKeyboardButton(text="← Відміна", callback_data=f"back_to"),
        InlineKeyboardButton(text="Далі →", callback_data=f"nextmailing_")
    ])

    return InlineKeyboardMarkup(inline_keyboard=inline_kb_list)


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

def post_keyboard(user_data: dict, user_id: str, url_buttons: list = None) -> InlineKeyboardMarkup:
    """Buttons under a broadcast post. Unsubscribe is only in client «ℹ️ Інфо»."""
    inline_kb_list = []
    if url_buttons:
        for row in url_buttons:
            inline_kb_list.append(
                [
                    InlineKeyboardButton(text=button_text, url=button_url)
                    for button_text, button_url in row
                ]
            )
    return InlineKeyboardMarkup(inline_keyboard=inline_kb_list) if inline_kb_list else None


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
