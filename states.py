from aiogram.dispatcher.filters.state import State, StatesGroup

class LoginState(StatesGroup):
    waiting_for_api_id = State()
    waiting_for_api_hash = State()
    waiting_for_phone = State()
    waiting_for_otp = State()
    waiting_for_2fa = State()
