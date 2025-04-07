import asyncio
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import UsernameInvalidError, UsernameOccupiedError
from telethon.tl.functions.channels import UpdateUsernameRequest
from db import get_session
from config import API_ID, API_HASH

# Track active changers
active_changers = {}

async def changer_loop(user_id, group_username, usernames, interval, session_str):
    try:
        client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
        await client.connect()
        entity = await client.get_entity(f"@{group_username}")

        while active_changers.get(user_id):
            for username in usernames:
                if not active_changers.get(user_id):
                    break
                try:
                    await client(UpdateUsernameRequest(entity, username))
                    print(f"[{user_id}] Changed to @{username}")
                except (UsernameInvalidError, UsernameOccupiedError):
                    print(f"[{user_id}] Failed to change to @{username}")
                await asyncio.sleep(interval)

        await client.disconnect()
    except Exception as e:
        print(f"[Changer Error] {e}")

async def start_username_changer(user_id, group_username, usernames, interval):
    session_str = get_session(user_id)
    if not session_str:
        return "❌ Session not found. Please log in again."

    if active_changers.get(user_id):
        return "⚠️ Username changer already running."

    active_changers[user_id] = True
    asyncio.create_task(changer_loop(user_id, group_username, usernames, interval, session_str))
    return f"✅ Started username changer for @{group_username}."

async def stop_username_changer(user_id):
    if user_id in active_changers:
        active_changers[user_id] = False
        return "🛑 Username changer stopped."
    return "⚠️ No active changer running."

# ✅ Export to status.py for live tracking
running_tasks = active_changers
