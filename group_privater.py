import asyncio
from datetime import datetime, timedelta
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import UpdateUsernameRequest
from telethon.tl.types import PeerChannel
from config import API_ID, API_HASH
from db import get_session

scheduled_tasks = {}

async def schedule_group_privacy(user_id, group_username, start_time_str, end_time_str, repeat=False, bot=None):
    session_string = get_session(user_id)
    if not session_string:
        return "❌ Session not found. Please login first using /start."

    client = TelegramClient(StringSession(session_string), int(API_ID), API_HASH)
    await client.connect()

    try:
        entity = await client.get_entity(f"@{group_username}")
        channel_id = entity.id
        access_hash = entity.access_hash
        peer = PeerChannel(channel_id)
        old_username = entity.username or group_username
    except Exception as e:
        return f"❌ Failed to fetch group info: {e}"

    try:
        now = datetime.now()
        start_time = datetime.strptime(start_time_str, "%H:%M").replace(year=now.year, month=now.month, day=now.day)
        end_time = datetime.strptime(end_time_str, "%H:%M").replace(year=now.year, month=now.month, day=now.day)

        if start_time <= now:
            start_time += timedelta(days=1)

        if end_time <= start_time:
            end_time += timedelta(days=1)

        wait_seconds_start = (start_time - now).total_seconds()
        wait_seconds_end = (end_time - now).total_seconds()

        async def run_once():
            await asyncio.sleep(wait_seconds_start)

            try:
                current = await client.get_entity(peer)
                if current.username:
                    await client(UpdateUsernameRequest(channel=peer, username=""))
                    print(f"[PRIVATE] Group @{group_username} made private.")
                    if bot:
                        await bot.send_message(user_id, f"✅ Group @{group_username} is now private. Username removed.")
                else:
                    print("[SKIP] Already private")
            except Exception as e:
                print(f"[ERROR] Making private failed: {e}")
                if bot:
                    await bot.send_message(user_id, f"❌ Failed to make group private: {e}")

            await asyncio.sleep(wait_seconds_end - wait_seconds_start)

            try:
                current = await client.get_entity(peer)
                if current.username != old_username:
                    await client(UpdateUsernameRequest(channel=peer, username=old_username))
                    print(f"[PUBLIC] Restored to @{old_username}")
                    if bot:
                        await bot.send_message(user_id, f"🔁 Timer ended. Group is now public with username @{old_username}")
                else:
                    print("[SKIP] Username already correct")
            except Exception as e:
                print(f"[ERROR] Restore failed: {e}")
                if bot:
                    await bot.send_message(user_id, f"❌ Failed to restore username: {e}")

            await client.disconnect()

        async def daily_loop():
            while True:
                await run_once()
                await asyncio.sleep(86400)

        task = asyncio.create_task(daily_loop() if repeat else run_once())
        scheduled_tasks[user_id] = task
        return f"✅ Group @{group_username} will go private at {start_time_str} and public at {end_time_str}.{f' (Repeats Daily)' if repeat else ''}"

    except Exception as e:
        return f"❌ Error scheduling task: {e}"
