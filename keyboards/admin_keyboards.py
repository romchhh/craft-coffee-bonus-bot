from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, KeyboardButton, ReplyKeyboardMarkup
from database_functions.admin_db import get_all_admins
from database_functions.links_db import get_all_links


# MAIN KEYBOARD
def admin_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="Розсилка"), KeyboardButton(text="Статистика")],
        [KeyboardButton(text="Адміністратори"), KeyboardButton(text="Посилання")],
        [KeyboardButton(text="🎁 Лояльність"), KeyboardButton(text="👥 Реферали")],
        [KeyboardButton(text="Головне меню")],
    ]

    keyboard = ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)
    return keyboard


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
        [InlineKeyboardButton(text="🔍 Вигрузити БД", callback_data="export_database")]
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
    inline_kb_list = []
    if url_buttons:
        for row in url_buttons:
            inline_kb_list.append([InlineKeyboardButton(text=button_text, url=button_url) for button_text, button_url in row])

    return InlineKeyboardMarkup(inline_keyboard=inline_kb_list)


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
