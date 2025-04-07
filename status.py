from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from username_changer import active_changers as running_tasks


def get_status_message(user_id):
    if user_id not in running_tasks:
        return "📴 No active username changer running.", None

    status_text = (
        "✅ Username Changer is ACTIVE!\n\n"
        f"👤 User ID: `{user_id}`\n"
        f"🔁 Running: `Yes`\n"
        f"⏳ Interval: User-defined\n"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("🛑 Stop", callback_data="stop_changer")]
    ])

    return status_text, keyboard
