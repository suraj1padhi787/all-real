import asyncio
import random
import json
import os
import sqlite3
from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from telethon import TelegramClient, functions
from telethon.tl.functions.messages import DeleteHistoryRequest, ReportSpamRequest
from datetime import datetime

from config import API_ID, API_HASH
from db import create_report_table

create_report_table()
hard_report_active = True
selected_reasons = {}
awaiting_username = {}

def load_proxies():
    if not os.path.exists("proxies.json"):
        return []
    with open("proxies.json", "r") as f:
        return json.load(f)

def get_all_sessions():
    return [f for f in os.listdir("sessions") if f.endswith(".session")]

def insert_report_log(username, user_id, reported_by, proxy_used, reasons):
    conn = sqlite3.connect("sessions.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS username_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            user_id INTEGER,
            reported_by TEXT,
            proxy_used TEXT,
            reasons TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("INSERT INTO username_reports (username, user_id, reported_by, proxy_used, reasons) VALUES (?, ?, ?, ?, ?)",
              (username, user_id, reported_by, proxy_used, reasons))
    conn.commit()
    conn.close()

def get_reason_objects(selected):
    from telethon.tl.types import (
        InputReportReasonSpam,
        InputReportReasonViolence,
        InputReportReasonPornography,
        InputReportReasonChildAbuse,
        InputReportReasonOther
    )
    map = {
        "Spam": InputReportReasonSpam(),
        "Violence": InputReportReasonViolence(),
        "Porn": InputReportReasonPornography(),
        "Child Abuse": InputReportReasonChildAbuse(),
        "Other": InputReportReasonOther()
    }
    return [map[r] for r in selected if r in map]

def register_username_report_handlers(dp):
    @dp.message_handler(commands=['start_report_username'])
    async def start_report_cmd(msg: types.Message):
        awaiting_username[msg.from_user.id] = True
        selected_reasons[msg.from_user.id] = []
        await msg.reply("🔍 Send @username to report:")

    @dp.message_handler(lambda m: m.text.startswith("@"))
    async def get_username_handler(msg: types.Message):
        if not awaiting_username.get(msg.from_user.id): return
        username = msg.text.replace("@", "").strip()
        awaiting_username[msg.from_user.id] = username

        # Reason selector
        keyboard = InlineKeyboardMarkup(row_width=2)
        for r in ["Spam", "Violence", "Porn", "Child Abuse", "Other"]:
            keyboard.insert(InlineKeyboardButton(r, callback_data=f"reason_{r}"))
        keyboard.add(InlineKeyboardButton("🚀 Start Hard Report", callback_data="start_hard_report"))
        await msg.answer(f"✅ Username: @{username}\nNow choose report reasons ↓", reply_markup=keyboard)

    @dp.callback_query_handler(lambda c: c.data.startswith("reason_"))
    async def toggle_reason(callback: types.CallbackQuery):
        user_id = callback.from_user.id
        reason = callback.data.split("_")[1]
        if reason in selected_reasons[user_id]:
            selected_reasons[user_id].remove(reason)
        else:
            selected_reasons[user_id].append(reason)
        await callback.answer(f"Selected: {', '.join(selected_reasons[user_id])}")

    @dp.callback_query_handler(lambda c: c.data == "start_hard_report")
    async def hard_report(callback: types.CallbackQuery):
        global hard_report_active
        hard_report_active = True
        user_id = callback.from_user.id
        username = awaiting_username.get(user_id)
        reasons = selected_reasons.get(user_id, [])

        if not username or not reasons:
            return await callback.answer("❌ Missing username or reasons!")

        await callback.message.edit_text(f"🚨 Starting hard report on @{username}\nReasons: {', '.join(reasons)}")

        sessions = get_all_sessions()
        proxies = load_proxies()
        success = 0

        for session in sessions:
            if not hard_report_active:
                await callback.message.answer("🛑 Report stopped.")
                break

            session_path = f"sessions/{session}"
            proxy = random.choice(proxies) if proxies else None
            proxy_str = f"{proxy[1]}:{proxy[2]}" if proxy else "No Proxy"

            try:
                client = TelegramClient(session_path, API_ID, API_HASH, proxy=tuple(proxy) if proxy else None)
                await client.connect()
                user = await client.get_entity(username)

                # Send random msg
                msg = random.choice([
                    "Stop spamming Telegram.",
                    "This is abuse. You are reported.",
                    "Violation of community standards.",
                    "Reported to Telegram security.",
                    "Your actions are logged and flagged."
                ])
                await client.send_message(user.id, msg)
                await asyncio.sleep(random.randint(2, 4))

                # Report
                for r in get_reason_objects(reasons):
                    await client(ReportSpamRequest(peer=user, reason=r, message="Violation"))

                # Block
                await asyncio.sleep(random.randint(1, 2))
                await client(functions.contacts.BlockRequest(id=user.id))

                # Delete chat
                await asyncio.sleep(1)
                await client(DeleteHistoryRequest(peer=user, max_id=0, revoke=True))

                # Save log
                insert_report_log(username, user.id, session, proxy_str, ", ".join(reasons))
                await callback.message.answer(f"✅ `{session}`: Reported + Blocked\n🌐 Proxy: `{proxy_str}`", parse_mode="Markdown")
                success += 1
                await client.disconnect()

            except Exception as e:
                if "proxy" in str(e).lower() or "connection" in str(e).lower():
                    if proxy in proxies:
                        proxies.remove(proxy)
                        await callback.message.answer(f"❌ Proxy failed: `{proxy_str}`", parse_mode="Markdown")
                continue

        await callback.message.answer(f"🎯 Done! Total successful reports: {success}")

    @dp.message_handler(commands=['stop_report_username'])
    async def stop_report_cmd(msg: types.Message):
        global hard_report_active
        hard_report_active = False
        await msg.reply("🛑 Hard report stopped.")
