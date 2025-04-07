import os
import asyncio
import random
import socks
from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import JoinChannelRequest, LeaveChannelRequest
from telethon.tl.functions.account import ReportPeerRequest
from telethon.tl.types import (
    InputReportReasonSpam, InputReportReasonViolence, InputReportReasonPornography,
    InputReportReasonChildAbuse, InputReportReasonOther
)
from db import get_all_sessions, delete_session_by_string, is_admin, save_user_proxies_to_db, get_user_proxies_from_db
from config import API_ID, API_HASH, ADMIN_ID
from db import get_all_user_proxies

def load_proxies_from_db():
    all_proxies = get_all_user_proxies()
    for user_id, proxies in all_proxies.items():
        user_proxies[user_id] = proxies

reporting_tasks = {}
targets = {}
selected_reasons = {}
joined_once = set()
user_proxies = {}
proxy_index_map = {}      # session_uid → proxy_index
proxy_used_indexes = {}   # user_id → set of used indexes

class ReportStates(StatesGroup):
    waiting_for_target = State()

def get_random_device_info():
    device_models = ["iPhone 13", "iPhone 14 Pro", "Samsung S22", "Pixel 6", "Xiaomi 12", "OnePlus 10"]
    system_versions = ["iOS 16.4", "iOS 16.5", "Android 12", "Android 13", "MIUI 14"]
    app_versions = ["9.5.1", "9.6.2", "9.4.3", "9.3.1"]
    return {
        "device_model": random.choice(device_models),
        "system_version": random.choice(system_versions),
        "app_version": random.choice(app_versions),
        "lang_code": "en",
        "system_lang_code": "en-US"
    }

def get_safe_client(session_str=None, user_id=None, session_uid=None):
    device_info = get_random_device_info()
    proxy = None

    if hasattr(get_safe_client, "proxy_mode") and get_safe_client.proxy_mode:
        proxies = user_proxies.get(user_id, [])
        if proxies:
            if user_id not in proxy_used_indexes:
                proxy_used_indexes[user_id] = set()

            if session_uid not in proxy_index_map:
                unused = [i for i in range(len(proxies)) if i not in proxy_used_indexes[user_id]]
                if not unused:
                    proxy_used_indexes[user_id] = set()
                    unused = list(range(len(proxies)))
                chosen = random.choice(unused)
                proxy_index_map[session_uid] = chosen
                proxy_used_indexes[user_id].add(chosen)

            proxy_data = proxies[proxy_index_map[session_uid]]
            proxy_type, ip, port, user, passwd = proxy_data
            proxy = (socks.SOCKS5, ip, int(port), bool(user), user, passwd)

    return TelegramClient(
        StringSession(session_str) if session_str else StringSession(),
        API_ID,
        API_HASH,
        device_model=device_info["device_model"],
        system_version=device_info["system_version"],
        app_version=device_info["app_version"],
        lang_code=device_info["lang_code"],
        system_lang_code=device_info["system_lang_code"],
        proxy=proxy
    )




reasons_map = {
    "Spam": InputReportReasonSpam(),
    "Violence": InputReportReasonViolence(),
    "Pornography": InputReportReasonPornography(),
    "Child Abuse": InputReportReasonChildAbuse(),
    "Other": InputReportReasonOther()
}

def get_reason_buttons(selected):
    buttons = [
        InlineKeyboardButton(f"{'✅' if r in selected else '☑️'} {r}", callback_data=f"toggle_{r}")
        for r in reasons_map.keys()
    ]
    buttons.append(InlineKeyboardButton("🚀 Confirm", callback_data="confirm"))
    return InlineKeyboardMarkup(row_width=2).add(*buttons)

def register_report_handlers(dp):
    @dp.message_handler(commands=["add_proxy"])
    async def add_proxy_cmd(message: types.Message):
        if not is_admin(message.from_user.id):
            return await message.reply("❌ Only admins can use this.")
        text = message.text.replace("/add_proxy", "").strip()
        if not text:
            return await message.reply("📥 Send proxies in format:\n`ip:port` or `ip:port:user:pass`", parse_mode="Markdown")
        lines = text.splitlines()
        proxy_list = []
        for line in lines:
            parts = line.strip().split(":")
            if len(parts) == 2:
                ip, port = parts
                proxy_list.append(("socks5", ip, int(port), None, None))
            elif len(parts) == 4:
                ip, port, user, passwd = parts
                proxy_list.append(("socks5", ip, int(port), user, passwd))
        if not proxy_list:
            return await message.reply("⚠️ No valid proxies found.")
        user_proxies[message.from_user.id] = proxy_list
        save_user_proxies_to_db(message.from_user.id, proxy_list)
        await message.reply(f"✅ Added {len(proxy_list)} proxies.")

    @dp.message_handler(commands=["view_proxies"])
    async def view_proxy_cmd(message: types.Message):
        if not is_admin(message.from_user.id):
            return await message.reply("❌ Only admins can use this.")
        proxies = user_proxies.get(message.from_user.id, [])
        if not proxies:
            return await message.reply("⚠️ No proxies found.")
        text = "\n".join([f"{p[1]}:{p[2]}" + (f":{p[3]}:{p[4]}" if p[3] else "") for p in proxies])
        await message.reply(f"🧾 Your Proxies:\n\n{text}")

    @dp.message_handler(commands=["clear_proxies"])
    async def clear_proxy_cmd(message: types.Message):
        if not is_admin(message.from_user.id):
            return await message.reply("❌ Only admins can use this.")
        user_proxies.pop(message.from_user.id, None)
        save_user_proxies_to_db(message.from_user.id, [])
        await message.reply("✅ Proxies cleared.")

    @dp.message_handler(commands=["check_sessions"])
    async def check_sessions_cmd(message: types.Message):
        if not is_admin(message.from_user.id):
            return await message.reply("❌ Sirf admin check kar sakta hai.")
        sessions = get_all_sessions()
        if not sessions:
            return await message.reply("⚠️ Koi session nahi mila.")
        valid = []
        dead = []
        for uid, session_str in sessions:
            try:
                client = get_safe_client(session_str, message.from_user.id)
                await client.connect()
                if await client.is_user_authorized():
                    valid.append(uid)
                else:
                    raise Exception("Not authorized")
                await client.disconnect()
            except Exception as e:
                dead.append((uid, str(e)))
        msg = f"🟢 Valid: {len(valid)}\n🔴 Dead: {len(dead)}\n\n"
        if dead:
            msg += "❌ Dead UIDs:\n" + "\n".join([f"`{uid}` → {err}" for uid, err in dead])
            msg += "\n\n🧹 Delete with: `/delete_session <uid>`"
        await message.reply(msg, parse_mode="Markdown")

    @dp.message_handler(commands=["delete_session"])
    async def delete_session_cmd(message: types.Message):
        if not is_admin(message.from_user.id):
            return await message.reply("❌ Only admin can delete session.")
        try:
            uid = message.text.split(" ", 1)[1].strip()
        except IndexError:
            return await message.reply("⚠️ Usage: /delete_session <uid>")
        session_file = f"username_changer_bot/sessions/{uid}.session"
        deleted = False
        if os.path.exists(session_file):
            os.remove(session_file)
            deleted = True
        if delete_session_by_string(uid):
            deleted = True
        if deleted:
            await message.reply(f"✅ Session `{uid}` deleted.", parse_mode="Markdown")
        else:
            await message.reply(f"⚠️ Session `{uid}` not found.", parse_mode="Markdown")

    @dp.message_handler(commands=["start_report"])
    async def start_report_cmd(message: types.Message):
        if not is_admin(message.from_user.id):
            return await message.reply("❌ Only admins can use this command.")
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton("✅ Use Proxy", callback_data="use_proxy_yes"),
            InlineKeyboardButton("❌ No Proxy", callback_data="use_proxy_no")
        )
        await message.reply("⚙️ Use proxy for reporting?", reply_markup=keyboard)

    @dp.callback_query_handler(lambda c: c.data.startswith("use_proxy_"))
    async def proxy_decision(call: types.CallbackQuery):
        user_id = call.from_user.id
        use_proxy = call.data == "use_proxy_yes"
        get_safe_client.proxy_mode = use_proxy
        await call.message.edit_text("🎯 Send the @username or ID to report:")
        await ReportStates.waiting_for_target.set()

    @dp.message_handler(state=ReportStates.waiting_for_target)
    async def receive_target(message: types.Message, state: FSMContext):
        targets[message.from_user.id] = message.text.strip()
        selected_reasons[message.from_user.id] = set()
        await message.reply("☑️ Choose reasons to report:", reply_markup=get_reason_buttons(set()))
        await state.finish()

    @dp.callback_query_handler(lambda c: c.data.startswith("toggle_") or c.data == "confirm")
    async def reason_selection(call: types.CallbackQuery):
        user_id = call.from_user.id
        if user_id not in selected_reasons:
            return await call.answer("❌ Use /start_report first.")
        if call.data == "confirm":
            reasons = list(selected_reasons[user_id])
            if not reasons:
                return await call.answer("⚠️ Select at least one reason.")
            await call.message.edit_text("🚀 Reporting started...")
            await start_mass_report(user_id, targets[user_id], reasons, call.bot)
            return await call.answer()
        reason = call.data.replace("toggle_", "")
        if reason in selected_reasons[user_id]:
            selected_reasons[user_id].remove(reason)
        else:
            selected_reasons[user_id].add(reason)
        await call.message.edit_reply_markup(reply_markup=get_reason_buttons(selected_reasons[user_id]))
        await call.answer()

def register_stop_handler(dp):
    @dp.message_handler(commands=["stop_report"])
    async def stop_report_cmd(message: types.Message):
        user_id = message.from_user.id
        if not is_admin(user_id):
            return await message.reply("❌ Only admins can stop reporting.")
        if user_id in reporting_tasks and reporting_tasks[user_id]:
            for client, task in reporting_tasks[user_id]:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                await client.disconnect()
            reporting_tasks.pop(user_id)
            await message.reply("🛑 Reporting stopped.")
        else:
            await message.reply("⚠️ No active reporting.")

async def start_mass_report(user_id, target, reasons, bot):
    sessions = get_all_sessions()
    if not sessions:
        await bot.send_message(user_id, "❌ No sessions available.")
        return

    valid_sessions = []
    dead_sessions = []

    for uid, session_str in sessions:
        try:
            client = get_safe_client(session_str, user_id, session_uid=uid)

            await client.connect()
            if await client.is_user_authorized():
                valid_sessions.append((uid, session_str))
                await client.disconnect()
            else:
                raise Exception("Not authorized")
        except Exception as e:
            dead_sessions.append((uid, str(e)))

    if dead_sessions:
        msg = "🔴 Dead Sessions:\n"
        for uid, err in dead_sessions:
            msg += f"❌ {uid} → {err}\n"
        msg += "\nUse `/delete_session <uid>` to remove manually."
        await bot.send_message(ADMIN_ID, msg)

    if not valid_sessions:
        return await bot.send_message(user_id, "⚠️ No valid sessions to report.")

    for uid, session_str in valid_sessions:
        try:
            client = get_safe_client(session_str, user_id, session_uid=uid)

            await client.connect()
            me = await client.get_me()
            uname = me.username or me.first_name or str(uid)
            if session_str not in joined_once:
                try:
                    entity = await client.get_entity(target)
                    await client(JoinChannelRequest(entity))
                    await asyncio.sleep(2)
                    await client(ReportPeerRequest(peer=entity, reason=random.choice([reasons_map[r] for r in reasons]), message="Reported"))
                    await asyncio.sleep(2)
                    await client(LeaveChannelRequest(entity))
                    proxy_text = ""
                    if getattr(get_safe_client, "proxy_mode", False):
                        proxies = user_proxies.get(user_id, [])
                        proxy_data = random.choice(proxies)

                    if proxy_data:
                        ip, port = proxy_data[1], proxy_data[2]
                        userpass = f":{proxy_data[3]}:{proxy_data[4]}" if proxy_data[3] else ""
                        proxy_text = f"\n🌐 Used Proxy: {ip}:{port}{userpass}"

                    await bot.send_message(user_id, f"✅ {uname} joined, reported & left {target}{proxy_text}")

                    joined_once.add(session_str)
                except Exception as e:
                    await bot.send_message(user_id, f"⚠️ {uname} couldn't join/report: {e}")
            task = asyncio.create_task(report_loop(client, target, user_id, uname, reasons, session_str, bot))
            if user_id not in reporting_tasks:
                reporting_tasks[user_id] = []
            reporting_tasks[user_id].append((client, task))
        except Exception as e:
            await bot.send_message(ADMIN_ID, f"⚠️ {uid} failed: {e}")

async def report_loop(client, target, user_id, uname, reasons, session_str, bot):
    try:
        while True:
            reason = random.choice(reasons)
            try:
                entity = await client.get_entity(target)
                await client(ReportPeerRequest(peer=entity, reason=reasons_map[reason], message="Reported"))

                # ✅ Show proxy used info (if enabled)
                proxy_text = ""
                if getattr(get_safe_client, "proxy_mode", False):
                    proxies = user_proxies.get(user_id, [])
                    proxy_data = random.choice(proxies)

                    if proxy_data:
                        ip, port = proxy_data[1], proxy_data[2]
                        userpass = f":{proxy_data[3]}:{proxy_data[4]}" if proxy_data[3] else ""
                        proxy_text = f"\n🌐 Used Proxy: {ip}:{port}{userpass}"

                await bot.send_message(user_id, f"📣 {uname} reported with {reason}{proxy_text}")

            except Exception as e:
                await bot.send_message(ADMIN_ID, f"⚠️ {uname} failed: {e}")
                break

            await asyncio.sleep(random.randint(3, 7))

    except Exception as e:
        await bot.send_message(ADMIN_ID, f"❌ {uname} crashed: {e}")
