from aiogram.fsm.state import State, StatesGroup


class Mailing(StatesGroup):
    content = State()
    media = State()
    description = State()
    url_buttons = State()


class LinkStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_edit_name = State()


class AdminManagement(StatesGroup):
    waiting_for_admin_username = State()
    waiting_for_admin_id = State()
    waiting_for_admin_removal = State()


class LoyaltySettings(StatesGroup):
    welcome_bonus = State()
    cashback_percent = State()
    edit_reward = State()
