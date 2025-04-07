import os
from telethon.sync import TelegramClient

# ✅ Shared sessions folder used by both bots
SESSIONS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "sessions"))
os.makedirs(SESSIONS_DIR, exist_ok=True)

# Cache for active OTP sessions
sessions_cache = {}

# 📤 Send OTP
async def send_otp_code(user_id, api_id, api_hash, phone):
    try:
        session_path = os.path.join(SESSIONS_DIR, f"{phone}")
        client = TelegramClient(session_path, int(api_id), api_hash)
        await client.connect()
        sent = await client.send_code_request(phone)
        sessions_cache[user_id] = client
        return sent
    except Exception as e:
        print(f"[ERROR] send_otp_code: {e}")
        return False

# ✅ Confirm OTP
async def confirm_otp_code(user_id, code, state, bot):
    client = sessions_cache.get(user_id)
    if not client:
        return False
    try:
        await client.sign_in(code=code)
        await client.disconnect()
        return True
    except Exception as e:
        await bot.send_message(user_id, f"❌ OTP Error: {e}")
        return False

# 🔐 Confirm 2FA
async def confirm_2fa_password(user_id, password, state, bot):
    client = sessions_cache.get(user_id)
    if not client:
        return False
    try:
        await client.sign_in(password=password)
        await client.disconnect()
        return True
    except Exception as e:
        await bot.send_message(user_id, f"❌ 2FA Error: {e}")
        return False
