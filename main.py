import os
import logging
import asyncio
from typing import Set, Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ConversationHandler,
    CallbackContext,
)

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
BROADCAST_MSG, ASK_BUTTON, BUTTON_TEXT, BUTTON_URL = range(4)

# Environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
APK_LINK = os.getenv("APK_LINK", "https://example.com/app.apk")  # o‘zgartiring

# Muhit o‘zgaruvchilarini tekshirish
missing_vars = []
if not BOT_TOKEN:
    missing_vars.append("BOT_TOKEN")
if not ADMIN_ID:
    missing_vars.append("ADMIN_ID")
try:
    ADMIN_ID = int(ADMIN_ID) if ADMIN_ID else None
except ValueError:
    missing_vars.append("ADMIN_ID (integer bo‘lishi kerak)")

if missing_vars:
    raise ValueError(f"Kerakli o‘zgaruvchilar topilmadi: {', '.join(missing_vars)}")

# Xotirada ma'lumotlar
users: Set[int] = set()
settings: Dict[str, str] = {"apk_enabled": "false"}

def add_user(user_id: int):
    users.add(user_id)

def get_user_count() -> int:
    return len(users)

def get_all_users() -> list[int]:
    return list(users)

def get_setting(key: str) -> str:
    return settings.get(key, "false")

def set_setting(key: str, value: str):
    settings[key] = value

def is_admin(update: Update) -> bool:
    return update.effective_user.id == ADMIN_ID

# /start - chiroyli xabar
async def start(update: Update, context: CallbackContext):
    user = update.effective_user
    add_user(user.id)

    text = (
        "🌟 *Betwinner rasmiy boti* 🌟\n\n"
        "Endi Telegramdan *chiqmagan holda* bets larni amalga oshirishingiz mumkin.\n"
        "Ekran pastki qismidagi *BetsPlay* tugmasini bosib, Betwinner sahifasiga o‘ting va "
        "bets larni amalga oshiring.\n\n"
        "✨ *Foydalanuvchilarga qulaylik tilagan holda*, Betwinner! 🎉\n\n"
        "_Bot orqali har doim yangiliklar va qulayliklar siz bilan._"
    )

    keyboard = []
    if get_setting("apk_enabled") == "true":
        keyboard.append([InlineKeyboardButton("📥 APK yuklash", url=APK_LINK)])

    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)

# /users (admin)
async def users_count(update: Update, context: CallbackContext):
    if not is_admin(update):
        await update.message.reply_text("❌ Bu buyruq faqat admin uchun.")
        return
    count = get_user_count()
    await update.message.reply_text(f"👥 Foydalanuvchilar soni: {count}")

# /toggle_apk (admin)
async def toggle_apk(update: Update, context: CallbackContext):
    if not is_admin(update):
        await update.message.reply_text("❌ Bu buyruq faqat admin uchun.")
        return
    current = get_setting("apk_enabled")
    new = "false" if current == "true" else "true"
    set_setting("apk_enabled", new)
    status = "yoqildi ✅" if new == "true" else "o‘chirildi ❌"
    await update.message.reply_text(f"APK tugmasi {status}.")

# ------------------- BROADCAST (tugmalar bilan) -------------------
async def broadcast_start(update: Update, context: CallbackContext):
    if not is_admin(update):
        await update.message.reply_text("❌ Bu buyruq faqat admin uchun.")
        return ConversationHandler.END

    await update.message.reply_text(
        "📨 Endi barcha foydalanuvchilarga yubormoqchi bo‘lgan xabaringizni yuboring.\n"
        "(Matn, rasm, video, hujjat – istalgan formatda)\n"
        "Bekor qilish uchun /cancel yuboring."
    )
    return BROADCAST_MSG

async def broadcast_receive(update: Update, context: CallbackContext):
    # Xabarni vaqtincha saqlaymiz
    context.user_data['broadcast_message'] = update.message
    keyboard = [
        [InlineKeyboardButton("➕ Tugma qo‘shish", callback_data="add_btn")],
        [InlineKeyboardButton("❌ Tugmasiz yuborish", callback_data="no_btn")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Ushbu xabarga tugma qo‘shishni xohlaysizmi?",
        reply_markup=reply_markup
    )
    return ASK_BUTTON

async def button_choice(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    if query.data == "add_btn":
        await query.edit_message_text("Tugma matnini yuboring:")
        return BUTTON_TEXT
    else:  # no_btn
        # To‘g‘ridan-to‘g‘ri yuborish
        await send_broadcast(query, context, None)
        return ConversationHandler.END

async def button_text(update: Update, context: CallbackContext):
    context.user_data['btn_text'] = update.message.text
    await update.message.reply_text(
        "Tugma URL manzilini yuboring.\n"
        "Agar *APK yuklash* tugmasi bo‘lishini istasangiz /skip yuboring."
    )
    return BUTTON_URL

async def button_url(update: Update, context: CallbackContext):
    text = update.message.text
    if text == "/skip":
        url = APK_LINK
        btn_text = context.user_data.get('btn_text', "📥 APK yuklash")
    else:
        url = text
        btn_text = context.user_data['btn_text']

    button = InlineKeyboardButton(btn_text, url=url)
    await send_broadcast(update, context, button)
    return ConversationHandler.END

async def send_broadcast(update_or_query, context: CallbackContext, button=None):
    # Xabarni olish
    msg = context.user_data.get('broadcast_message')
    if not msg:
        await (update_or_query.message.reply_text("Xatolik: xabar topilmadi."))
        return

    users_list = get_all_users()
    sent = failed = 0
    reply_markup = InlineKeyboardMarkup([[button]]) if button else None

    # Xabar borligini bildirish
    await (update_or_query.message.reply_text(
        f"⏳ Xabar {len(users_list)} ta foydalanuvchiga yuborilmoqda..."
    ))

    for uid in users_list:
        try:
            await msg.copy(chat_id=uid, reply_markup=reply_markup)
            sent += 1
        except Exception as e:
            logger.warning(f"Yuborilmadi {uid}: {e}")
            failed += 1
        await asyncio.sleep(0.05)

    await (update_or_query.message.reply_text(
        f"✅ Yuborildi: {sent}\n❌ Xatolik: {failed}"
    ))

    # Tozalash
    context.user_data.clear()

async def broadcast_cancel(update: Update, context: CallbackContext):
    await update.message.reply_text("🚫 Broadcast bekor qilindi.")
    context.user_data.clear()
    return ConversationHandler.END

# Noma'lum buyruqlar
async def unknown(update: Update, context: CallbackContext):
    await update.message.reply_text("❓ Tushunarsiz buyruq.")

# ------------------- Asosiy funksiya -------------------
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Oddiy handlerlar
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("users", users_count))
    app.add_handler(CommandHandler("toggle_apk", toggle_apk))

    # Broadcast conversation handler
    broadcast_conv = ConversationHandler(
        entry_points=[CommandHandler("broadcast", broadcast_start)],
        states={
            BROADCAST_MSG: [MessageHandler(filters.ALL & ~filters.COMMAND, broadcast_receive)],
            ASK_BUTTON: [CallbackQueryHandler(button_choice)],
            BUTTON_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, button_text)],
            BUTTON_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, button_url)],
        },
        fallbacks=[CommandHandler("cancel", broadcast_cancel)],
    )
    app.add_handler(broadcast_conv)

    # Noma'lum buyruqlar
    app.add_handler(MessageHandler(filters.COMMAND, unknown))

    # Botni ishga tushirish
    app.run_polling()

if __name__ == "__main__":
    main()
